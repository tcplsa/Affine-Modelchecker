#!/usr/bin/env python3
"""Select up to four complementary rIC3 workers by solved-set coverage."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from run_ric3_four_core_baseline import CONFIGS


VALID = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def portfolio(rows: list[dict[str, str]], selected: list[str]) -> tuple[int, int, int, float]:
    solved = safe = unsafe = 0
    cost = 0.0
    for row in rows:
        candidates = [
            (float(row[f"{cfg}_wall_seconds"]), row[f"{cfg}_status"])
            for cfg in selected if row[f"{cfg}_status"] in VALID
        ]
        if candidates:
            elapsed, status = min(candidates)
            solved += 1
            safe += status == "SAFE"
            unsafe += status == "UNSAFE"
            cost += elapsed
        else:
            cost += 1.5 * float(row["timeout_seconds"])
    return solved, safe, unsafe, cost


def main() -> int:
    args = parse_args()
    rows = list(csv.DictReader(args.input.open(encoding="utf-8"), delimiter="\t"))
    ids = [item[0] for item in CONFIGS]
    labels = {item[0]: item[1] for item in CONFIGS}
    lines = ["# rIC3 four-core baseline screen", "", f"Models: {len(rows)}.", ""]
    lines += ["| Worker | Solved | SAFE | UNSAFE | Penalized cost |", "|---|---:|---:|---:|---:|"]
    for cfg in ids:
        solved, safe, unsafe, cost = portfolio(rows, [cfg])
        lines.append(f"| {labels[cfg]} | {solved} | {safe} | {unsafe} | {cost:.1f} |")

    selected: list[str] = []
    lines += ["", "## Greedy coverage", "", "| Cores | Added worker | Solved | SAFE | UNSAFE | Penalized cost |", "|---:|---|---:|---:|---:|---:|"]
    remaining = set(ids)
    for core in range(1, 5):
        choice = max(
            remaining,
            key=lambda cfg: (
                portfolio(rows, selected + [cfg])[0],
                -portfolio(rows, selected + [cfg])[3],
            ),
        )
        selected.append(choice)
        remaining.remove(choice)
        solved, safe, unsafe, cost = portfolio(rows, selected)
        lines.append(f"| {core} | {labels[choice]} | {solved} | {safe} | {unsafe} | {cost:.1f} |")

    conflicts = sum(row.get("outcome_conflict") == "1" for row in rows)
    lines += ["", f"Outcome conflicts: {conflicts}.", "", "Selected four-worker baseline:", ""]
    lines.extend(f"- `{cfg}`: {labels[cfg]}" for cfg in selected)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"rows={len(rows)} selected={','.join(selected)} conflicts={conflicts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
