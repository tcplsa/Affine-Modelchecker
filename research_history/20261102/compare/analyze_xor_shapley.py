#!/usr/bin/env python3
"""Compute exact bucket Shapley values and pair interactions."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable


SOLVED = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--results", required=True, nargs="+", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--timeout-multiplier", type=float, default=1.5)
    parser.add_argument("--min-effect", type=float, default=2.0)
    return parser.parse_args()


def write_tsv(path: Path, rows: Iterable[dict], header: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def main() -> int:
    args = parse_args()
    if args.timeout_multiplier < 1 or args.min_effect < 0:
        raise SystemExit("timeout multiplier must be >=1 and min effect non-negative")
    design = json.loads(args.manifest.read_text(encoding="utf-8"))
    model_spec = {model["name"]: model for model in design["models"]}

    raw: Dict[tuple[str, int, str], dict] = {}
    for path in args.results:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                raw[(row["name"], int(row["seed"]), row["task"])] = row
    seeds = sorted({seed for _name, seed, _task in raw})

    observations = []
    interactions = []
    incomplete = []
    conflicts = []
    baseline_checks = []
    for name, model in sorted(model_spec.items()):
        buckets = model["active_buckets"]
        n = len(buckets)
        expected_masks = range(1 << n)
        for seed in seeds:
            rows = {mask: raw.get((name, seed, "mask_%03d" % mask)) for mask in expected_masks}
            missing = [mask for mask, row in rows.items() if row is None]
            if missing:
                if any((name, seed, task) in raw for _n, _s, task in raw if _n == name and _s == seed):
                    incomplete.append({"name": name, "seed": seed, "missing_masks": len(missing)})
                continue
            solved_outcomes = {row["status"] for row in rows.values() if row["status"] in SOLVED}
            if len(solved_outcomes) > 1:
                conflicts.append({"name": name, "seed": seed, "outcomes": ",".join(sorted(solved_outcomes))})
                continue

            timeout = float(next(iter(rows.values()))["timeout_seconds"])
            penalty = timeout * args.timeout_multiplier
            costs = {
                mask: float(row["wall_seconds"]) if row["status"] in SOLVED else penalty
                for mask, row in rows.items()
            }
            full = (1 << n) - 1
            empty_cost = costs[0]
            full_cost = costs[full]
            aig = raw.get((name, seed, "baseline_aig"))
            if aig is not None:
                aig_cost = float(aig["wall_seconds"]) if aig["status"] in SOLVED else penalty
                baseline_checks.append({
                    "name": name,
                    "seed": seed,
                    "aig_cost": "%.6f" % aig_cost,
                    "empty_mask_cost": "%.6f" % empty_cost,
                    "empty_minus_aig": "%.6f" % (empty_cost - aig_cost),
                    "aig_status": aig["status"],
                    "empty_status": rows[0]["status"],
                })

            factorial_n = math.factorial(n)
            for bit, bucket in enumerate(buckets):
                phi = 0.0
                for mask in expected_masks:
                    if mask & (1 << bit):
                        continue
                    size = bin(mask).count("1")
                    weight = math.factorial(size) * math.factorial(n - size - 1) / factorial_n
                    phi += weight * (costs[mask] - costs[mask | (1 << bit)])
                add = costs[0] - costs[1 << bit]
                retain = costs[full ^ (1 << bit)] - costs[full]
                observations.append({
                    "arm": model["arm"],
                    "year": model["year"],
                    "name": name,
                    "seed": seed,
                    "bucket": bucket,
                    "bucket_xors": model["bucket_sizes"][bucket],
                    "total_xors": model["total_xors"],
                    "bucket_count": n,
                    "empty_cost": "%.6f" % empty_cost,
                    "full_cost": "%.6f" % full_cost,
                    "shapley_seconds": "%.6f" % phi,
                    "shapley_percent_of_empty": "%.6f" % (100 * phi / empty_cost if empty_cost else 0),
                    "add_seconds": "%.6f" % add,
                    "retain_seconds": "%.6f" % retain,
                })

            if n >= 2:
                denominator = math.factorial(n - 1)
                for left in range(n):
                    for right in range(left + 1, n):
                        interaction = 0.0
                        blocked = (1 << left) | (1 << right)
                        for mask in expected_masks:
                            if mask & blocked:
                                continue
                            size = bin(mask).count("1")
                            weight = (
                                math.factorial(size)
                                * math.factorial(n - size - 2)
                                / denominator
                            )
                            second = (
                                -costs[mask | blocked]
                                + costs[mask | (1 << left)]
                                + costs[mask | (1 << right)]
                                - costs[mask]
                            )
                            interaction += weight * second
                        interactions.append({
                            "arm": model["arm"],
                            "year": model["year"],
                            "name": name,
                            "seed": seed,
                            "bucket_left": buckets[left],
                            "bucket_right": buckets[right],
                            "interaction_seconds": "%.6f" % interaction,
                            "interaction_percent_of_empty": "%.6f" % (
                                100 * interaction / empty_cost if empty_cost else 0
                            ),
                        })

    obs_by_bucket: dict[tuple[str, str], list[dict]] = defaultdict(list)
    obs_by_model_bucket: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in observations:
        obs_by_bucket[(row["arm"], row["bucket"])].append(row)
        obs_by_model_bucket[(row["arm"], row["name"], row["bucket"])].append(row)

    bucket_summary = []
    for (arm, bucket), rows in sorted(obs_by_bucket.items()):
        values = [float(row["shapley_seconds"]) for row in rows]
        percents = [float(row["shapley_percent_of_empty"]) for row in rows]
        add = [float(row["add_seconds"]) for row in rows]
        retain = [float(row["retain_seconds"]) for row in rows]
        stable_positive = stable_negative = mixed = 0
        model_names = sorted({row["name"] for row in rows})
        for name in model_names:
            model_values = [
                float(row["shapley_seconds"])
                for row in obs_by_model_bucket[(arm, name, bucket)]
            ]
            if model_values and all(value > args.min_effect for value in model_values):
                stable_positive += 1
            elif model_values and all(value < -args.min_effect for value in model_values):
                stable_negative += 1
            else:
                mixed += 1
        bucket_summary.append({
            "arm": arm,
            "bucket": bucket,
            "models": len(model_names),
            "observations": len(rows),
            "median_shapley_seconds": "%.6f" % median(values),
            "mean_shapley_seconds": "%.6f" % statistics.mean(values),
            "median_shapley_percent": "%.6f" % median(percents),
            "positive_observations": sum(value > args.min_effect for value in values),
            "negative_observations": sum(value < -args.min_effect for value in values),
            "neutral_observations": sum(abs(value) <= args.min_effect for value in values),
            "stable_positive_models": stable_positive,
            "stable_negative_models": stable_negative,
            "mixed_models": mixed,
            "median_add_seconds": "%.6f" % median(add),
            "median_retain_seconds": "%.6f" % median(retain),
        })

    interaction_groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in interactions:
        interaction_groups[(row["arm"], row["bucket_left"], row["bucket_right"])].append(row)
    interaction_summary = []
    for (arm, left, right), rows in sorted(interaction_groups.items()):
        values = [float(row["interaction_seconds"]) for row in rows]
        interaction_summary.append({
            "arm": arm,
            "bucket_left": left,
            "bucket_right": right,
            "models": len({row["name"] for row in rows}),
            "observations": len(rows),
            "median_interaction_seconds": "%.6f" % median(values),
            "positive_observations": sum(value > args.min_effect for value in values),
            "negative_observations": sum(value < -args.min_effect for value in values),
            "neutral_observations": sum(abs(value) <= args.min_effect for value in values),
        })

    args.output_dir.mkdir(parents=True, exist_ok=True)
    obs_header = [
        "arm", "year", "name", "seed", "bucket", "bucket_xors", "total_xors",
        "bucket_count", "empty_cost", "full_cost", "shapley_seconds",
        "shapley_percent_of_empty", "add_seconds", "retain_seconds",
    ]
    write_tsv(args.output_dir / "shapley_observations.tsv", observations, obs_header)
    write_tsv(args.output_dir / "bucket_summary.tsv", bucket_summary, [
        "arm", "bucket", "models", "observations", "median_shapley_seconds",
        "mean_shapley_seconds", "median_shapley_percent", "positive_observations",
        "negative_observations", "neutral_observations", "stable_positive_models",
        "stable_negative_models", "mixed_models", "median_add_seconds",
        "median_retain_seconds",
    ])
    write_tsv(args.output_dir / "interaction_observations.tsv", interactions, [
        "arm", "year", "name", "seed", "bucket_left", "bucket_right",
        "interaction_seconds", "interaction_percent_of_empty",
    ])
    write_tsv(args.output_dir / "interaction_summary.tsv", interaction_summary, [
        "arm", "bucket_left", "bucket_right", "models", "observations",
        "median_interaction_seconds", "positive_observations",
        "negative_observations", "neutral_observations",
    ])
    write_tsv(args.output_dir / "baseline_checks.tsv", baseline_checks, [
        "name", "seed", "aig_cost", "empty_mask_cost", "empty_minus_aig",
        "aig_status", "empty_status",
    ])
    write_tsv(args.output_dir / "incomplete.tsv", incomplete, ["name", "seed", "missing_masks"])
    write_tsv(args.output_dir / "conflicts.tsv", conflicts, ["name", "seed", "outcomes"])

    lines = [
        "# Exact XOR Bucket Shapley Analysis",
        "",
        "- Result files: %d" % len(args.results),
        "- Run identifiers found: %s" % ", ".join(map(str, seeds)),
        "- Complete model/seed observations: %d" % len({(row['name'], row['seed']) for row in observations}),
        "- Incomplete model/seeds: %d" % len(incomplete),
        "- Outcome conflicts: %d" % len(conflicts),
        "- Positive values mean that converting the bucket to native XOR improves timeout-aware cost.",
        "",
        "| Arm | Bucket | Models | Median Shapley | Median % | Stable + / - / mixed | Add | Retain |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in bucket_summary:
        lines.append(
            "| {arm} | {bucket} | {models} | {median_shapley_seconds} | "
            "{median_shapley_percent} | {stable_positive_models}/{stable_negative_models}/{mixed_models} | "
            "{median_add_seconds} | {median_retain_seconds} |".format(**row)
        )
    (args.output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("observations=%d interactions=%d report=%s" % (
        len(observations), len(interactions), args.output_dir / "report.md",
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
