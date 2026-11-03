#!/usr/bin/env python3
"""Pool disjoint XAG native/canonical-CNF validations with model-cluster bootstrap."""

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}
REFERENCE = "xag_native"
CANDIDATE = "xag_canonical-cnf"


def read_file(path: Path, dataset: str) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    for row in rows:
        row["_dataset"] = dataset
    return rows


def row_cost(row: dict[str, str], penalty_factor: float) -> float:
    return float(row["wall_seconds"]) if row["status"] in SOLVED else penalty_factor * float(row["timeout_seconds"])


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blind-original", required=True, type=Path)
    parser.add_argument("--blind-components", required=True, type=Path)
    parser.add_argument("--final", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout-penalty", type=float, default=1.5)
    parser.add_argument("--bootstrap", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=20260803)
    args = parser.parse_args()

    rows = []
    rows.extend(read_file(args.blind_original, "blind-1"))
    rows.extend(read_file(args.blind_components, "blind-1"))
    rows.extend(read_file(args.final, "blind-2"))
    rows = [row for row in rows if row["config"] in {REFERENCE, CANDIDATE}]

    indexed: dict[tuple[str, str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        indexed[(row["_dataset"], row["model_id"], row["run"])][row["config"]] = row
    models: dict[tuple[str, str], list[dict[str, dict[str, str]]]] = defaultdict(list)
    for (dataset, model_id, _run), pair in indexed.items():
        if REFERENCE in pair and CANDIDATE in pair:
            models[(dataset, model_id)].append(pair)

    model_records = []
    for (dataset, model_id), pairs in models.items():
        if not any(pair[config]["status"] in SOLVED for pair in pairs for config in (REFERENCE, CANDIDATE)):
            continue
        ref = sum(row_cost(pair[REFERENCE], args.timeout_penalty) for pair in pairs)
        cand = sum(row_cost(pair[CANDIDATE], args.timeout_penalty) for pair in pairs)
        model_records.append((dataset, model_id, ref, cand, pairs))

    def summary(subset: list[tuple[str, str, float, float, list[dict[str, dict[str, str]]]]]) -> dict[str, float | int]:
        ref_total = sum(record[2] for record in subset)
        cand_total = sum(record[3] for record in subset)
        ref_solved = cand_solved = ref_only = cand_only = joint_runs = 0
        ref_joint = cand_joint = 0.0
        ratios = []
        for *_metadata, pairs in subset:
            for pair in pairs:
                ref_ok = pair[REFERENCE]["status"] in SOLVED
                cand_ok = pair[CANDIDATE]["status"] in SOLVED
                ref_solved += ref_ok
                cand_solved += cand_ok
                ref_only += ref_ok and not cand_ok
                cand_only += cand_ok and not ref_ok
                if ref_ok and cand_ok:
                    joint_runs += 1
                    ref_time = float(pair[REFERENCE]["wall_seconds"])
                    cand_time = float(pair[CANDIDATE]["wall_seconds"])
                    ref_joint += ref_time
                    cand_joint += cand_time
                    ratios.append(ref_time / cand_time)
        return {
            "models": len(subset), "ref_total": ref_total, "cand_total": cand_total,
            "reduction": 100.0 * (ref_total - cand_total) / ref_total,
            "ref_solved": ref_solved, "cand_solved": cand_solved,
            "ref_only": ref_only, "cand_only": cand_only, "joint_runs": joint_runs,
            "joint_reduction": 100.0 * (ref_joint - cand_joint) / ref_joint,
            "median_ratio": statistics.median(ratios),
        }

    grouped = {
        "blind-1": [record for record in model_records if record[0] == "blind-1"],
        "blind-2": [record for record in model_records if record[0] == "blind-2"],
        "pooled": model_records,
    }
    summaries = {name: summary(subset) for name, subset in grouped.items()}

    rng = random.Random(args.seed)
    reductions = []
    n = len(model_records)
    for _ in range(args.bootstrap):
        sample = [model_records[rng.randrange(n)] for _ in range(n)]
        ref_total = sum(record[2] for record in sample)
        cand_total = sum(record[3] for record in sample)
        reductions.append(100.0 * (ref_total - cand_total) / ref_total)
    low = percentile(reductions, 0.025)
    high = percentile(reductions, 0.975)
    probability_positive = sum(value > 0 for value in reductions) / len(reductions)

    lines = [
        "# Canonical-CNF Cross-Validation", "",
        "Models unsolved by both configurations in both repeats are excluded. Timeout runs cost "
        f"{args.timeout_penalty:.1f}x their limit. Bootstrap resamples whole models, preserving "
        "the two repeated four-lane runs as one cluster.", "",
        "| Dataset | Informative models | Native/canonical solved runs | Native/canonical only | Native s | Canonical s | Penalized reduction | Joint reduction | Median native/canonical |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("blind-1", "blind-2", "pooled"):
        result = summaries[name]
        lines.append(
            f"| {name} | {result['models']} | {result['ref_solved']}/{result['cand_solved']} | "
            f"{result['ref_only']}/{result['cand_only']} | {result['ref_total']:.2f} | "
            f"{result['cand_total']:.2f} | {result['reduction']:+.2f}% | "
            f"{result['joint_reduction']:+.2f}% | {result['median_ratio']:.3f} |"
        )
    lines.extend([
        "", "## Model-Cluster Bootstrap", "",
        f"- Replicates: {args.bootstrap}",
        f"- Pooled penalized reduction: {summaries['pooled']['reduction']:+.2f}%",
        f"- 95% percentile interval: [{low:+.2f}%, {high:+.2f}%]",
        f"- Bootstrap probability that canonical-CNF is better: {100.0 * probability_positive:.2f}%",
        "",
    ])
    report = "\n".join(lines)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
