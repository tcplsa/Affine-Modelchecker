#!/usr/bin/env python3
"""Compare an equal-budget 2xw0+2xw2 portfolio with a recorded 4xw0 baseline."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", nargs="+", required=True, type=Path)
    parser.add_argument("--portfolio", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def read(paths: list[Path]) -> dict[tuple[str, str], dict[str, str]]:
    rows: dict[tuple[str, str], dict[str, str]] = {}
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = (row["model_id"], row["seed_block"])
                if key in rows:
                    raise ValueError(f"duplicate row {key}")
                rows[key] = row
    return rows


def solved(row: dict[str, str], config: str) -> bool:
    return row[f"{config}_status"] in VALID


def runtime(row: dict[str, str], config: str) -> float:
    return float(row[f"{config}_wall_seconds"])


def evaluate(keys, baseline, portfolio) -> dict[str, float | int]:
    values = []
    for key in keys:
        base_row = baseline[key]
        port_row = portfolio[key]
        base_ok = solved(base_row, "ric3_width_w0")
        solved_configs = [
            config for config in ("ric3_width_w0", "ric3_width_w2")
            if solved(port_row, config)
        ]
        port_ok = bool(solved_configs)
        port_time = min((runtime(port_row, config) for config in solved_configs), default=math.inf)
        base_time = runtime(base_row, "ric3_width_w0")
        timeout = float(base_row["timeout_seconds"])
        values.append((base_ok, port_ok, base_time, port_time, timeout))
    informative = [value for value in values if value[0] or value[1]]
    common = [value for value in informative if value[0] and value[1]]
    ratios = [value[3] / value[2] for value in common]
    base_cost = sum(value[2] if value[0] else 1.5 * value[4] for value in informative)
    port_cost = sum(value[3] if value[1] else 1.5 * value[4] for value in informative)
    return {
        "rows": len(values),
        "solved": sum(value[1] for value in values),
        "base": sum(value[0] for value in values),
        "only": sum(value[1] and not value[0] for value in values),
        "lost": sum(value[0] and not value[1] for value in values),
        "common": len(common),
        "geo": math.exp(statistics.mean(map(math.log, ratios))) if ratios else math.nan,
        "median": statistics.median(ratios) if ratios else math.nan,
        "wins": sum(value[3] + 2 < value[2] for value in common),
        "losses": sum(value[2] + 2 < value[3] for value in common),
        "par": port_cost / base_cost if base_cost else math.nan,
    }


def fmt(value: float | int) -> str:
    return str(value) if isinstance(value, int) else f"{value:.3f}"


def main() -> int:
    args = arguments()
    baseline = read(args.baseline)
    portfolio = read(args.portfolio)
    if baseline.keys() != portfolio.keys():
        missing = baseline.keys() ^ portfolio.keys()
        raise ValueError(f"input key mismatch: {len(missing)} rows")
    seeds = sorted({key[1] for key in baseline})
    groups = [("Aggregate", sorted(baseline))]
    groups += [(f"Seed {seed}", sorted(key for key in baseline if key[1] == seed)) for seed in seeds]
    lines = [
        "# Equal-budget BVE width portfolio",
        "",
        "Candidate: two native-width replicas plus two width-weight=2 replicas. Baseline: four native-width replicas.",
        "",
        "| Cohort | Rows | Solved 2+2 / 4xw0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, keys in groups:
        value = evaluate(keys, baseline, portfolio)
        lines.append(
            f"| {label} | {value['rows']} | {value['solved']}/{value['base']} | "
            f"{value['only']}/{value['lost']} | {value['common']} | {fmt(value['geo'])} | "
            f"{fmt(value['median'])} | {value['wins']}/{value['losses']} | {fmt(value['par'])} |"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows={len(baseline)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
