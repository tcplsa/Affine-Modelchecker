#!/usr/bin/env python3
"""Analyze BVE telemetry inside the strict multi-seed MC confirmation cohort."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path


CANDIDATE = "xag_sumhigh4"
REFERENCE = "xag_legacy4"
VALID = {"SAFE", "UNSAFE"}
METRICS = (
    ("translation_simplified_clauses", "Residual clauses"),
    ("translation_simplified_literals", "Residual literals"),
    ("translation_bve_resolvents", "Retained resolvents"),
    ("translation_bve_resolvent_literals", "Resolvent literals"),
    ("translation_bve_max_resolvent_size", "Maximum resolvent width"),
    ("translation_bve_merge_checks", "Estimated merge checks"),
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def read_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle, delimiter="\t"))
    return rows


def geometric(values: list[float]) -> float:
    return math.exp(statistics.mean(math.log(value) for value in values))


def correlation(left: list[float], right: list[float]) -> float:
    if len(left) < 3:
        return math.nan
    left_mean = statistics.mean(left)
    right_mean = statistics.mean(right)
    left_delta = [value - left_mean for value in left]
    right_delta = [value - right_mean for value in right]
    denominator = math.sqrt(
        sum(value * value for value in left_delta)
        * sum(value * value for value in right_delta)
    )
    if denominator == 0:
        return math.nan
    return sum(a * b for a, b in zip(left_delta, right_delta)) / denominator


def model_rows(
    rows: list[dict[str, str]], tier: str | None,
) -> list[tuple[dict[str, str], float | None]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["model_id"]].append(row)
    result = []
    for current in grouped.values():
        if tier is not None and current[0]["tier"] != tier:
            continue
        common = [
            row for row in current
            if row[f"{CANDIDATE}_status"] in VALID
            and row[f"{REFERENCE}_status"] in VALID
        ]
        runtime_ratio = None
        if common:
            runtime_ratio = geometric([
                float(row[f"{CANDIDATE}_wall_seconds"])
                / float(row[f"{REFERENCE}_wall_seconds"])
                for row in common
            ])
        result.append((current[0], runtime_ratio))
    return result


def add_table(
    lines: list[str], title: str,
    rows: list[tuple[dict[str, str], float | None]],
) -> None:
    lines += [
        "",
        f"## {title}",
        "",
        f"Models in scope: {len(rows)}.",
        "",
        "| Observable | Pairs | Geo ratio | Median ratio | Correlation with log runtime ratio |",
        "|---|---:|---:|---:|---:|",
    ]
    for field, label in METRICS:
        ratios = []
        runtime_logs = []
        telemetry_logs = []
        for row, runtime_ratio in rows:
            try:
                candidate = float(row[f"{CANDIDATE}_{field}"])
                reference = float(row[f"{REFERENCE}_{field}"])
            except (KeyError, ValueError):
                continue
            if candidate <= 0 or reference <= 0:
                continue
            ratio = candidate / reference
            ratios.append(ratio)
            if runtime_ratio is not None:
                runtime_logs.append(math.log(runtime_ratio))
                telemetry_logs.append(math.log(ratio))
        lines.append(
            f"| {label} | {len(ratios)} | {geometric(ratios):.3f} | "
            f"{statistics.median(ratios):.3f} | "
            f"{correlation(runtime_logs, telemetry_logs):+.3f} |"
        )


def main() -> int:
    args = arguments()
    rows = read_rows(args.inputs)
    lines = [
        "# Strict-cohort MC BVE telemetry",
        "",
        "Telemetry ratios use one structural record per model, including unresolved "
        "models. Runtime ratios are geometric means over common-solved seed blocks. "
        "Correlations use the common-solved subset and are Pearson correlations between "
        "per-model log telemetry and log runtime ratios.",
    ]
    add_table(lines, "All strict-cohort models", model_rows(rows, None))
    add_table(lines, "Historical-fast tier", model_rows(rows, "fast"))
    add_table(lines, "Historical-timeout tier", model_rows(rows, "timeout"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
