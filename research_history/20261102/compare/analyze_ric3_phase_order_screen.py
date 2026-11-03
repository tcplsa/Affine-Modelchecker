#!/usr/bin/env python3
"""Rank phase-specific BVE order assignments against all-legacy."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}
SEQUENCES = ("LLL", "PLL", "LPL", "LLP", "PPL", "PLP", "LPP", "PPP")
REFERENCE = "phase_lll"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def solved(row: dict[str, str], config: str) -> bool:
    return row[f"{config}_status"] in VALID


def runtime(row: dict[str, str], config: str) -> float:
    return float(row[f"{config}_wall_seconds"])


def evaluate(rows: list[dict[str, str]], config: str) -> dict[str, float | int]:
    informative = [row for row in rows if solved(row, config) or solved(row, REFERENCE)]
    common = [row for row in informative if solved(row, config) and solved(row, REFERENCE)]
    ratios = [runtime(row, config) / runtime(row, REFERENCE) for row in common]
    def cost(row: dict[str, str], name: str) -> float:
        return runtime(row, name) if solved(row, name) else 1.5 * float(row["timeout_seconds"])
    return {
        "solved": sum(solved(row, config) for row in rows),
        "reference": sum(solved(row, REFERENCE) for row in rows),
        "only": sum(solved(row, config) and not solved(row, REFERENCE) for row in rows),
        "lost": sum(solved(row, REFERENCE) and not solved(row, config) for row in rows),
        "common": len(common),
        "geo": math.exp(statistics.mean(map(math.log, ratios))) if ratios else math.nan,
        "median": statistics.median(ratios) if ratios else math.nan,
        "wins": sum(runtime(row, config) + 2 < runtime(row, REFERENCE) for row in common),
        "losses": sum(runtime(row, REFERENCE) + 2 < runtime(row, config) for row in common),
        "par": (
            sum(cost(row, config) for row in informative)
            / sum(cost(row, REFERENCE) for row in informative)
        ) if informative else math.nan,
    }


def table(lines: list[str], title: str, rows: list[dict[str, str]]) -> None:
    lines += ["", f"## {title}", "", "| Sequence | Solved candidate/LLL | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for sequence in SEQUENCES:
        value = evaluate(rows, f"phase_{sequence.lower()}")
        lines.append(
            f"| {sequence} | {value['solved']}/{value['reference']} | "
            f"{value['only']}/{value['lost']} | {value['common']} | "
            f"{value['geo']:.3f} | {value['median']:.3f} | "
            f"{value['wins']}/{value['losses']} | {value['par']:.3f} |"
        )


def main() -> int:
    args = arguments()
    rows = []
    for path in args.inputs:
        with path.open(encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle, delimiter="\t"))
    lines = [
        "# rIC3 phase-specific BVE order screen", "",
        f"Models: {len(rows)}; outcome conflicts: {sum(row['outcome_conflict'] == '1' for row in rows)}.",
        "L is legacy and P is product-sum-high for initial, post-SCorr, and post-FrTs BVE phases.",
    ]
    table(lines, "Aggregate", rows)
    for tier in ("trivial", "fast", "medium", "slow", "timeout"):
        table(lines, f"Tier {tier}", [row for row in rows if row["tier"] == tier])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows={len(rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
