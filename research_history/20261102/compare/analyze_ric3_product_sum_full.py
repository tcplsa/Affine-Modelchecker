#!/usr/bin/env python3
"""Compare Native product-sum-high with completed full rIC3 baselines."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}
CANDIDATE = "native_product_sum_high4"
REFERENCES = (
    ("native_legacy4", "Native legacy"),
    ("native_product_high4", "Native product-high"),
    ("native_local4", "Native native-local"),
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", nargs="+", required=True, type=Path)
    parser.add_argument("--candidate", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def read_rows(paths: list[Path]) -> dict[str, dict[str, str]]:
    rows = {}
    for path in paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = row.get("model_id") or row["name"]
                if key in rows:
                    raise ValueError(f"duplicate model: {key}")
                rows[key] = row
    return rows


def solved(row: dict[str, str], config: str) -> bool:
    return row.get(f"{config}_status") in VALID


def runtime(row: dict[str, str], config: str) -> float:
    return float(row[f"{config}_wall_seconds"])


def pair(rows: list[dict[str, str]], reference: str) -> dict[str, float | int]:
    common = [row for row in rows if solved(row, CANDIDATE) and solved(row, reference)]
    informative = [row for row in rows if solved(row, CANDIDATE) or solved(row, reference)]
    ratios = [runtime(row, CANDIDATE) / runtime(row, reference) for row in common]
    penalty = lambda row, config: (
        runtime(row, config) if solved(row, config)
        else 1.5 * float(row["timeout_seconds"])
    )
    ref_cost = sum(penalty(row, reference) for row in informative)
    return {
        "candidate": sum(solved(row, CANDIDATE) for row in rows),
        "reference": sum(solved(row, reference) for row in rows),
        "only": sum(solved(row, CANDIDATE) and not solved(row, reference) for row in rows),
        "lost": sum(solved(row, reference) and not solved(row, CANDIDATE) for row in rows),
        "common": len(common),
        "geo": math.exp(statistics.mean(map(math.log, ratios))) if ratios else math.nan,
        "median": statistics.median(ratios) if ratios else math.nan,
        "wins": sum(runtime(row, CANDIDATE) + 2 < runtime(row, reference) for row in common),
        "losses": sum(runtime(row, reference) + 2 < runtime(row, CANDIDATE) for row in common),
        "par": (
            sum(penalty(row, CANDIDATE) for row in informative) / ref_cost
            if ref_cost else math.nan
        ),
    }


def fmt(value: float | int) -> str:
    return str(value) if isinstance(value, int) else (
        "-" if math.isnan(value) else f"{value:.3f}"
    )


def table(lines: list[str], title: str, rows: list[dict[str, str]]) -> None:
    lines += ["", f"## {title}", "",
              "| Reference | Solved candidate/reference | Only/lost | Common | Geo | Median | W/L >2s | PAR |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for reference, label in REFERENCES:
        stats = pair(rows, reference)
        lines.append(
            f"| {label} | {stats['candidate']}/{stats['reference']} | "
            f"{stats['only']}/{stats['lost']} | {stats['common']} | "
            f"{fmt(stats['geo'])} | {fmt(stats['median'])} | "
            f"{stats['wins']}/{stats['losses']} | {fmt(stats['par'])} |"
        )


def main() -> int:
    args = arguments()
    baseline = read_rows(args.baseline)
    candidate = read_rows(args.candidate)
    rows = []
    for model_id, new_row in candidate.items():
        old_row = baseline.get(model_id)
        if old_row is None:
            continue
        merged = dict(old_row)
        merged.update({key: value for key, value in new_row.items()
                       if key.startswith(f"{CANDIDATE}_")})
        rows.append(merged)

    lines = ["# rIC3 Native product-sum-high full validation", "",
             f"Joined models: {len(rows)}. Outcome conflicts: "
             f"{sum(row.get('outcome_conflict') == '1' for row in rows)}."]
    table(lines, "All completed candidate models", rows)

    by_year = defaultdict(list)
    by_tier = defaultdict(list)
    for row in rows:
        by_year[row.get("year", "unknown")].append(row)
        by_tier[row.get("tier", "unknown")].append(row)
    for year in sorted(by_year):
        table(lines, f"Year {year}", by_year[year])
    for tier in sorted(by_tier):
        table(lines, f"Tier {tier}", by_tier[tier])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"joined={len(rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
