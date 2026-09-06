#!/usr/bin/env python3
"""Cluster-bootstrap selector ratios over frozen structure groups."""

from __future__ import annotations

import argparse
import csv
import math
import random
from collections import defaultdict
from pathlib import Path


def number(row: dict[str, str], key: str) -> float:
    return float(row.get(key, "") or 0.0)


def solved(row: dict[str, str], config: str) -> bool:
    return row.get(f"{config}_status") in {"SAFE", "UNSAFE"}


def choose(row: dict[str, str], support: int, coverage: float, controls: int) -> str:
    total = number(row, "cadical_affine_next_total")
    count = number(row, "cadical_affine_next_count")
    rank = number(row, "cadical_affine_rank")
    avg = number(row, "cadical_affine_support_avg")
    if total > 0 and count == total and rank == total:
        return "cadical_hints" if avg <= support else "gauss_global"
    guarded = f"gauss_guard{controls}"
    guarded_count = number(row, f"{guarded}_affine_guarded_next_count")
    guarded_total = number(row, f"{guarded}_affine_next_total") or total
    if guarded_total and guarded_count / guarded_total >= coverage:
        return guarded
    return "cadical"


def log_ratios(rows: list[dict[str, str]], policy: tuple[int, float, int]) -> list[float]:
    values = []
    for row in rows:
        config = choose(row, *policy)
        if solved(row, config) and solved(row, "cadical"):
            candidate = number(row, f"{config}_wall_seconds")
            baseline = number(row, "cadical_wall_seconds")
            if candidate > 0 and baseline > 0:
                values.append(math.log(candidate / baseline))
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--split", default="holdout")
    parser.add_argument("--support", type=int, default=32)
    parser.add_argument("--coverage", type=float, default=0.75)
    parser.add_argument("--controls", type=int, default=2)
    parser.add_argument("--samples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260825)
    args = parser.parse_args()

    with args.input.open(newline="", encoding="utf-8") as stream:
        rows = [
            row for row in csv.DictReader(stream, delimiter="\t")
            if row["split"] == args.split
        ]
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row["structure_group"]].append(row)

    policy = (args.support, args.coverage, args.controls)
    observed = log_ratios(rows, policy)
    if not observed:
        raise SystemExit("no commonly solved observations")
    names = sorted(groups)
    rng = random.Random(args.seed)
    replicates = []
    for _ in range(args.samples):
        sampled_rows = []
        for _ in names:
            sampled_rows.extend(groups[rng.choice(names)])
        values = log_ratios(sampled_rows, policy)
        if values:
            replicates.append(sum(values) / len(values))
    replicates.sort()
    low = replicates[int(0.025 * len(replicates))]
    high = replicates[int(0.975 * len(replicates))]
    print(f"split={args.split}")
    print(f"models={len(rows)}")
    print(f"structure_groups={len(names)}")
    print(f"common_solves={len(observed)}")
    print(f"policy={args.support}/{args.coverage:.2f}/{args.controls}")
    print(f"gmean_ratio={math.exp(sum(observed) / len(observed)):.6f}")
    print(f"group_bootstrap_95ci=[{math.exp(low):.6f}, {math.exp(high):.6f}]")
    print(f"bootstrap_samples={len(replicates)}")
    print(f"bootstrap_seed={args.seed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
