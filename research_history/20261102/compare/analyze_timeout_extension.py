#!/usr/bin/env python3
"""Estimate 1800-to-3600 second coverage gains from censored PDR runs."""

from __future__ import annotations

import argparse
import csv
import glob
import math
from collections import defaultdict
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}
CALIBRATION_CONFIGS = ("ric3_aigx2", "ric3_xagx2")
CURRENT_CONFIGS = {
    "MC strict": ("xag_legacy4", "xag_sumhigh4"),
    "MC AIG-hard": ("mc_aig4", "mc_legacy4", "mc_high4", "mc_sumhigh4"),
    "rIC3 AIG-hard": ("ric3_aig4", "ric3_legacy4", "ric3_high4", "ric3_sumhigh4"),
}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--calibration",
        type=Path,
        default=Path("test_tools/compare/results/experiments/20260725_010439_823862_seed3-b788630a_ric3xagx2_a06ed4.tsv"),
    )
    parser.add_argument(
        "--hard-dir",
        type=Path,
        default=Path("test_tools/compare/results/bve_aig_hard_domain_v1"),
    )
    parser.add_argument(
        "--strict-mc-dir",
        type=Path,
        default=Path("test_tools/compare/results/mc_sumhigh_concurrent_v1"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("test_tools/compare/results/timeout_1800_to_3600_report.md"),
    )
    return parser.parse_args()


def read_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows = []
    for path in paths:
        with path.open(encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle, delimiter="\t"))
    return rows


def solved(row: dict[str, str], config: str, limit: float) -> bool:
    return (
        row.get(f"{config}_status") in VALID
        and float(row[f"{config}_wall_seconds"]) <= limit
    )


def wilson(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    if trials == 0:
        return math.nan, math.nan
    rate = successes / trials
    denominator = 1 + z * z / trials
    center = (rate + z * z / (2 * trials)) / denominator
    radius = z * math.sqrt(rate * (1 - rate) / trials + z * z / (4 * trials * trials)) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def interval_counts(rows: list[dict[str, str]], config: str) -> list[int]:
    bounds = (0, 60, 300, 600, 900, 1200, 1500, 1800, 2400, 3000, 3600)
    times = [
        float(row[f"{config}_wall_seconds"])
        for row in rows
        if row.get(f"{config}_status") in VALID
    ]
    return [sum(low < value <= high for value in times) for low, high in zip(bounds, bounds[1:])]


def current_projection(
    rows: list[dict[str, str]], config: str, calibration_rate: float,
    calibration_tail_rate: float, calibration_factor: float,
) -> tuple[int, int, int, float, float]:
    solved_1800 = sum(solved(row, config, 1800) for row in rows)
    censored = len(rows) - solved_1800
    tail_events = sum(
        row.get(f"{config}_status") in VALID
        and 900 < float(row[f"{config}_wall_seconds"]) <= 1800
        for row in rows
    )
    tail_risk = censored + tail_events
    if tail_risk and tail_events:
        raw_probability = 1 - (1 - tail_events / tail_risk) ** 2
        adjusted_probability = min(1.0, calibration_factor * raw_probability)
    else:
        adjusted_probability = calibration_rate
    return solved_1800, censored, tail_events, adjusted_probability, censored * adjusted_probability


def model_union(rows: list[dict[str, str]], configs: tuple[str, ...]) -> tuple[int, int]:
    by_model: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        model_id = row.get("model_id") or row.get("name")
        by_model[model_id].append(row)
    solved_models = sum(
        any(solved(row, config, 1800) for row in model_rows for config in configs)
        for model_rows in by_model.values()
    )
    return solved_models, len(by_model) - solved_models


def main() -> int:
    args = arguments()
    calibration = read_rows([args.calibration])
    lines = [
        "# Timeout extension: 1800 to 3600 seconds",
        "",
        "The historical calibration is a completed 3,600-second HWMCC 2015 run with "
        "two rIC3 replicas per AIG/XAG configuration. Runs solved after 1,800 seconds "
        "are observed directly; current 1,800-second experiments are right-censored.",
        "",
        "## Historical calibration",
        "",
        "| Configuration | Solved <=1800 | Added in (1800,3600] | Unresolved at 1800 | Conversion of unresolved |",
        "|---|---:|---:|---:|---:|",
    ]
    pooled_added = 0
    pooled_unresolved = 0
    pooled_tail_events = 0
    pooled_tail_risk = 0
    for config in CALIBRATION_CONFIGS:
        solved_1800 = sum(solved(row, config, 1800) for row in calibration)
        solved_3600 = sum(solved(row, config, 3600) for row in calibration)
        added = solved_3600 - solved_1800
        unresolved = len(calibration) - solved_1800
        tail_events = sum(
            row.get(f"{config}_status") in VALID
            and 900 < float(row[f"{config}_wall_seconds"]) <= 1800
            for row in calibration
        )
        pooled_added += added
        pooled_unresolved += unresolved
        pooled_tail_events += tail_events
        pooled_tail_risk += unresolved + tail_events
        lines.append(
            f"| {config} | {solved_1800} | {added} | {unresolved} | {added / unresolved:.1%} |"
        )

    union_1800 = {
        row["name"] for row in calibration
        if any(solved(row, config, 1800) for config in CALIBRATION_CONFIGS)
    }
    union_3600 = {
        row["name"] for row in calibration
        if any(solved(row, config, 3600) for config in CALIBRATION_CONFIGS)
    }
    union_unresolved = len(calibration) - len(union_1800)
    union_added = len(union_3600 - union_1800)
    pooled_rate = pooled_added / pooled_unresolved
    pooled_low, pooled_high = wilson(pooled_added, pooled_unresolved)
    union_low, union_high = wilson(union_added, union_unresolved)
    observed_tail_rate = pooled_tail_events / pooled_tail_risk
    constant_hazard_prediction = 1 - (1 - observed_tail_rate) ** 2
    calibration_factor = pooled_rate / constant_hazard_prediction
    lines += [
        "",
        f"Pooled observation conversion is **{pooled_added}/{pooled_unresolved} = "
        f"{pooled_rate:.1%}** (Wilson 95% interval {pooled_low:.1%}--{pooled_high:.1%}).",
        f"The AIG/XAG model union grows from {len(union_1800)} to {len(union_3600)}: "
        f"**{union_added}/{union_unresolved} = {union_added / union_unresolved:.1%}** of "
        f"the unresolved models (Wilson {union_low:.1%}--{union_high:.1%}).",
        "",
        "## Solve-time histogram",
        "",
        "| Configuration | <=60 | 60-300 | 300-600 | 600-900 | 900-1200 | 1200-1500 | 1500-1800 | 1800-2400 | 2400-3000 | 3000-3600 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for config in CALIBRATION_CONFIGS:
        values = interval_counts(calibration, config)
        lines.append(f"| {config} | " + " | ".join(map(str, values)) + " |")

    strict_mc = read_rows(sorted(args.strict_mc_dir.glob("seed*.tsv")))
    hard_mc = read_rows(sorted(args.hard_dir.glob("mc_seed*_shard*_of_3.tsv")))
    hard_ric3 = read_rows(sorted(args.hard_dir.glob("ric3_seed*_shard*_of_3.tsv")))
    datasets = {
        "MC strict": strict_mc,
        "MC AIG-hard": hard_mc,
        "rIC3 AIG-hard": hard_ric3,
    }
    lines += [
        "",
        "## Projection for current experiments",
        "",
        "The central estimate scales the historical conversion by each configuration's "
        "observed 900--1800 second tail hazard. A calibration factor corrects the "
        "constant-hazard extrapolation, which overpredicts the known 3,600-second tail.",
        "",
        "| Dataset/configuration | Solved <=1800 | Censored | Solves in 900-1800 | Estimated added observations by 3600 |",
        "|---|---:|---:|---:|---:|",
    ]
    for dataset, configs in CURRENT_CONFIGS.items():
        rows = datasets[dataset]
        for config in configs:
            solved_count, censored, tail, probability, expected = current_projection(
                rows, config, pooled_rate, observed_tail_rate, calibration_factor,
            )
            lines.append(
                f"| {dataset}: {config} | {solved_count} | {censored} | {tail} | "
                f"{expected:.1f} ({probability:.1%} of censored) |"
            )

    union_rate = union_added / union_unresolved
    lines += [
        "",
        "### Model-level union estimate",
        "",
        "This table first combines all recorded seed blocks and listed configurations. "
        "The remaining models are therefore harder survivors than the calibration set; "
        "the projection is best regarded as an optimistic order-of-magnitude estimate.",
        "",
        "| Dataset | Models solved by 1800 union | Still unresolved | Estimated additional unique models by 3600 (Wilson range) |",
        "|---|---:|---:|---:|",
    ]
    for dataset, configs in CURRENT_CONFIGS.items():
        solved_models, unresolved_models = model_union(datasets[dataset], configs)
        lines.append(
            f"| {dataset} | {solved_models} | {unresolved_models} | "
            f"{unresolved_models * union_rate:.1f} "
            f"({unresolved_models * union_low:.1f}--{unresolved_models * union_high:.1f}) |"
        )

    lines += [
        "",
        "## Interpretation",
        "",
        "The historical 3,600-second run shows a real but modest tail: doubling the "
        "limit recovers about 7% of unresolved configuration observations and about 5% "
        "of unresolved models in a two-representation union. The projection should not "
        "be read as a guarantee: benchmark mix, replica count, seeds, and the declining "
        "late-time hazard differ. It is most useful as an order-of-magnitude estimate.",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
