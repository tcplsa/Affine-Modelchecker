#!/usr/bin/env python3
"""Join hard-tail BVE candidates with the frozen full-campaign baselines."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}
BASELINES = ("aig_legacy4", "xag_legacy4", "xag_best4")
CANDIDATES = (
    "xag_translation_sum_lift_legacy4",
    "xag_translation_legacy_lift_sum4",
    "xag_split_order4",
    "xag_role3_legacy1",
    "aig1_xag_role3",
    "aig1_xag_role2_legacy1",
    "xag_role4_replica",
)
FOLLOWUP_CANDIDATES = {
    "xag_role3_legacy1",
    "aig1_xag_role3",
    "aig1_xag_role2_legacy1",
    "xag_role4_replica",
}
LABELS = {
    "aig_legacy4": "AIG legacy",
    "xag_legacy4": "XAG legacy/legacy",
    "xag_best4": "XAG sum-high/sum-high",
    "xag_translation_sum_lift_legacy4": "XAG sum-high/legacy",
    "xag_translation_legacy_lift_sum4": "XAG legacy/sum-high",
    "xag_split_order4": "XAG 2+2 order portfolio",
    "xag_role3_legacy1": "3 XAG role + 1 XAG legacy",
    "aig1_xag_role3": "1 AIG legacy + 3 XAG role",
    "aig1_xag_role2_legacy1": "1 AIG legacy + 2 XAG role + 1 XAG legacy",
    "xag_role4_replica": "XAG legacy/sum-high seed replica",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-inputs", nargs="+", required=True, type=Path)
    parser.add_argument("--candidate", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def read_rows(paths: list[Path]) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = row.get("model_id") or row["name"]
                if key in rows:
                    raise ValueError(f"duplicate model {key}")
                rows[key] = row
    return rows


def read_candidates(paths: list[Path]) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = row.get("model_id") or row["name"]
                merged = rows.setdefault(key, {})
                for field, value in row.items():
                    if field not in merged or any(
                        field.startswith(f"{config}_") for config in CANDIDATES
                    ):
                        merged[field] = value
    return rows


def solved(row: dict[str, str], config: str) -> bool:
    return row.get(f"{config}_status") in VALID


def runtime(row: dict[str, str], config: str) -> float:
    return float(row[f"{config}_wall_seconds"])


def pair_stats(
    rows: list[dict[str, str]], candidate: str, reference: str,
) -> dict[str, float | int]:
    common = [row for row in rows if solved(row, candidate) and solved(row, reference)]
    informative = [row for row in rows if solved(row, candidate) or solved(row, reference)]
    ratios = [runtime(row, candidate) / runtime(row, reference) for row in common]
    penalty = lambda row, config: (
        runtime(row, config) if solved(row, config)
        else 1.5 * float(row["timeout_seconds"])
    )
    candidate_cost = sum(penalty(row, candidate) for row in informative)
    reference_cost = sum(penalty(row, reference) for row in informative)
    query_ratios = []
    for row in common:
        try:
            left = float(row[f"{candidate}_queries"])
            right = float(row[f"{reference}_queries"])
        except (KeyError, ValueError):
            continue
        if left > 0 and right > 0:
            query_ratios.append(left / right)
    return {
        "candidate_solved": sum(solved(row, candidate) for row in rows),
        "reference_solved": sum(solved(row, reference) for row in rows),
        "only": sum(solved(row, candidate) and not solved(row, reference) for row in rows),
        "lost": sum(solved(row, reference) and not solved(row, candidate) for row in rows),
        "common": len(common),
        "geo": math.exp(statistics.mean(map(math.log, ratios))) if ratios else math.nan,
        "median": statistics.median(ratios) if ratios else math.nan,
        "wins": sum(runtime(row, candidate) + 2 < runtime(row, reference) for row in common),
        "losses": sum(runtime(row, reference) + 2 < runtime(row, candidate) for row in common),
        "par": candidate_cost / reference_cost if reference_cost else math.nan,
        "query_geo": (
            math.exp(statistics.mean(map(math.log, query_ratios)))
            if query_ratios else math.nan
        ),
    }


def fmt(value: float | int) -> str:
    return str(value) if isinstance(value, int) else (
        "-" if math.isnan(value) else f"{value:.3f}"
    )


def main() -> int:
    args = parse_args()
    baselines = read_rows(args.baseline_inputs)
    candidate_rows = read_candidates(args.candidate)
    rows: list[dict[str, str]] = []
    for model_id, candidate in candidate_rows.items():
        baseline = baselines.get(model_id)
        if baseline is None:
            continue
        merged = dict(baseline)
        for key, value in candidate.items():
            if key not in merged or any(key.startswith(f"{config}_") for config in CANDIDATES):
                merged[key] = value
        rows.append(merged)

    lines = [
        "# Hard-tail BVE specialization", "",
        f"Joined completed candidate rows: {len(rows)}.", "",
        "All entries use four PDR lanes and the same master seed. PAR-1.5 excludes "
        "pairs unsolved by both configurations.", "",
        "| Candidate vs reference | Solved | Only/lost | Common | Geo | Median | W/L >2s | Query geo | PAR |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for candidate in CANDIDATES:
        candidate_subset = [
            row for row in rows if f"{candidate}_status" in row
        ]
        if not candidate_subset:
            continue
        references = ["aig_legacy4", "xag_legacy4", "xag_best4"]
        role_reference = "xag_translation_legacy_lift_sum4"
        if candidate in FOLLOWUP_CANDIDATES and any(
            f"{role_reference}_status" in row for row in candidate_subset
        ):
            references.append(role_reference)
        for reference in references:
            stats = pair_stats(candidate_subset, candidate, reference)
            lines.append(
                f"| {LABELS[candidate]} vs {LABELS[reference]} | "
                f"{stats['candidate_solved']}/{stats['reference_solved']} | "
                f"{stats['only']}/{stats['lost']} | {stats['common']} | "
                f"{fmt(stats['geo'])} | {fmt(stats['median'])} | "
                f"{stats['wins']}/{stats['losses']} | {fmt(stats['query_geo'])} | "
                f"{fmt(stats['par'])} |"
            )

    all_configs = BASELINES + CANDIDATES
    present = [
        config for config in all_configs
        if any(f"{config}_status" in row for row in rows)
    ]
    lines += ["", "## Coverage", ""]
    coverage = []
    for config in present:
        available = [row for row in rows if f"{config}_status" in row]
        coverage.append((
            sum(solved(row, config) for row in available), config, len(available),
        ))
    for solved_count, config, available_count in sorted(
        coverage, key=lambda item: (-item[0], LABELS[item[1]]),
    ):
        lines.append(
            f"- {LABELS[config]}: {solved_count} solved (n={available_count})"
        )
    lines.append(
        f"- Union: {sum(any(solved(row, config) for config in present) for row in rows)} solved"
    )

    lines += ["", "## Candidate-only solves", ""]
    for candidate in CANDIDATES:
        if candidate not in present:
            continue
        unique = [
            row.get("model_id", row["name"]) for row in rows
            if solved(row, candidate)
            and not any(solved(row, baseline) for baseline in BASELINES)
        ]
        lines.append(f"- {LABELS[candidate]}: {', '.join(unique) if unique else 'none'}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"joined={len(rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
