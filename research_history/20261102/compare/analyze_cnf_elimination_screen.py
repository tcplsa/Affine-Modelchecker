#!/usr/bin/env python3
"""Analyze CNF elimination screening results against per-representation MiniSat baselines."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path

from run_cnf_elimination_screen import ORDER_TREATMENTS, TREATMENTS


VALID = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--treatment-set", choices=("broad", "order"), default="broad")
    return parser.parse_args()


def number(row: dict[str, str], key: str) -> float | None:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return None


def geometric_mean(values: list[float]) -> float | None:
    positive = [value for value in values if value > 0]
    if not positive:
        return None
    return math.exp(sum(math.log(value) for value in positive) / len(positive))


def formatted(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def main() -> int:
    args = parse_args()
    with args.input.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    treatments = TREATMENTS if args.treatment_set == "broad" else ORDER_TREATMENTS
    lines = [
        "# CNF elimination screen", "",
        f"Models: {len(rows)}. A ratio below 1.0 favors the treatment.", "",
    ]
    for representation in ("aig", "xag"):
        baseline_id = "min_default" if args.treatment_set == "broad" else "order_legacy"
        baseline = f"{representation}_{baseline_id}"
        if not rows or f"{baseline}_status" not in rows[0]:
            continue
        lines += [
            f"## {representation.upper()}", "",
            "| Treatment | Solved | Only | Lost | Penalized cost | Common | "
            "Runtime geo | Runtime median | Wins >1s | Losses >1s | Query median | "
            "Clause median | Literal median | Depth median |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for ident, label, _overrides in treatments:
            config = f"{representation}_{ident}"
            solved = lambda row, prefix: row.get(f"{prefix}_status") in VALID
            common = [row for row in rows if solved(row, config) and solved(row, baseline)]
            only = sum(solved(row, config) and not solved(row, baseline) for row in rows)
            lost = sum(solved(row, baseline) and not solved(row, config) for row in rows)
            timeout = lambda row: float(row.get("timeout_seconds") or 0.0)
            cost = sum(
                float(row[f"{config}_wall_seconds"])
                if solved(row, config) else 1.5 * timeout(row)
                for row in rows
            )
            runtime_ratios: list[float] = []
            ratios: dict[str, list[float]] = {
                "queries": [], "clauses": [], "literals": [], "depth": [],
            }
            wins = losses = 0
            for row in common:
                candidate_time = float(row[f"{config}_wall_seconds"])
                baseline_time = float(row[f"{baseline}_wall_seconds"])
                if baseline_time > 0:
                    runtime_ratios.append(candidate_time / baseline_time)
                wins += candidate_time + 1.0 < baseline_time
                losses += baseline_time + 1.0 < candidate_time
                fields = {
                    "queries": "queries",
                    "clauses": "translation_simplified_clauses",
                    "literals": "translation_simplified_literals",
                    "depth": "pdr_depth",
                }
                for key, field in fields.items():
                    candidate = number(row, f"{config}_{field}")
                    reference = number(row, f"{baseline}_{field}")
                    if candidate is not None and reference is not None and reference > 0:
                        ratios[key].append(candidate / reference)
            med = lambda values: statistics.median(values) if values else None
            lines.append(
                f"| {label} | {sum(solved(row, config) for row in rows)} | {only} | {lost} | "
                f"{cost:.1f} | {len(common)} | {formatted(geometric_mean(runtime_ratios))} | "
                f"{formatted(med(runtime_ratios))} | {wins} | {losses} | "
                f"{formatted(med(ratios['queries']))} | {formatted(med(ratios['clauses']))} | "
                f"{formatted(med(ratios['literals']))} | {formatted(med(ratios['depth']))} |"
            )
        lines.append("")

    conflicts = sum(row.get("outcome_conflict") == "1" for row in rows)
    lines += [f"Outcome conflicts: {conflicts}.", ""]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"rows={len(rows)} conflicts={conflicts} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
