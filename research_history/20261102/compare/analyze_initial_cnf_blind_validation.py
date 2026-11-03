#!/usr/bin/env python3
"""Analyze the held-out initial-CNF/input-order validation campaign."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}
SOURCE_CONFIG = {
    "results.tsv": None,
    "results_original.tsv": None,
    "results_bad-last.tsv": "xag_native_bad-last",
    "results_fanout-desc.tsv": "xag_precanonical_fanout-desc",
    "results_precanonical_original.tsv": "xag_precanonical_original",
    "results_canonical_components.tsv": None,
}


def read_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        if path.name not in SOURCE_CONFIG:
            raise ValueError(f"unknown validation result file: {path}")
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                row["_validation_config"] = SOURCE_CONFIG[path.name] or row["config"]
                rows.append(row)
    return rows


def cost(row: dict[str, str], penalty: float) -> float:
    return float(row["wall_seconds"]) if row["status"] in SOLVED else penalty * float(row["timeout_seconds"])


def reduction(reference: float, candidate: float) -> float:
    return 100.0 * (reference - candidate) / reference if reference else math.nan


def pair_summary(
    cases: list[dict[str, dict[str, str]]], reference: str, candidate: str, penalty: float
) -> dict[str, object]:
    complete = [case for case in cases if reference in case and candidate in case]
    eligible = [case for case in complete if case[reference]["status"] in SOLVED or case[candidate]["status"] in SOLVED]
    jointly = [case for case in complete if case[reference]["status"] in SOLVED and case[candidate]["status"] in SOLVED]
    reference_only = sum(case[reference]["status"] in SOLVED and case[candidate]["status"] not in SOLVED for case in complete)
    candidate_only = sum(case[candidate]["status"] in SOLVED and case[reference]["status"] not in SOLVED for case in complete)
    ref_total = sum(cost(case[reference], penalty) for case in eligible)
    cand_total = sum(cost(case[candidate], penalty) for case in eligible)
    ref_joint = sum(float(case[reference]["wall_seconds"]) for case in jointly)
    cand_joint = sum(float(case[candidate]["wall_seconds"]) for case in jointly)
    ref_wins = cand_wins = ref_meaningful = cand_meaningful = 0
    ratios = []
    for case in eligible:
        ref_cost = cost(case[reference], penalty)
        cand_cost = cost(case[candidate], penalty)
        if cand_cost < ref_cost:
            cand_wins += 1
            cand_meaningful += ref_cost - cand_cost > 2.0
        elif ref_cost < cand_cost:
            ref_wins += 1
            ref_meaningful += cand_cost - ref_cost > 2.0
    for case in jointly:
        ref_time = float(case[reference]["wall_seconds"])
        cand_time = float(case[candidate]["wall_seconds"])
        if ref_time > 0 and cand_time > 0:
            ratios.append(ref_time / cand_time)
    return {
        "complete": len(complete), "eligible": len(eligible), "jointly": len(jointly),
        "reference_only": reference_only, "candidate_only": candidate_only,
        "ref_total": ref_total, "cand_total": cand_total,
        "ref_joint": ref_joint, "cand_joint": cand_joint,
        "ref_wins": ref_wins, "cand_wins": cand_wins,
        "ref_meaningful": ref_meaningful, "cand_meaningful": cand_meaningful,
        "median_ratio": statistics.median(ratios) if ratios else math.nan,
    }


def stable_models(
    indexed: dict[tuple[str, str], dict[str, dict[str, str]]],
    reference: str, candidate: str, penalty: float,
) -> tuple[int, int, int, int]:
    by_model: dict[str, dict[str, dict[str, dict[str, str]]]] = defaultdict(dict)
    for (model_id, run), case in indexed.items():
        by_model[model_id][run] = case
    informative = stable_win = stable_loss = mixed = 0
    for runs in by_model.values():
        if not all(run in runs and reference in runs[run] and candidate in runs[run] for run in ("1", "2")):
            continue
        rows = [runs[run][config] for run in ("1", "2") for config in (reference, candidate)]
        if not any(row["status"] in SOLVED for row in rows):
            continue
        informative += 1
        deltas = [cost(runs[run][reference], penalty) - cost(runs[run][candidate], penalty) for run in ("1", "2")]
        if all(delta > 2.0 for delta in deltas):
            stable_win += 1
        elif all(delta < -2.0 for delta in deltas):
            stable_loss += 1
        else:
            mixed += 1
    return informative, stable_win, stable_loss, mixed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout-penalty", type=float, default=1.5)
    args = parser.parse_args()
    rows = read_rows(args.inputs)
    configs = sorted({row["_validation_config"] for row in rows})
    indexed: dict[tuple[str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    duplicates = 0
    for row in rows:
        key = (row["model_id"], row["run"])
        config = row["_validation_config"]
        duplicates += config in indexed[key]
        indexed[key][config] = row
    complete = [case for case in indexed.values() if all(config in case for config in configs)]
    eligible = [case for case in complete if any(case[config]["status"] in SOLVED for config in configs)]
    conflicts = sum(
        len({case[config]["status"] for config in configs if case[config]["status"] in SOLVED}) > 1
        for case in complete
    )

    ranking = []
    for config in configs:
        solved = sum(case[config]["status"] in SOLVED for case in complete)
        total = sum(cost(case[config], args.timeout_penalty) for case in eligible)
        ranking.append((total, config, solved))
    ranking.sort()
    best_total = ranking[0][0]

    lines = [
        "# Initial CNF Blind Validation Report", "",
        f"Rows: {len(rows)}; configurations: {len(configs)}; complete model/run cases: "
        f"{len(complete)}; retained non-all-timeout cases: {len(eligible)}; duplicate cells: "
        f"{duplicates}; outcome conflicts: {conflicts}; timeout penalty: {args.timeout_penalty:.2f}x.", "",
        "## Global Ranking", "",
        "| Rank | Configuration | Solved / complete | Penalized s | Gap vs best |",
        "|---:|---|---:|---:|---:|",
    ]
    for rank, (total, config, solved) in enumerate(ranking, 1):
        lines.append(
            f"| {rank} | {config} | {solved}/{len(complete)} | {total:.2f} | "
            f"{100.0 * (total / best_total - 1.0):+.2f}% |"
        )

    references = ["aig_native", "xag_native"]
    comparisons = [
        (reference, candidate)
        for candidate in configs for reference in references
        if candidate != reference and reference in configs
    ]
    interaction_pair = ("xag_precanonical_original", "xag_precanonical_fanout-desc")
    if all(config in configs for config in interaction_pair):
        comparisons.append(interaction_pair)
    component_pairs = (
        ("xag_canonical-minisat", "xag_canonical-cnf"),
        ("xag_precanonical_original", "xag_canonical-cnf"),
        ("xag_precanonical_original", "xag_canonical-minisat"),
    )
    comparisons.extend(
        pair for pair in component_pairs
        if all(config in configs for config in pair)
    )
    lines.extend([
        "", "## Pairwise Comparisons", "",
        "Positive reduction favors the candidate. The median ratio is reference/candidate on jointly solved cases.", "",
        "| Reference | Candidate | Retained | Joint | Ref/Cand only | Ref s | Cand s | Reduction | Joint reduction | Ref/Cand wins >2s | Median ratio |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for reference, candidate in comparisons:
        summary = pair_summary(complete, reference, candidate, args.timeout_penalty)
        lines.append(
            f"| {reference} | {candidate} | {summary['eligible']} | {summary['jointly']} | "
            f"{summary['reference_only']}/{summary['candidate_only']} | "
            f"{summary['ref_total']:.2f} | {summary['cand_total']:.2f} | "
            f"{reduction(summary['ref_total'], summary['cand_total']):+.2f}% | "
            f"{reduction(summary['ref_joint'], summary['cand_joint']):+.2f}% | "
            f"{summary['ref_meaningful']}/{summary['cand_meaningful']} | "
            f"{summary['median_ratio']:.3f} |"
        )

    lines.extend([
        "", "## Two-Repeat Stability", "",
        "A stable win/loss requires a gap above two seconds in the same direction in both four-lane repeats.", "",
        "| Reference | Candidate | Informative models | Stable candidate wins | Stable candidate losses | Mixed/small |",
        "|---|---|---:|---:|---:|---:|",
    ])
    for reference, candidate in comparisons:
        informative, wins, losses, mixed = stable_models(indexed, reference, candidate, args.timeout_penalty)
        lines.append(f"| {reference} | {candidate} | {informative} | {wins} | {losses} | {mixed} |")

    primary_pairs = [
        pair for pair in (
            ("aig_native", "aig_canonical-cnf"),
            ("xag_native", "xag_canonical-cnf"),
            ("aig_native", "xag_native"),
            ("aig_canonical-cnf", "xag_canonical-cnf"),
        )
        if all(config in configs for config in pair)
    ]
    for field, title in (("tier", "By Tier"), ("year", "By Year")):
        values = sorted({case[configs[0]][field] for case in complete})
        lines.extend([
            "", f"## {title}", "",
            "| Reference | Candidate | Group | Retained | Ref/Cand only | Penalized reduction | Joint reduction | Wins >2s |",
            "|---|---|---|---:|---:|---:|---:|---:|",
        ])
        for reference, candidate in primary_pairs:
            for value in values:
                subset = [case for case in complete if case[reference][field] == value]
                summary = pair_summary(subset, reference, candidate, args.timeout_penalty)
                if not summary["eligible"]:
                    continue
                lines.append(
                    f"| {reference} | {candidate} | {value} | {summary['eligible']} | "
                    f"{summary['reference_only']}/{summary['candidate_only']} | "
                    f"{reduction(summary['ref_total'], summary['cand_total']):+.2f}% | "
                    f"{reduction(summary['ref_joint'], summary['cand_joint']):+.2f}% | "
                    f"{summary['ref_meaningful']}/{summary['cand_meaningful']} |"
                )

    lines.extend(["", "## One-Sided Solves For Primary Pairs", ""])
    for reference, candidate in primary_pairs:
        one_sided = [
            case for case in complete
            if (case[reference]["status"] in SOLVED) != (case[candidate]["status"] in SOLVED)
        ]
        lines.append(f"### {reference} versus {candidate}")
        lines.append("")
        if not one_sided:
            lines.extend(["None.", ""])
            continue
        lines.extend([
            "| Model/run | Year | Tier | Reference | Candidate |",
            "|---|---:|---|---|---|",
        ])
        for case in one_sided:
            ref = case[reference]
            cand = case[candidate]
            lines.append(
                f"| {ref['model_id']} / {ref['run']} | {ref['year']} | {ref['tier']} | "
                f"{ref['status']} {float(ref['wall_seconds']):.2f}s | "
                f"{cand['status']} {float(cand['wall_seconds']):.2f}s |"
            )
        lines.append("")

    lines.extend(["", "## Status Counts", ""])
    for config in configs:
        lines.append(f"- {config}: {dict(Counter(row['status'] for row in rows if row['_validation_config'] == config))}")
    report = "\n".join(lines) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
