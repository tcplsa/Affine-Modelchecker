#!/usr/bin/env python3
"""Analyze concurrent Native legacy versus product-sum-high validation."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}
CANDIDATE = "ric3_product_sum_high"
REFERENCE = "ric3_legacy"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--inputs", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def solved(row: dict[str, str], config: str) -> bool:
    return row[f"{config}_status"] in VALID


def runtime(row: dict[str, str], config: str) -> float:
    return float(row[f"{config}_wall_seconds"])


def evaluate(rows: list[dict[str, str]]) -> dict[str, float | int]:
    informative = [row for row in rows if solved(row, CANDIDATE) or solved(row, REFERENCE)]
    common = [row for row in informative if solved(row, CANDIDATE) and solved(row, REFERENCE)]
    ratios = [runtime(row, CANDIDATE) / runtime(row, REFERENCE) for row in common]
    def cost(row: dict[str, str], config: str) -> float:
        return runtime(row, config) if solved(row, config) else 1.5 * float(row["timeout_seconds"])
    return {
        "rows": len(rows),
        "candidate": sum(solved(row, CANDIDATE) for row in rows),
        "reference": sum(solved(row, REFERENCE) for row in rows),
        "only": sum(solved(row, CANDIDATE) and not solved(row, REFERENCE) for row in rows),
        "lost": sum(solved(row, REFERENCE) and not solved(row, CANDIDATE) for row in rows),
        "common": len(common),
        "geo": math.exp(statistics.mean(map(math.log, ratios))) if ratios else math.nan,
        "median": statistics.median(ratios) if ratios else math.nan,
        "wins": sum(runtime(row, CANDIDATE) + 2 < runtime(row, REFERENCE) for row in common),
        "losses": sum(runtime(row, REFERENCE) + 2 < runtime(row, CANDIDATE) for row in common),
        "par": (
            sum(cost(row, CANDIDATE) for row in informative)
            / sum(cost(row, REFERENCE) for row in informative)
        ) if informative else math.nan,
    }


def clustered_interval(rows: list[dict[str, str]], iterations: int = 10000) -> tuple[float, float]:
    by_model: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if solved(row, CANDIDATE) and solved(row, REFERENCE):
            by_model[row["model_id"]].append(
                math.log(runtime(row, CANDIDATE) / runtime(row, REFERENCE))
            )
    models = sorted(by_model)
    if not models:
        return math.nan, math.nan
    rng = random.Random(20260811)
    values = []
    for _ in range(iterations):
        sample = [rng.choice(models) for _ in models]
        logs = [value for model in sample for value in by_model[model]]
        values.append(math.exp(statistics.mean(logs)))
    values.sort()
    return values[int(iterations * 0.025)], values[int(iterations * 0.975) - 1]


def add_table(lines: list[str], title: str, groups) -> None:
    lines += ["", f"## {title}", "", "| Cohort | Rows | Solved candidate/reference | Only/lost | Common | Geo (model CI) | Median | W/L >2s | PAR-1.5 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for label, rows in groups:
        value = evaluate(rows)
        ci_low, ci_high = clustered_interval(rows)
        lines.append(
            f"| {label} | {value['rows']} | {value['candidate']}/{value['reference']} | "
            f"{value['only']}/{value['lost']} | {value['common']} | "
            f"{value['geo']:.3f} [{ci_low:.3f}, {ci_high:.3f}] | {value['median']:.3f} | "
            f"{value['wins']}/{value['losses']} | {value['par']:.3f} |"
        )


def main() -> int:
    args = arguments()
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    metadata = {model["id"]: model for model in selection["models"]}
    rows = []
    cohorts = []
    for path in args.inputs:
        with path.open(encoding="utf-8") as handle:
            current = list(csv.DictReader(handle, delimiter="\t"))
        cohorts.append((path.stem, current))
        rows.extend(current)
    ci_low, ci_high = clustered_interval(rows)
    lines = [
        "# Concurrent rIC3 BVE-order validation", "",
        "Candidate: Native product-sum-high. Reference: Native legacy. Both four replicas and launched concurrently per model.", "",
        f"Models: {len(selection['ids'])}; model-seed rows: {len(rows)}; outcome conflicts: {sum(row['outcome_conflict'] == '1' for row in rows)}.",
        f"Model-clustered 95% bootstrap interval for the common-solve geometric ratio: [{ci_low:.3f}, {ci_high:.3f}].",
    ]
    add_table(lines, "Aggregate and seeds", [("Aggregate", rows), *cohorts])
    years = sorted({int(model["year"]) for model in metadata.values()})
    add_table(lines, "Years", [(str(year), [row for row in rows if int(metadata[row["model_id"]]["year"]) == year]) for year in years])
    tiers = ("trivial", "fast", "medium", "slow", "timeout")
    add_table(lines, "Historical tiers", [(tier, [row for row in rows if metadata[row["model_id"]]["tier"] == tier]) for tier in tiers])
    outcomes = ("SAFE", "UNSAFE")
    add_table(lines, "Outcomes", [(outcome, [row for row in rows if row["outcome"] == outcome]) for outcome in outcomes])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows={len(rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
