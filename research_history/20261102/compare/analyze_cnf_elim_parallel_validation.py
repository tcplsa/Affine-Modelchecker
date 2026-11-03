#!/usr/bin/env python3
"""Summarize four-lane elimination-order validation."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path

from run_cnf_elim_parallel_validation import configs_for_set


VALID = {"SAFE", "UNSAFE"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config-set", choices=("all", "core"), default="all")
    args = parser.parse_args()
    with args.input.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    lines = [
        "# Four-lane elimination-order validation", "",
        f"Models: {len(rows)}. Timeout is charged at 1.5x.", "",
        "| Configuration | Solved | Only vs reference | Lost | Penalized cost | Common | "
        "Runtime geo | Runtime median | Wins >2s | Losses >2s |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for ident, label, representation, _order, _lanes in configs_for_set(args.config_set):
        reference = "aig_legacy4" if representation == "aig" else "xag_legacy4"
        solved = lambda row, config: row.get(f"{config}_status") in VALID
        common = [row for row in rows if solved(row, ident) and solved(row, reference)]
        only = sum(solved(row, ident) and not solved(row, reference) for row in rows)
        lost = sum(solved(row, reference) and not solved(row, ident) for row in rows)
        cost = sum(
            float(row[f"{ident}_wall_seconds"])
            if solved(row, ident) else 1.5 * float(row["timeout_seconds"])
            for row in rows
        )
        ratios = [
            float(row[f"{ident}_wall_seconds"]) / float(row[f"{reference}_wall_seconds"])
            for row in common if float(row[f"{reference}_wall_seconds"]) > 0
        ]
        geo = math.exp(sum(math.log(value) for value in ratios) / len(ratios)) if ratios else None
        median = statistics.median(ratios) if ratios else None
        wins = sum(
            float(row[f"{ident}_wall_seconds"]) + 2.0
            < float(row[f"{reference}_wall_seconds"])
            for row in common
        )
        losses = sum(
            float(row[f"{reference}_wall_seconds"]) + 2.0
            < float(row[f"{ident}_wall_seconds"])
            for row in common
        )
        fmt = lambda value: "-" if value is None else f"{value:.3f}"
        lines.append(
            f"| {label} | {sum(solved(row, ident) for row in rows)} | {only} | {lost} | "
            f"{cost:.1f} | {len(common)} | {fmt(geo)} | {fmt(median)} | {wins} | {losses} |"
        )
    lines += ["", f"Outcome conflicts: {sum(row.get('outcome_conflict') == '1' for row in rows)}.", ""]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"rows={len(rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
