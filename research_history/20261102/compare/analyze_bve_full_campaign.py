#!/usr/bin/env python3
"""Analyze final AIG/XAG/BVE campaigns with paired, coverage-aware statistics."""

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}
MC_COMPARISONS = (
    ("xag_legacy4", "aig_legacy4", "XAG legacy vs AIG legacy"),
    ("xag_best4", "xag_legacy4", "XAG new BVE vs XAG legacy"),
    ("xag_best4", "aig_legacy4", "XAG new BVE vs AIG legacy"),
)
RIC3_COMPARISONS = (
    ("native_product_high4", "native_legacy4", "Native product-high vs Native legacy"),
    ("native_local4", "native_legacy4", "Native native-local vs Native legacy"),
    ("native_local4", "native_product_high4", "Native native-local vs product-high"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bootstrap", type=int, default=10000)
    return parser.parse_args()


def read_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: dict[tuple[str, str], dict[str, str]] = {}
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = (row.get("year", ""), row["name"])
                if key in rows:
                    raise ValueError(f"duplicate benchmark row {key} in {path}")
                rows[key] = row
    return list(rows.values())


def solved(row: dict[str, str], config: str) -> bool:
    return row.get(f"{config}_status") in VALID


def runtime(row: dict[str, str], config: str) -> float:
    return float(row[f"{config}_wall_seconds"])


def timeout(row: dict[str, str]) -> float:
    return float(row["timeout_seconds"])


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def bootstrap_geo_ci(
    ratios: list[float], families: list[str], iterations: int,
) -> tuple[float, float]:
    if not ratios:
        return math.nan, math.nan
    logs = [math.log(value) for value in ratios]
    rng = random.Random(20260805)
    estimates = []
    clusters: dict[str, list[float]] = defaultdict(list)
    for family, value in zip(families, logs):
        clusters[family].append(value)
    keys = list(clusters)
    for _ in range(iterations):
        sampled = [value for _ in keys for value in clusters[rng.choice(keys)]]
        estimates.append(math.exp(statistics.mean(sampled)))
    return percentile(estimates, 0.025), percentile(estimates, 0.975)


def pair_stats(
    rows: list[dict[str, str]], candidate: str, reference: str, bootstrap: int,
) -> dict[str, float | int]:
    common = [row for row in rows if solved(row, candidate) and solved(row, reference)]
    ratios = [runtime(row, candidate) / runtime(row, reference) for row in common]
    families = [row.get("family") or row.get("model_id") or row["name"] for row in common]
    informative = [row for row in rows if solved(row, candidate) or solved(row, reference)]
    penalty = lambda row, config: (
        runtime(row, config) if solved(row, config) else 1.5 * timeout(row)
    )
    cand_cost = sum(penalty(row, candidate) for row in informative)
    ref_cost = sum(penalty(row, reference) for row in informative)
    ci_low, ci_high = bootstrap_geo_ci(ratios, families, bootstrap)
    return {
        "models": len(rows),
        "candidate_solved": sum(solved(row, candidate) for row in rows),
        "reference_solved": sum(solved(row, reference) for row in rows),
        "only": sum(solved(row, candidate) and not solved(row, reference) for row in rows),
        "lost": sum(solved(row, reference) and not solved(row, candidate) for row in rows),
        "common": len(common),
        "informative": len(informative),
        "geo": math.exp(statistics.mean(math.log(value) for value in ratios)) if ratios else math.nan,
        "median": statistics.median(ratios) if ratios else math.nan,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "wins": sum(runtime(row, candidate) + 2.0 < runtime(row, reference) for row in common),
        "losses": sum(runtime(row, reference) + 2.0 < runtime(row, candidate) for row in common),
        "cand_cost": cand_cost,
        "ref_cost": ref_cost,
        "cost_ratio": cand_cost / ref_cost if ref_cost else math.nan,
    }


def fmt(value: float | int, digits: int = 3) -> str:
    if isinstance(value, int):
        return str(value)
    return "-" if math.isnan(value) else f"{value:.{digits}f}"


def mechanism_table(rows: list[dict[str, str]]) -> list[str]:
    fields = (
        ("translation_raw_vars", "Raw vars"),
        ("translation_raw_clauses", "Raw clauses"),
        ("translation_simplified_vars", "Simplified vars"),
        ("translation_simplified_clauses", "Simplified clauses"),
        ("translation_simplified_literals", "Simplified literals"),
        ("queries", "SAT queries"),
        ("pdr_depth", "PDR depth"),
    )
    if not rows or f"xag_best4_{fields[0][0]}" not in rows[0]:
        return []
    lines = [
        "## Mechanism observables", "",
        "Ratios are XAG new-BVE / reference on pairs where both values are positive.", "",
        "| Observable | vs XAG legacy median | vs AIG legacy median |",
        "|---|---:|---:|",
    ]
    for field, label in fields:
        values = []
        for reference in ("xag_legacy4", "aig_legacy4"):
            ratios = []
            for row in rows:
                try:
                    candidate_value = float(row[f"xag_best4_{field}"])
                    reference_value = float(row[f"{reference}_{field}"])
                except (KeyError, ValueError):
                    continue
                if candidate_value > 0 and reference_value > 0:
                    ratios.append(candidate_value / reference_value)
            values.append(statistics.median(ratios) if ratios else math.nan)
        lines.append(f"| {label} | {fmt(values[0])} | {fmt(values[1])} |")
    lines.append("")
    return lines


def main() -> int:
    args = parse_args()
    rows = read_rows(args.inputs)
    conflicts = sum(row.get("outcome_conflict") == "1" for row in rows)
    is_native = bool(rows and "native_legacy4_status" in rows[0])
    comparisons = RIC3_COMPARISONS if is_native else MC_COMPARISONS
    lines = [
        "# Full representation/BVE campaign", "",
        f"Models: {len(rows)}. Outcome conflicts: {conflicts}.", "",
        "Timeouts are charged at 1.5x the per-row limit. Pairs where both configurations "
        "are unsolved are excluded from penalized cost; runtime ratios use common solves only.", "",
        "| Comparison | Solved candidate/reference | Only/lost | Common | Geo ratio (95% family-cluster CI) | Median | W/L >2s | Informative PAR ratio |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for candidate, reference, label in comparisons:
        stats = pair_stats(rows, candidate, reference, args.bootstrap)
        lines.append(
            f"| {label} | {stats['candidate_solved']}/{stats['reference_solved']} | "
            f"{stats['only']}/{stats['lost']} | {stats['common']} | {fmt(stats['geo'])} "
            f"[{fmt(stats['ci_low'])}, {fmt(stats['ci_high'])}] | {fmt(stats['median'])} | "
            f"{stats['wins']}/{stats['losses']} | {fmt(stats['cost_ratio'])} "
            f"(n={stats['informative']}) |"
        )

    primary_pairs = (
        (("native_product_high4", "native_legacy4", "Native product-high vs Native legacy"),
         ("native_local4", "native_legacy4", "Native native-local vs Native legacy"))
        if is_native else
        (("xag_best4", "aig_legacy4", "XAG new-BVE vs AIG legacy"),)
    )
    by_year: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_year[row.get("year", "unknown")].append(row)
    by_tier: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_tier[row.get("group", "unknown")].append(row)
    for candidate, reference, label in primary_pairs:
        lines += ["", f"## {label} by year", "",
                  "| Year | Models | Solved candidate/reference | Only/lost | Common | Geo ratio | PAR ratio |",
                  "|---|---:|---:|---:|---:|---:|---:|"]
        for year in sorted(by_year):
            stats = pair_stats(by_year[year], candidate, reference, 1000)
            lines.append(
                f"| {year} | {stats['models']} | {stats['candidate_solved']}/{stats['reference_solved']} | "
                f"{stats['only']}/{stats['lost']} | {stats['common']} | {fmt(stats['geo'])} | "
                f"{fmt(stats['cost_ratio'])} |"
            )
        lines += ["", f"## {label} by historical tier", "",
                  "| Tier | Models | Solved candidate/reference | Only/lost | Common | Geo ratio | PAR ratio |",
                  "|---|---:|---:|---:|---:|---:|---:|"]
        for tier in sorted(by_tier):
            stats = pair_stats(by_tier[tier], candidate, reference, 1000)
            lines.append(
                f"| {tier} | {stats['models']} | {stats['candidate_solved']}/{stats['reference_solved']} | "
                f"{stats['only']}/{stats['lost']} | {stats['common']} | {fmt(stats['geo'])} | "
                f"{fmt(stats['cost_ratio'])} |"
            )
        lines.append("")
    lines += mechanism_table(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"rows={len(rows)} conflicts={conflicts} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
