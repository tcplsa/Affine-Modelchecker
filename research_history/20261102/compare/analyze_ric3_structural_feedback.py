#!/usr/bin/env python3
"""Analyze four-seed structural-predicate portfolios and feedback transfer."""

from __future__ import annotations

import argparse
import csv
import glob
import math
import random
import statistics
from collections import Counter
from collections import defaultdict
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}
CONFIGS = ("baseline", "critical64", "xorcritical64", "feedback64", "feedback128")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--input", type=Path)
    inputs.add_argument("--input-glob")
    parser.add_argument("--feedback-dir", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--bootstrap", type=int, default=20000)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def geo(values: list[float]) -> float:
    return math.exp(sum(math.log(value) for value in values) / len(values)) if values else math.nan


def percentile(values: list[float], probability: float) -> float:
    values = sorted(values)
    position = (len(values) - 1) * probability
    low = int(position)
    high = min(low + 1, len(values) - 1)
    weight = position - low
    return values[low] * (1 - weight) + values[high] * weight


def cluster_ci(
    rows: list[dict[str, str]], config: str, iterations: int,
) -> tuple[float, float]:
    by_family: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row.get(f"{config}_status") not in VALID or row.get("baseline_status") not in VALID:
            continue
        baseline = float(row["baseline_wall_seconds"])
        if baseline < 1.0:
            continue
        by_family[row["family"]].append(
            math.log(float(row[f"{config}_wall_seconds"]) / baseline)
        )
    families = sorted(by_family)
    if not families:
        return math.nan, math.nan
    rng = random.Random(20260813)
    samples = []
    for _ in range(iterations):
        values = [value for _ in families for value in by_family[rng.choice(families)]]
        samples.append(math.exp(statistics.mean(values)))
    return percentile(samples, 0.025), percentile(samples, 0.975)


def status_detail(rows: list[dict[str, str]], config: str) -> str:
    counts = Counter(row.get(f"{config}_status", "") for row in rows)
    return ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))


def main() -> int:
    args = arguments()
    paths = [args.input] if args.input else [Path(path) for path in sorted(glob.glob(args.input_glob))]
    rows = []
    for path in paths:
        with path.open(encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle, delimiter="\t"))
    feedback_files = list(args.feedback_dir.glob("*.json"))
    solved = Counter()
    costs = Counter()
    conflicts = sum(row.get("outcome_conflict") == "1" for row in rows)
    for config in CONFIGS:
        for row in rows:
            if row.get(f"{config}_status") in VALID:
                solved[config] += 1
                costs[config] += float(row[f"{config}_wall_seconds"])
            else:
                costs[config] += args.timeout

    baseline = "baseline"
    lines = [
        "# rIC3 structural-predicate feedback experiment", "",
        f"Models: {len(rows)}; feedback files: {len(feedback_files)}; outcome conflicts: {conflicts}.", "",
        "| Configuration | Solved | Only/lost vs baseline | Common | Geo ratio (family CI) | Summed common ratio | PAR-1 | PAR-1.5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    base_set = {
        row["model_id"] for row in rows if row.get(f"{baseline}_status") in VALID
    }
    for config in CONFIGS:
        config_set = {
            row["model_id"] for row in rows if row.get(f"{config}_status") in VALID
        }
        common = [
            row for row in rows
            if row.get(f"{config}_status") in VALID and row.get(f"{baseline}_status") in VALID
        ]
        ratio_rows = [row for row in common if float(row[f"{baseline}_wall_seconds"]) >= 1.0]
        ratios = [float(row[f"{config}_wall_seconds"]) / float(row[f"{baseline}_wall_seconds"]) for row in ratio_rows]
        summed = (
            sum(float(row[f"{config}_wall_seconds"]) for row in common)
            / sum(float(row[f"{baseline}_wall_seconds"]) for row in common)
        ) if common else math.nan
        informative = [
            row for row in rows
            if row.get(f"{config}_status") in VALID or row.get(f"{baseline}_status") in VALID
        ]
        def par(penalty: float) -> float:
            candidate = sum(
                float(row[f"{config}_wall_seconds"])
                if row.get(f"{config}_status") in VALID else penalty * args.timeout
                for row in informative
            )
            reference = sum(
                float(row[f"{baseline}_wall_seconds"])
                if row.get(f"{baseline}_status") in VALID else penalty * args.timeout
                for row in informative
            )
            return candidate / reference if reference else math.nan
        ci_low, ci_high = cluster_ci(rows, config, args.bootstrap)
        lines.append(
            f"| {config} | {solved[config]} | {len(config_set - base_set)}/{len(base_set - config_set)} | "
            f"{len(common)} | {geo(ratios):.3f} [{ci_low:.3f}, {ci_high:.3f}] | "
            f"{summed:.3f} | {par(1.0):.3f} | {par(1.5):.3f} |"
        )
    lines += [
        "", "The main success criterion is solved-set expansion and penalized runtime. "
        "The geometric ratio is secondary and excludes sub-second baseline cases.",
        "", "## Status counts", "",
        "| Configuration | Statuses |", "|---|---|",
    ]
    for config in CONFIGS:
        lines.append(f"| {config} | {status_detail(rows, config)} |")

    lines += ["", "## Coverage changes", ""]
    for config in CONFIGS[1:]:
        config_set = {
            row["model_id"] for row in rows if row.get(f"{config}_status") in VALID
        }
        gained = sorted(config_set - base_set)
        lost = sorted(base_set - config_set)
        lines += [
            f"### {config}", "",
            f"Gained ({len(gained)}): " + (", ".join(gained) if gained else "none") + ".", "",
            f"Lost ({len(lost)}): " + (", ".join(lost) if lost else "none") + ".", "",
        ]

    config_sets = {
        config: {row["model_id"] for row in rows if row.get(f"{config}_status") in VALID}
        for config in CONFIGS
    }
    union = set().union(*config_sets.values())
    never = sorted({row["model_id"] for row in rows} - union)
    lines += [
        "## Offline coverage ceiling", "",
        f"The union of all five equal-budget configurations solves {len(union)}/{len(rows)} models, "
        f"including {len(union - base_set)} beyond baseline. This is an offline diagnostic, not an "
        "equal-resource portfolio result.", "",
        f"Never solved ({len(never)}): " + (", ".join(never) if never else "none") + ".",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
