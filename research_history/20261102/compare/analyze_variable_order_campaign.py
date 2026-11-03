#!/usr/bin/env python3
"""Rank deterministic CaDiCaL variable orders against first occurrence."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout-penalty", type=float, default=1.5)
    parser.add_argument("--min-difference", type=float, default=2.0)
    args = parser.parse_args()

    cells: dict[tuple[str, str, str, str], dict[str, str]] = {}
    duplicates = 0
    for path in args.inputs:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = (row["model_id"], row["run"], row["config"], row["variable_order"])
                duplicates += key in cells
                cells[key] = row

    configs = sorted({key[2] for key in cells})
    orders = sorted({key[3] for key in cells})
    lines = [
        "# Variable Order Campaign", "",
        f"Rows: {len(cells)}; duplicates replaced: {duplicates}; timeout penalty: {args.timeout_penalty:.2f}x; "
        f"small-difference threshold: {args.min_difference:.2f}s.", "",
    ]
    for config in configs:
        lines.extend([
            f"## {config}", "",
            "| Order | Paired | Solved | Base/order only | Penalized reduction | Joint reduction | Median base/order | Wins > threshold (base/order) |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for order in orders:
            pairs = []
            for model, run, candidate_config, candidate_order in cells:
                if candidate_config != config or candidate_order != order:
                    continue
                baseline = cells.get((model, run, config, "first"))
                if baseline is not None:
                    pairs.append((baseline, cells[(model, run, config, order)]))
            if not pairs:
                continue
            eligible = [pair for pair in pairs if pair[0]["status"] in SOLVED or pair[1]["status"] in SOLVED]
            joint = [pair for pair in pairs if pair[0]["status"] in SOLVED and pair[1]["status"] in SOLVED]
            def cost(row: dict[str, str]) -> float:
                return float(row["wall_seconds"]) if row["status"] in SOLVED else args.timeout_penalty * float(row["timeout_seconds"])
            base_total = sum(cost(base) for base, _ in eligible)
            order_total = sum(cost(candidate) for _, candidate in eligible)
            base_joint = sum(float(base["wall_seconds"]) for base, _ in joint)
            order_joint = sum(float(candidate["wall_seconds"]) for _, candidate in joint)
            ratios = [
                float(base["wall_seconds"]) / max(float(candidate["wall_seconds"]), 1e-9)
                for base, candidate in joint
            ]
            base_only = sum(base["status"] in SOLVED and candidate["status"] not in SOLVED for base, candidate in pairs)
            order_only = sum(candidate["status"] in SOLVED and base["status"] not in SOLVED for base, candidate in pairs)
            base_wins = sum(
                float(base["wall_seconds"]) + args.min_difference < float(candidate["wall_seconds"])
                for base, candidate in joint
            )
            order_wins = sum(
                float(candidate["wall_seconds"]) + args.min_difference < float(base["wall_seconds"])
                for base, candidate in joint
            )
            reduction = 100.0 * (base_total - order_total) / base_total if base_total else 0.0
            joint_reduction = 100.0 * (base_joint - order_joint) / base_joint if base_joint else 0.0
            lines.append(
                f"| {order} | {len(pairs)} | {sum(candidate['status'] in SOLVED for _, candidate in pairs)} | "
                f"{base_only}/{order_only} | {reduction:+.2f}% | {joint_reduction:+.2f}% | "
                f"{statistics.median(ratios) if ratios else math.nan:.3f} | {base_wins}/{order_wins} |"
            )
        status = Counter(
            row["status"] for key, row in cells.items() if key[2] == config
        )
        lines.extend(["", f"Status counts: {dict(status)}", ""])
    report = "\n".join(lines) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
