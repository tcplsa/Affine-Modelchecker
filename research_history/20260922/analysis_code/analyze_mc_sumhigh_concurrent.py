#!/usr/bin/env python3
"""Analyze multi-seed concurrent MC sum-high confirmation."""

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

from analyze_bve_full_campaign import pair_stats


CANDIDATE = "xag_sumhigh4"
REFERENCE = "xag_legacy4"
VALID = {"SAFE", "UNSAFE"}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bootstrap", type=int, default=10000)
    return parser.parse_args()


def read_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = (row["model_id"], row["seed_block"])
                if key in seen:
                    raise ValueError(f"duplicate observation {key}")
                seen.add(key)
                rows.append(row)
    return rows


def fmt(value: float | int, digits: int = 3) -> str:
    if isinstance(value, int):
        return str(value)
    return "-" if math.isnan(value) else f"{value:.{digits}f}"


def add_table(
    lines: list[str], title: str, groups: list[tuple[str, list[dict[str, str]]]],
    bootstrap: int,
) -> None:
    lines += [
        "", f"## {title}", "",
        "| Group | Observations | Solved sum-high/legacy | Only/lost | Common | "
        "Geo (cluster 95% CI) | Median | W/L >2s | PAR-1.5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, rows in groups:
        stats = pair_stats(rows, CANDIDATE, REFERENCE, bootstrap)
        lines.append(
            f"| {label} | {len(rows)} | {stats['candidate_solved']}/{stats['reference_solved']} | "
            f"{stats['only']}/{stats['lost']} | {stats['common']} | {fmt(stats['geo'])} "
            f"[{fmt(stats['ci_low'])}, {fmt(stats['ci_high'])}] | {fmt(stats['median'])} | "
            f"{stats['wins']}/{stats['losses']} | {fmt(stats['cost_ratio'])} |"
        )


def counter_ratios(
    rows: list[dict[str, str]], numerator: str, denominator: str | None = None,
) -> list[tuple[float, str]]:
    ratios: list[tuple[float, str]] = []
    for row in rows:
        try:
            candidate = float(row[f"{CANDIDATE}_{numerator}"])
            reference = float(row[f"{REFERENCE}_{numerator}"])
            if denominator is not None:
                candidate /= float(row[f"{CANDIDATE}_{denominator}"])
                reference /= float(row[f"{REFERENCE}_{denominator}"])
        except (KeyError, ValueError, ZeroDivisionError):
            continue
        if candidate > 0 and reference > 0:
            ratios.append((candidate / reference, row["family"]))
    return ratios


def cluster_geo_interval(
    ratios: list[tuple[float, str]], iterations: int, seed: int,
) -> tuple[float, float]:
    by_family: dict[str, list[float]] = defaultdict(list)
    for ratio, family in ratios:
        by_family[family].append(math.log(ratio))
    families = sorted(by_family)
    if not families:
        return math.nan, math.nan
    rng = random.Random(seed)
    family_stats = [
        (sum(by_family[family]), len(by_family[family])) for family in families
    ]
    samples = []
    for _ in range(iterations):
        selected = [family_stats[rng.randrange(len(family_stats))] for _ in families]
        total = sum(value for value, _ in selected)
        count = sum(count for _, count in selected)
        samples.append(math.exp(total / count))
    samples.sort()
    return (
        samples[int(0.025 * (len(samples) - 1))],
        samples[int(0.975 * (len(samples) - 1))],
    )


def summed_counter_ratio(rows: list[dict[str, str]], field: str) -> float:
    candidate = 0.0
    reference = 0.0
    for row in rows:
        try:
            candidate += float(row[f"{CANDIDATE}_{field}"])
            reference += float(row[f"{REFERENCE}_{field}"])
        except (KeyError, ValueError):
            continue
    return candidate / reference if reference > 0 else math.nan


def add_counter_table(
    lines: list[str], title: str, rows: list[dict[str, str]],
    fields: tuple[tuple[str, str], ...], bootstrap: int, seed: int,
) -> None:
    lines += [
        "", f"### {title}", "",
        "Ratios use observations solved by both configurations. The geometric ratio "
        "uses pairs in which both counters are positive; the summed ratio retains zero "
        "counts and is tail-sensitive.", "",
        "| Observable | Positive pairs | Geo ratio (95% family-cluster CI) | Median | Summed-count ratio |",
        "|---|---:|---:|---:|---:|",
    ]
    for index, (field, label) in enumerate(fields):
        ratios = counter_ratios(rows, field)
        values = [value for value, _ in ratios]
        if not values:
            continue
        low, high = cluster_geo_interval(ratios, bootstrap, seed + index)
        lines.append(
            f"| {label} | {len(values)} | {fmt(math.exp(statistics.mean(map(math.log, values))))} "
            f"[{fmt(low)}, {fmt(high)}] | {fmt(statistics.median(values))} | "
            f"{fmt(summed_counter_ratio(rows, field))} |"
        )


def add_normalized_table(
    lines: list[str], title: str, rows: list[dict[str, str]],
    fields: tuple[tuple[str, str, str], ...], bootstrap: int, seed: int,
) -> None:
    lines += [
        "", f"### {title}", "",
        "| Normalized observable | Positive pairs | Geo ratio (95% family-cluster CI) | Median |",
        "|---|---:|---:|---:|",
    ]
    for index, (numerator, denominator, label) in enumerate(fields):
        ratios = counter_ratios(rows, numerator, denominator)
        values = [value for value, _ in ratios]
        if not values:
            continue
        low, high = cluster_geo_interval(ratios, bootstrap, seed + index)
        lines.append(
            f"| {label} | {len(values)} | {fmt(math.exp(statistics.mean(map(math.log, values))))} "
            f"[{fmt(low)}, {fmt(high)}] | {fmt(statistics.median(values))} |"
        )


def main() -> int:
    args = arguments()
    rows = read_rows(args.inputs)
    if not rows:
        raise ValueError("no result rows")
    lines = [
        "# MC XAG product-sum-high concurrent confirmation", "",
        f"Observations: {len(rows)}; models: {len({row['model_id'] for row in rows})}; "
        f"seed blocks: {len({row['seed_block'] for row in rows})}; outcome conflicts: "
        f"{sum(row['outcome_conflict'] == '1' for row in rows)}.", "",
        "MC calls the candidate `sum-high`; it orders BVE pivots by "
        "`(positive*negative, positive+negative, -variable_id)`, the same "
        "fill-aware product-sum-high principle transferred to rIC3. Both configurations "
        "use four forward-XAG lanes with matched explicit seeds and are launched "
        "concurrently within each model.",
    ]
    add_table(lines, "Aggregate", [("all", rows)], args.bootstrap)

    seeds = sorted({row["seed_block"] for row in rows})
    add_table(
        lines, "By seed block",
        [(seed, [row for row in rows if row["seed_block"] == seed]) for seed in seeds],
        min(args.bootstrap, 3000),
    )
    years = sorted({row["model_id"].split("__", 1)[0] for row in rows})
    add_table(
        lines, "By year",
        [(year, [row for row in rows if row["model_id"].startswith(f"{year}__")]) for year in years],
        min(args.bootstrap, 3000),
    )
    tiers = ("trivial", "fast", "medium", "slow", "timeout")
    add_table(
        lines, "By historical tier",
        [(tier, [row for row in rows if row["tier"] == tier]) for tier in tiers],
        min(args.bootstrap, 3000),
    )
    add_table(
        lines, "By outcome",
        [(outcome, [row for row in rows if row["outcome"] == outcome]) for outcome in ("SAFE", "UNSAFE")],
        min(args.bootstrap, 3000),
    )

    fields = (
        ("translation_simplified_vars", "Simplified variables"),
        ("translation_simplified_clauses", "Simplified clauses"),
        ("translation_simplified_literals", "Simplified literals"),
        ("queries", "SAT queries"),
        ("cti", "CTIs"),
        ("mic", "MIC calls"),
        ("generalize", "Generalize calls"),
        ("push", "Push calls"),
        ("pdr_depth", "PDR depth"),
        ("lemma_added", "Unique lemmas added"),
        ("block_lemma_added", "Block lemmas added"),
        ("push_lemma_added", "Push lemmas added"),
        ("frame_core", "Frame UNSAT cores"),
        ("lift_core", "Lift UNSAT cores"),
    )
    lines += ["", "## Outcome-stratified PDR observables"]
    common_by_outcome = {
        outcome: [
            row for row in rows
            if row["outcome"] == outcome
            and row[f"{CANDIDATE}_status"] in VALID
            and row[f"{REFERENCE}_status"] in VALID
        ]
        for outcome in ("SAFE", "UNSAFE")
    }
    pdr_fields = tuple(item for item in fields if item[0] in {
        "queries", "cti", "mic", "generalize", "push", "pdr_depth",
        "lemma_added", "block_lemma_added", "push_lemma_added",
        "frame_core", "lift_core",
    })
    normalized_fields = (
        ("cti", "queries", "CTIs / query"),
        ("mic", "queries", "MIC calls / query"),
        ("generalize", "queries", "Generalize calls / query"),
        ("push", "queries", "Push calls / query"),
        ("queries", "pdr_depth", "Queries / PDR depth"),
        ("push", "pdr_depth", "Push calls / PDR depth"),
        ("lemma_literals", "lemma_added", "Literals / unique lemma"),
        ("block_lemma_literals", "block_lemma_added", "Literals / block lemma"),
        ("push_lemma_literals", "push_lemma_added", "Literals / push lemma"),
        ("frame_core_input_literals", "frame_core", "Input literals / frame core"),
        ("frame_core_literals", "frame_core", "Output literals / frame core"),
        ("frame_core_literals", "frame_core_input_literals", "Frame-core retention fraction"),
        ("lift_core_input_literals", "lift_core", "Input literals / lift core"),
        ("lift_core_literals", "lift_core", "Output literals / lift core"),
        ("lift_core_literals", "lift_core_input_literals", "Lift-core retention fraction"),
    )
    for outcome_index, outcome in enumerate(("SAFE", "UNSAFE")):
        outcome_rows = common_by_outcome[outcome]
        add_counter_table(
            lines, f"{outcome} raw counters ({len(outcome_rows)} common solves)",
            outcome_rows, pdr_fields, min(args.bootstrap, 5000), 7100 + outcome_index * 100,
        )
        add_normalized_table(
            lines, f"{outcome} normalized counters", outcome_rows,
            normalized_fields, min(args.bootstrap, 5000), 8100 + outcome_index * 100,
        )

    differences = [
        row for row in rows
        if (row[f"{CANDIDATE}_status"] in VALID) != (row[f"{REFERENCE}_status"] in VALID)
    ]
    lines += ["", "## Coverage differences", "", "| Model | Seed | Tier | Outcome | Sum-high | Legacy |", "|---|---:|---|---|---:|---:|"]
    for row in differences:
        def result(config: str) -> str:
            if row[f"{config}_status"] in VALID:
                return f"{float(row[f'{config}_wall_seconds']):.3f}s"
            return row[f"{config}_status"]
        lines.append(
            f"| {row['model_id']} | {row['seed_block']} | {row['tier']} | "
            f"{row['outcome']} | {result(CANDIDATE)} | {result(REFERENCE)} |"
        )
    if not differences:
        lines.append("| None | - | - | - | - | - |")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows={len(rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
