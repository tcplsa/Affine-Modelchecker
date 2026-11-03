#!/usr/bin/env python3
"""Explain role-aware BVE using paired simplification and CDCL observables."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path


REFERENCE = "xag_observe_legacy4"
CANDIDATE = "xag_observe_role4"
VALID = {"SAFE", "UNSAFE"}

OBSERVABLES = (
    ("lift_bve_attempted", "Lift BVE attempts"),
    ("lift_bve_eliminated", "Lift variables eliminated"),
    ("lift_bve_rejected_growth", "Lift growth rejections"),
    ("lift_bve_rejected_clause_limit", "Lift clause-limit rejections"),
    ("lift_bve_removed_clauses", "Lift clauses removed"),
    ("lift_bve_resolvents", "Lift resolvents"),
    ("lift_bve_resolvent_literals", "Lift resolvent literals"),
    ("lift_bve_merge_checks", "Lift merge checks"),
    ("lift_simplified_clauses", "Lift output clauses"),
    ("lift_simplified_literals", "Lift output literals"),
    ("lift_binary_clauses", "Lift binary clauses"),
    ("lift_ternary_clauses", "Lift ternary clauses"),
    ("lift_long_clauses", "Lift long clauses"),
    ("lift_sat_conflicts", "Lift CDCL conflicts"),
    ("lift_sat_decisions", "Lift CDCL decisions"),
    ("lift_sat_propagations", "Lift CDCL propagations"),
    ("frame_sat_conflicts", "Frame CDCL conflicts"),
    ("frame_sat_decisions", "Frame CDCL decisions"),
    ("frame_sat_propagations", "Frame CDCL propagations"),
    ("queries", "PDR SAT queries"),
    ("cti", "CTIs"),
    ("mic", "MIC attempts"),
    ("pdr_depth", "PDR depth"),
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def number(row: dict[str, str], config: str, field: str) -> float | None:
    value = row.get(f"{config}_{field}", "")
    try:
        return float(value)
    except ValueError:
        return None


def solved(row: dict[str, str], config: str) -> bool:
    return row.get(f"{config}_status") in VALID


def geo(values: list[float]) -> float:
    positive = [value for value in values if value > 0 and math.isfinite(value)]
    return math.exp(statistics.mean(map(math.log, positive))) if positive else math.nan


def fmt(value: float) -> str:
    return "-" if math.isnan(value) else f"{value:.3f}"


def pearson(left: list[float], right: list[float]) -> float:
    if len(left) < 3 or len(left) != len(right):
        return math.nan
    left_mean = statistics.mean(left)
    right_mean = statistics.mean(right)
    numerator = sum(
        (x - left_mean) * (y - right_mean) for x, y in zip(left, right)
    )
    left_var = sum((x - left_mean) ** 2 for x in left)
    right_var = sum((y - right_mean) ** 2 for y in right)
    denominator = math.sqrt(left_var * right_var)
    return numerator / denominator if denominator else math.nan


def field_ratio(row: dict[str, str], field: str) -> float | None:
    left = number(row, CANDIDATE, field)
    right = number(row, REFERENCE, field)
    if left is None or right is None or left <= 0 or right <= 0:
        return None
    return left / right


def main() -> int:
    args = arguments()
    with args.input.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    candidate_solved = sum(solved(row, CANDIDATE) for row in rows)
    reference_solved = sum(solved(row, REFERENCE) for row in rows)
    candidate_only = [row for row in rows if solved(row, CANDIDATE) and not solved(row, REFERENCE)]
    reference_only = [row for row in rows if solved(row, REFERENCE) and not solved(row, CANDIDATE)]
    common = [row for row in rows if solved(row, CANDIDATE) and solved(row, REFERENCE)]
    runtime_ratios = []
    for row in common:
        left = number(row, CANDIDATE, "wall_seconds")
        right = number(row, REFERENCE, "wall_seconds")
        if left is not None and right is not None and right > 0:
            runtime_ratios.append(left / right)

    lines = [
        "# Role-aware BVE observables", "",
        f"Completed models: {len(rows)}.", "",
        f"Solved role/legacy: {candidate_solved}/{reference_solved}; "
        f"only/lost: {len(candidate_only)}/{len(reference_only)}; common: {len(common)}.",
        f"Common-solve runtime geo ratio: {fmt(geo(runtime_ratios))}.", "",
        "Ratios below are role-aware / legacy on paired rows with positive values. "
        "Values below 1 mean the role-aware configuration performs less work.", "",
        "| Observable | All paired geo | Common-solve geo | Median common |",
        "|---|---:|---:|---:|",
    ]
    for field, label in OBSERVABLES:
        all_ratios = []
        common_ratios = []
        for row in rows:
            left = number(row, CANDIDATE, field)
            right = number(row, REFERENCE, field)
            if left is None or right is None or left <= 0 or right <= 0:
                continue
            observed_ratio = left / right
            all_ratios.append(observed_ratio)
            if row in common:
                common_ratios.append(observed_ratio)
        median = statistics.median(common_ratios) if common_ratios else math.nan
        lines.append(
            f"| {label} | {fmt(geo(all_ratios))} | "
            f"{fmt(geo(common_ratios))} | {fmt(median)} |"
        )

    lines += ["", "## Outcome-discordant models", ""]
    lines.append("Role-only: " + (", ".join(
        row.get("model_id", row["name"]) for row in candidate_only
    ) or "none"))
    lines.append("Legacy-only: " + (", ".join(
        row.get("model_id", row["name"]) for row in reference_only
    ) or "none"))

    lines += ["", "| Model | Outcome | Merge checks | Resolvent literals | Output literals | Lift conflicts | Frame conflicts |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for row in candidate_only + reference_only:
        outcome = "role-only" if row in candidate_only else "legacy-only"
        values = [
            field_ratio(row, field) for field in (
                "lift_bve_merge_checks", "lift_bve_resolvent_literals",
                "lift_simplified_literals", "lift_sat_conflicts",
                "frame_sat_conflicts",
            )
        ]
        lines.append(
            f"| {row.get('model_id', row['name'])} | {outcome} | "
            + " | ".join(fmt(value) if value is not None else "-" for value in values)
            + " |"
        )

    runtime_logs = []
    usable_common = []
    for row in common:
        value = field_ratio(row, "wall_seconds")
        if value is None:
            continue
        runtime_logs.append(math.log(value))
        usable_common.append(row)
    correlations = []
    for field, label in OBSERVABLES:
        feature_logs = []
        paired_runtime_logs = []
        for row, runtime_log in zip(usable_common, runtime_logs):
            value = field_ratio(row, field)
            if value is None:
                continue
            feature_logs.append(math.log(value))
            paired_runtime_logs.append(runtime_log)
        correlation = pearson(feature_logs, paired_runtime_logs)
        if not math.isnan(correlation):
            correlations.append((abs(correlation), correlation, len(feature_logs), label))
    lines += ["", "## Runtime-ratio correlations", "",
              "Pearson correlation between paired log observable ratios and paired log runtime ratios. "
              "This is diagnostic, not a causal or predictive guarantee.", "",
              "| Observable | Correlation | Pairs |", "|---|---:|---:|"]
    for _magnitude, correlation, count, label in sorted(correlations, reverse=True)[:12]:
        lines.append(f"| {label} | {correlation:.3f} | {count} |")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows={len(rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
