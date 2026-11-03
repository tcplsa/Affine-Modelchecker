#!/usr/bin/env python3
"""Summarize matched compact/stable/canonical XOR experiments."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


MODE_ORDER = (
    "compact", "stable", "canonical_compact", "canonical_stable",
    "raw_canonical_compact", "raw_canonical_stable",
    "precanonical_compact", "precanonical_stable",
)
VALID = {"SAFE", "UNSAFE"}


def median(values: list[float]) -> float:
    return statistics.median(values) if values else math.nan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--penalty", type=float, default=900.0)
    args = parser.parse_args()
    with args.input.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["variant"], row["mode"])].append(row)

    variants = sorted({row["variant"] for row in rows})
    observed_modes = {row["mode"] for row in rows}
    modes = [mode for mode in MODE_ORDER if mode in observed_modes]
    lines = [
        "# XOR Canonical-Numbering Mechanism Report", "",
        f"Rows: {len(rows)}; variants: {len(variants)}.", "",
        "| Variant | Mode | Solved | Median cost | First-query time | Conflicts | Decisions | Propagations | Restarts |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    summary: dict[tuple[str, str], dict[str, float]] = {}
    for variant in variants:
        for mode in modes:
            subset = grouped.get((variant, mode), [])
            costs = [float(row["wall_seconds"]) if row["status"] in VALID else args.penalty for row in subset]
            record = {
                "solved": float(sum(row["status"] in VALID for row in subset)),
                "cost": median(costs),
            }
            for field in ("query_elapsed", "query_conflicts", "query_decisions", "query_propagations", "query_restarts"):
                record[field] = median([
                    float(row[field]) for row in subset if row["status"] in VALID and row.get(field)
                ])
            summary[(variant, mode)] = record
            def fmt(value: float) -> str:
                return "" if math.isnan(value) else f"{value:.2f}"
            lines.append(
                f"| {variant} | {mode} | {int(record['solved'])}/{len(subset)} | "
                f"{fmt(record['cost'])} | {fmt(record['query_elapsed'])} | "
                f"{fmt(record['query_conflicts'])} | {fmt(record['query_decisions'])} | "
                f"{fmt(record['query_propagations'])} | {fmt(record['query_restarts'])} |"
            )

    def separation(left: str, right: str) -> tuple[float, int]:
        logs: list[float] = []
        mismatches = 0
        for variant in variants:
            a, b = summary[(variant, left)], summary[(variant, right)]
            if math.isnan(a["cost"]) or math.isnan(b["cost"]):
                continue
            logs.append(abs(math.log(max(a["cost"], 1e-6) / max(b["cost"], 1e-6))))
            if (a["solved"] > 0) != (b["solved"] > 0):
                mismatches += 1
        return median(logs), mismatches

    comparisons = []
    for left, right, label in (
        ("compact", "stable", "Compact/stable"),
        ("canonical_compact", "canonical_stable", "Canonical compact/stable"),
        ("raw_canonical_compact", "raw_canonical_stable", "No-eliminate canonical compact/stable"),
        ("precanonical_compact", "precanonical_stable", "Pre-eliminate canonical compact/stable"),
    ):
        if left in observed_modes and right in observed_modes:
            separation_value, mismatch = separation(left, right)
            comparisons.append((label, separation_value, mismatch))
    status_counts = {mode: Counter(row["status"] for row in rows if row["mode"] == mode) for mode in modes}
    lines.extend(["", "## Numbering Separation", ""])
    for label, separation_value, mismatch in comparisons:
        lines.append(
            f"- {label} median absolute log-ratio: {separation_value:.4f}; "
            f"solved-status mismatches: {mismatch}."
        )
    if len(comparisons) >= 2 and comparisons[0][1]:
        lines.append(f"- Second/first separation ratio: {comparisons[1][1] / comparisons[0][1]:.4f}.")
    lines.extend(["", "## Status Counts", ""])
    for mode in modes:
        lines.append(f"- {mode}: {dict(status_counts[mode])}")
    report = "\n".join(lines) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
