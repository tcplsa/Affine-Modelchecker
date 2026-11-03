#!/usr/bin/env python3
"""Analyze rIC3 BVE-order screens and portfolio validation."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path

from run_ric3_bve_validation import ORDERS


VALID = {"SAFE", "UNSAFE"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with args.input.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    reference = "xag_legacy"
    configs = [("aig_legacy", "AIG legacy"), *[
        (f"xag_{ident}", f"XAG {order}") for ident, order in ORDERS
    ]]
    lines = [
        "# rIC3 deterministic BVE-order report", "", f"Models: {len(rows)}.", "",
        "| Configuration | Solved | Only vs XAG legacy | Lost | Penalized cost | Common | "
        "Runtime geo | Runtime median | Wins >2s | Losses >2s |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    solved = lambda row, config: row.get(f"{config}_status") in VALID
    for config, label in configs:
        common = [row for row in rows if solved(row, config) and solved(row, reference)]
        only = sum(solved(row, config) and not solved(row, reference) for row in rows)
        lost = sum(solved(row, reference) and not solved(row, config) for row in rows)
        cost = sum(
            float(row[f"{config}_wall_seconds"])
            if solved(row, config) else 1.5 * float(row["timeout_seconds"])
            for row in rows
        )
        ratios = [
            float(row[f"{config}_wall_seconds"]) / float(row[f"{reference}_wall_seconds"])
            for row in common if float(row[f"{reference}_wall_seconds"]) > 0
        ]
        geo = math.exp(sum(math.log(value) for value in ratios) / len(ratios)) if ratios else None
        median = statistics.median(ratios) if ratios else None
        wins = sum(
            float(row[f"{config}_wall_seconds"]) + 2.0
            < float(row[f"{reference}_wall_seconds"])
            for row in common
        )
        losses = sum(
            float(row[f"{reference}_wall_seconds"]) + 2.0
            < float(row[f"{config}_wall_seconds"])
            for row in common
        )
        fmt = lambda value: "-" if value is None else f"{value:.3f}"
        lines.append(
            f"| {label} | {sum(solved(row, config) for row in rows)} | {only} | {lost} | "
            f"{cost:.1f} | {len(common)} | {fmt(geo)} | {fmt(median)} | {wins} | {losses} |"
        )
    lines += ["", f"Outcome conflicts: {sum(row.get('outcome_conflict') == '1' for row in rows)}.", ""]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"rows={len(rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
