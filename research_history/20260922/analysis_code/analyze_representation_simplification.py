#!/usr/bin/env python3
"""Analyze cross-year representation and MiniSat preprocessing experiments."""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}
REPRESENTATIONS = ("aig", "xag", "lowered")
REGIMES = ("native", "raw", "precanonical")


def read_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows = []
    for path in paths:
        with path.open(encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle, delimiter="\t"))
    return rows


def cost(row: dict[str, str], factor: float) -> float:
    if row["status"] in SOLVED:
        return float(row["wall_seconds"])
    return factor * float(row["timeout_seconds"])


def summarize_group(rows: list[dict[str, str]], configs: list[str], penalty: float) -> dict[str, object]:
    by_case: dict[tuple[str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        if row["config"] in configs:
            by_case[(row["model_id"], row["run"])][row["config"]] = row
    complete = [case for case in by_case.values() if all(config in case for config in configs)]
    eligible = [case for case in complete if any(case[c]["status"] in SOLVED for c in configs)]
    totals = {config: sum(cost(case[config], penalty) for case in eligible) for config in configs}
    solved = {config: sum(case[config]["status"] in SOLVED for case in complete) for config in configs}
    wins = Counter()
    meaningful = Counter()
    for case in eligible:
        values = {config: cost(case[config], penalty) for config in configs}
        winner = min(values, key=values.get)
        wins[winner] += 1
        if max(values.values()) - min(values.values()) > 2.0:
            meaningful[winner] += 1
    best = min(totals, key=totals.get) if totals else ""
    speedups = {
        config: (totals[config] / totals[best] - 1.0) if totals and totals[best] else math.nan
        for config in configs if config != best
    }
    return {
        "complete": len(complete), "eligible": len(eligible), "totals": totals,
        "solved": solved, "wins": wins, "meaningful": meaningful,
        "best": best, "speedups": speedups,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout-penalty", type=float, default=1.5)
    args = parser.parse_args()
    rows = read_rows(args.inputs)
    conflicts = 0
    outcomes: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        if row["status"] in SOLVED:
            outcomes[(row["model_id"], row["run"])].add(row["status"])
    conflicts = sum(len(values) > 1 for values in outcomes.values())

    lines = [
        "# Representation / Simplification Report", "",
        f"Rows: {len(rows)}; solved-outcome conflicts: {conflicts}; "
        f"timeout penalty: {args.timeout_penalty:.2f}x.", "",
        "All tables exclude cases where every compared configuration timed out or errored. "
        "Meaningful wins additionally require a fastest/slowest gap above 2 seconds.", "",
    ]

    def emit(title: str, result: dict[str, object]) -> None:
        lines.extend([f"## {title}", ""])
        lines.append(
            f"Complete pairs: {result['complete']}; retained cases: {result['eligible']}; "
            f"best penalized total: {result['best']}."
        )
        lines.extend(["", "| Config | Solved | Penalized seconds | Wins | Wins >2s | Gap vs best |", "|---|---:|---:|---:|---:|---:|"])
        totals = result["totals"]
        for config in totals:
            gap = "best" if config == result["best"] else f"{100.0 * result['speedups'][config]:.1f}%"
            lines.append(
                f"| {config} | {result['solved'][config]}/{result['complete']} | "
                f"{totals[config]:.2f} | {result['wins'][config]} | "
                f"{result['meaningful'][config]} | {gap} |"
            )
        lines.append("")

    for regime in REGIMES:
        configs = [f"{representation}_{regime}" for representation in REPRESENTATIONS]
        emit(f"Representations under {regime}", summarize_group(rows, configs, args.timeout_penalty))
    for representation in REPRESENTATIONS:
        configs = [f"{representation}_{regime}" for regime in REGIMES]
        emit(f"Preprocessing for {representation}", summarize_group(rows, configs, args.timeout_penalty))

    lines.extend(["## Status Counts", ""])
    for config in sorted({row["config"] for row in rows}):
        lines.append(f"- {config}: {dict(Counter(row['status'] for row in rows if row['config'] == config))}")
    report = "\n".join(lines) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
