#!/usr/bin/env python3
"""Analyze the paired rIC3 native-local component ablation."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}
CONFIGS = (
    ("legacy4_seed2", "Legacy"),
    ("product_high4_seed2", "Product+high"),
    ("product_sum_high4_seed2", "Product+sum+high"),
    ("native_boundary4_seed2", "Product+boundary+high"),
    ("native_local4_seed2", "Product+boundary+sum+high"),
)
COMPARISONS = (
    ("product_sum_high4_seed2", "product_high4_seed2", "Occurrence-sum without boundary"),
    ("native_boundary4_seed2", "product_high4_seed2", "Boundary without occurrence-sum"),
    ("native_local4_seed2", "product_sum_high4_seed2", "Boundary with occurrence-sum"),
    ("native_local4_seed2", "native_boundary4_seed2", "Occurrence-sum with boundary"),
    ("native_local4_seed2", "legacy4_seed2", "Full native-local vs legacy"),
)


def solved(row: dict[str, str], config: str) -> bool:
    return row.get(f"{config}_status") in VALID


def stats(rows: list[dict[str, str]], candidate: str, reference: str) -> dict[str, float | int]:
    common = [row for row in rows if solved(row, candidate) and solved(row, reference)]
    informative = [row for row in rows if solved(row, candidate) or solved(row, reference)]
    ratios = [
        float(row[f"{candidate}_wall_seconds"]) / float(row[f"{reference}_wall_seconds"])
        for row in common
    ]
    penalty = lambda row, config: (
        float(row[f"{config}_wall_seconds"])
        if solved(row, config) else 1.5 * float(row["timeout_seconds"])
    )
    candidate_cost = sum(penalty(row, candidate) for row in informative)
    reference_cost = sum(penalty(row, reference) for row in informative)
    return {
        "candidate_solved": sum(solved(row, candidate) for row in rows),
        "reference_solved": sum(solved(row, reference) for row in rows),
        "only": sum(solved(row, candidate) and not solved(row, reference) for row in rows),
        "lost": sum(solved(row, reference) and not solved(row, candidate) for row in rows),
        "common": len(common),
        "geo": math.exp(statistics.mean(map(math.log, ratios))) if ratios else math.nan,
        "median": statistics.median(ratios) if ratios else math.nan,
        "par": candidate_cost / reference_cost if reference_cost else math.nan,
    }


def table(rows: list[dict[str, str]], title: str) -> list[str]:
    lines = [
        f"## {title}", "",
        "| Effect | Solved candidate/reference | Only/lost | Common | Geo | Median | PAR |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for candidate, reference, label in COMPARISONS:
        value = stats(rows, candidate, reference)
        lines.append(
            f"| {label} | {value['candidate_solved']}/{value['reference_solved']} | "
            f"{value['only']}/{value['lost']} | {value['common']} | {value['geo']:.3f} | "
            f"{value['median']:.3f} | {value['par']:.3f} |"
        )
    lines.append("")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = []
    seen = set()
    for path in args.input:
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                model_id = row["model_id"]
                if model_id in seen:
                    raise ValueError(f"duplicate result row: {model_id}")
                seen.add(model_id)
                rows.append(row)
    lines = [
        "# rIC3 native-local follow-up", "", f"Completed models: {len(rows)}.", "",
        "All configurations use four independent IC3 replicas and the same disjoint seed block.", "",
        "| Configuration | Solved | Unique against the other four |",
        "|---|---:|---:|",
    ]
    solved_sets = {
        config: {row["model_id"] for row in rows if solved(row, config)}
        for config, _ in CONFIGS
    }
    for config, label in CONFIGS:
        others = set().union(*(values for key, values in solved_sets.items() if key != config))
        lines.append(f"| {label} | {len(solved_sets[config])} | {len(solved_sets[config] - others)} |")
    lines += [""] + table(rows, "All selected models")
    for bucket in ("baseline_discordant", "hard_common", "all_baseline_unsolved"):
        bucket_rows = [row for row in rows if row.get("group") == bucket]
        if bucket_rows:
            lines += table(bucket_rows, bucket)
    lines += [f"Outcome conflicts: {sum(row.get('outcome_conflict') == '1' for row in rows)}.", ""]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"rows={len(rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
