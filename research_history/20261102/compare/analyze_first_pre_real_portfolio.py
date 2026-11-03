#!/usr/bin/env python3
"""Report real four-lane first-model portfolio validation."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


CONFIGS = [
    ("aig4_default", "4 AIG default"),
    ("xag4_default", "4 XAG default"),
    ("aig4_phase", "4 AIG phase-diverse"),
    ("xag4_phase", "4 XAG phase-diverse"),
    ("mixed4_phase", "3 AIG + 1 XAG phase-diverse"),
    ("mixed4_struct", "2 AIG + 2 XAG structural"),
]
VALID = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def metrics(rows: list[dict[str, str]], cfg: str) -> tuple[int, int, int, float]:
    solved = safe = unsafe = 0
    cost = 0.0
    for row in rows:
        status = row[f"{cfg}_status"]
        if status in VALID:
            solved += 1
            safe += status == "SAFE"
            unsafe += status == "UNSAFE"
            cost += float(row[f"{cfg}_wall_seconds"])
        else:
            cost += 1.5 * float(row["timeout_seconds"])
    return solved, safe, unsafe, cost


def main() -> int:
    args = parse_args()
    rows = list(csv.DictReader(args.input.open(encoding="utf-8"), delimiter="\t"))
    baselines = {cfg: metrics(rows, cfg) for cfg, _ in CONFIGS}
    base_cost = baselines["aig4_default"][3]
    lines = [
        "# Real four-lane first-model portfolio", "", f"Models: {len(rows)}.", "",
        "| Configuration | Solved | SAFE | UNSAFE | Extra vs 4AIG | Penalized delta |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    base_solved = baselines["aig4_default"][0]
    for cfg, label in CONFIGS:
        solved, safe, unsafe, cost = baselines[cfg]
        delta = (base_cost - cost) / base_cost * 100 if base_cost else 0.0
        lines.append(f"| {label} | {solved} | {safe} | {unsafe} | {solved-base_solved:+d} | {delta:+.1f}% |")
    conflicts = sum(row.get("outcome_conflict") == "1" for row in rows)
    lines += ["", f"Outcome conflicts: {conflicts}.", ""]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"rows={len(rows)} conflicts={conflicts} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
