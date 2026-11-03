#!/usr/bin/env python3
"""Build multiplicity-adjusted year and difficulty-tier intervals for BVE results."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Callable


VALID = {"SAFE", "UNSAFE"}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mc-inputs", nargs="+", required=True, type=Path)
    parser.add_argument("--ric3-inputs", nargs="+", required=True, type=Path)
    parser.add_argument("--ric3-selection", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bootstrap", type=int, default=20000)
    return parser.parse_args()


def read_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle, delimiter="\t"))
    return rows


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def interval(
    rows: list[dict[str, str]],
    candidate: str,
    reference: str,
    cluster: Callable[[dict[str, str]], str],
    comparisons: int,
    iterations: int,
    seed: int,
) -> tuple[int, int, int, float, float, float]:
    logs_by_cluster: dict[str, list[float]] = defaultdict(list)
    candidate_solved = 0
    reference_solved = 0
    for row in rows:
        candidate_ok = row[f"{candidate}_status"] in VALID
        reference_ok = row[f"{reference}_status"] in VALID
        candidate_solved += candidate_ok
        reference_solved += reference_ok
        if candidate_ok and reference_ok:
            logs_by_cluster[cluster(row)].append(
                math.log(
                    float(row[f"{candidate}_wall_seconds"])
                    / float(row[f"{reference}_wall_seconds"])
                )
            )

    keys = sorted(logs_by_cluster)
    cluster_stats = [
        (sum(logs_by_cluster[key]), len(logs_by_cluster[key])) for key in keys
    ]
    observed_sum = sum(total for total, _ in cluster_stats)
    observed_count = sum(count for _, count in cluster_stats)
    rng = random.Random(seed)
    estimates = []
    for _ in range(iterations):
        sampled = [cluster_stats[rng.randrange(len(cluster_stats))] for _ in keys]
        sample_sum = sum(total for total, _ in sampled)
        sample_count = sum(count for _, count in sampled)
        estimates.append(math.exp(sample_sum / sample_count))

    tail = 0.05 / comparisons / 2.0
    return (
        candidate_solved,
        reference_solved,
        observed_count,
        math.exp(observed_sum / observed_count),
        percentile(estimates, tail),
        percentile(estimates, 1.0 - tail),
    )


def add_table(
    lines: list[str],
    title: str,
    groups: list[tuple[str, list[dict[str, str]]]],
    candidate: str,
    reference: str,
    cluster: Callable[[dict[str, str]], str],
    iterations: int,
    seed: int,
) -> None:
    comparisons = len(groups)
    confidence = 100.0 * (1.0 - 0.05 / comparisons)
    lines += [
        "",
        f"## {title}",
        "",
        f"Each interval is a {confidence:.2f}% cluster-bootstrap interval, giving "
        "Bonferroni familywise 95% coverage across the table.",
        "",
        "| Group | Solved candidate/reference | Common | Geo ratio | Familywise interval |",
        "|---|---:|---:|---:|---:|",
    ]
    for index, (label, rows) in enumerate(groups):
        cand, ref, common, geo, low, high = interval(
            rows, candidate, reference, cluster, comparisons, iterations, seed + index
        )
        lines.append(
            f"| {label} | {cand}/{ref} | {common} | {geo:.3f} | "
            f"[{low:.3f}, {high:.3f}] |"
        )


def main() -> int:
    args = arguments()
    mc_rows = read_rows(args.mc_inputs)
    ric3_rows = read_rows(args.ric3_inputs)
    selection = json.loads(args.ric3_selection.read_text(encoding="utf-8"))
    metadata = {model["id"]: model for model in selection["models"]}
    years = (2015, 2017, 2019, 2020, 2024, 2025)
    tiers = ("trivial", "fast", "medium", "slow", "timeout")

    lines = [
        "# Multiplicity-adjusted BVE subgroup analysis",
        "",
        "Intervals resample MC family clusters and rIC3 model clusters with all seed "
        "observations retained. Geometric ratios use common solves only.",
    ]
    add_table(
        lines,
        "MC years",
        [
            (str(year), [row for row in mc_rows if row["model_id"].startswith(f"{year}__")])
            for year in years
        ],
        "xag_sumhigh4",
        "xag_legacy4",
        lambda row: row["family"],
        args.bootstrap,
        20260813,
    )
    add_table(
        lines,
        "rIC3 years",
        [
            (
                str(year),
                [row for row in ric3_rows if metadata[row["model_id"]]["year"] == year],
            )
            for year in years
        ],
        "ric3_product_sum_high",
        "ric3_legacy",
        lambda row: row["model_id"],
        args.bootstrap,
        20260831,
    )
    add_table(
        lines,
        "MC historical tiers",
        [(tier, [row for row in mc_rows if row["tier"] == tier]) for tier in tiers],
        "xag_sumhigh4",
        "xag_legacy4",
        lambda row: row["family"],
        args.bootstrap,
        20260913,
    )
    add_table(
        lines,
        "rIC3 historical tiers",
        [
            (
                tier,
                [row for row in ric3_rows if metadata[row["model_id"]]["tier"] == tier],
            )
            for tier in tiers
        ],
        "ric3_product_sum_high",
        "ric3_legacy",
        lambda row: row["model_id"],
        args.bootstrap,
        20260931,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
