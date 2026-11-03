#!/usr/bin/env python3
"""Analyze variable mapping x CaDiCaL initial queue orientation."""

from __future__ import annotations

import argparse
import csv
import math
import random
from collections import Counter, defaultdict
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}
CELLS = (
    "native-forward", "canonical-forward",
    "native-reverse", "canonical-reverse",
)


def read(path: Path, orientation: str) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    result = []
    for row in rows:
        if row["config"] == "xag_native":
            row["_cell"] = f"native-{orientation}"
        elif row["config"] == "xag_canonical-cnf":
            row["_cell"] = f"canonical-{orientation}"
        else:
            continue
        result.append(row)
    return result


def cost(row: dict[str, str], penalty: float) -> float:
    return float(row["wall_seconds"]) if row["status"] in SOLVED else penalty * float(row["timeout_seconds"])


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def pair(
    cases: list[dict[str, dict[str, str]]], reference: str, candidate: str, penalty: float
) -> dict[str, float | int]:
    eligible = [case for case in cases if case[reference]["status"] in SOLVED or case[candidate]["status"] in SOLVED]
    jointly = [case for case in cases if case[reference]["status"] in SOLVED and case[candidate]["status"] in SOLVED]
    ref_total = sum(cost(case[reference], penalty) for case in eligible)
    cand_total = sum(cost(case[candidate], penalty) for case in eligible)
    return {
        "eligible": len(eligible), "jointly": len(jointly),
        "ref_only": sum(case[reference]["status"] in SOLVED and case[candidate]["status"] not in SOLVED for case in cases),
        "cand_only": sum(case[candidate]["status"] in SOLVED and case[reference]["status"] not in SOLVED for case in cases),
        "ref_total": ref_total, "cand_total": cand_total,
        "reduction": 100.0 * (ref_total - cand_total) / ref_total if ref_total else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forward", required=True, type=Path)
    parser.add_argument("--reverse", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout-penalty", type=float, default=1.5)
    parser.add_argument("--bootstrap", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=20260804)
    args = parser.parse_args()

    rows = read(args.forward, "forward") + read(args.reverse, "reverse")
    indexed: dict[tuple[str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    duplicates = 0
    for row in rows:
        key = (row["model_id"], row["run"])
        duplicates += row["_cell"] in indexed[key]
        indexed[key][row["_cell"]] = row
    complete = [case for case in indexed.values() if all(cell in case for cell in CELLS)]
    conflicts = sum(
        len({case[cell]["status"] for cell in CELLS if case[cell]["status"] in SOLVED}) > 1
        for case in complete
    )

    comparisons = (
        ("native-forward", "canonical-forward", "Mapping effect, normal queue"),
        ("native-reverse", "canonical-reverse", "Mapping effect, reversed queue"),
        ("native-forward", "native-reverse", "Queue reversal, native mapping"),
        ("canonical-forward", "canonical-reverse", "Queue reversal, canonical mapping"),
    )
    summaries = {
        title: pair(complete, reference, candidate, args.timeout_penalty)
        for reference, candidate, title in comparisons
    }
    forward_delta = summaries["Mapping effect, normal queue"]["ref_total"] - summaries["Mapping effect, normal queue"]["cand_total"]
    reverse_delta = summaries["Mapping effect, reversed queue"]["ref_total"] - summaries["Mapping effect, reversed queue"]["cand_total"]

    by_model: dict[str, list[dict[str, dict[str, str]]]] = defaultdict(list)
    for (model_id, _run), case in indexed.items():
        if all(cell in case for cell in CELLS):
            by_model[model_id].append(case)
    model_records = []
    for model_id, model_cases in by_model.items():
        if not any(case[cell]["status"] in SOLVED for case in model_cases for cell in CELLS):
            continue
        totals = {
            cell: sum(cost(case[cell], args.timeout_penalty) for case in model_cases)
            for cell in CELLS
        }
        model_records.append((model_id, totals))

    common_totals = {
        cell: sum(totals[cell] for _, totals in model_records)
        for cell in CELLS
    }

    def effects(totals: dict[str, float]) -> tuple[float, float, float, float, float]:
        mapping_forward = totals["native-forward"] - totals["canonical-forward"]
        mapping_reverse = totals["native-reverse"] - totals["canonical-reverse"]
        queue_native = totals["native-forward"] - totals["native-reverse"]
        queue_canonical = totals["canonical-forward"] - totals["canonical-reverse"]
        interaction = mapping_reverse - mapping_forward
        return mapping_forward, mapping_reverse, queue_native, queue_canonical, interaction

    common_effects = effects(common_totals)
    bootstrap_effects = [[] for _ in range(5)]
    rng = random.Random(args.seed)
    for _ in range(args.bootstrap):
        sampled = [model_records[rng.randrange(len(model_records))][1] for _ in model_records]
        sampled_totals = {cell: sum(record[cell] for record in sampled) for cell in CELLS}
        for values, value in zip(bootstrap_effects, effects(sampled_totals)):
            values.append(value)

    lines = [
        "# Canonical Mapping / Queue Orientation Causal Report", "",
        f"Rows read: {len(rows)}; complete four-cell cases: {len(complete)}; duplicate cells: "
        f"{duplicates}; outcome conflicts: {conflicts}; timeout penalty: {args.timeout_penalty:.2f}x.", "",
        "| Contrast | Retained | Joint | Reference/candidate only | Reference s | Candidate s | Candidate reduction |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for reference, candidate, title in comparisons:
        result = summaries[title]
        lines.append(
            f"| {title} | {result['eligible']} | {result['jointly']} | "
            f"{result['ref_only']}/{result['cand_only']} | {result['ref_total']:.2f} | "
            f"{result['cand_total']:.2f} | {result['reduction']:+.2f}% |"
        )
    lines.extend([
        "", "## Difference In Differences", "",
        f"Pair-specific canonical gain with normal queue: {forward_delta:+.2f} s; "
        f"with reversed queue: {reverse_delta:+.2f} s.", "",
        f"The common model-cluster analysis retains {len(model_records)} models and charges every "
        "cell on exactly the same set:", "",
        "| Effect (positive means candidate operation helps) | Seconds | 95% model-bootstrap interval |",
        "|---|---:|---:|",
        f"| Canonical mapping, normal queue | {common_effects[0]:+.2f} | "
        f"[{percentile(bootstrap_effects[0], 0.025):+.2f}, {percentile(bootstrap_effects[0], 0.975):+.2f}] |",
        f"| Canonical mapping, reversed queue | {common_effects[1]:+.2f} | "
        f"[{percentile(bootstrap_effects[1], 0.025):+.2f}, {percentile(bootstrap_effects[1], 0.975):+.2f}] |",
        f"| Reverse queue, native mapping | {common_effects[2]:+.2f} | "
        f"[{percentile(bootstrap_effects[2], 0.025):+.2f}, {percentile(bootstrap_effects[2], 0.975):+.2f}] |",
        f"| Reverse queue, canonical mapping | {common_effects[3]:+.2f} | "
        f"[{percentile(bootstrap_effects[3], 0.025):+.2f}, {percentile(bootstrap_effects[3], 0.975):+.2f}] |",
        f"| Mapping x queue interaction | {common_effects[4]:+.2f} | "
        f"[{percentile(bootstrap_effects[4], 0.025):+.2f}, {percentile(bootstrap_effects[4], 0.975):+.2f}] |",
        "",
        "A large negative interaction means reversing the queue removes canonical's normal-queue "
        "benefit, supporting initial decision priority as the causal mechanism. An interval around "
        "zero instead leaves compact numbering or memory locality as equally plausible.", "",
        "## Status Counts", "",
    ])
    for cell in CELLS:
        lines.append(f"- {cell}: {dict(Counter(row['status'] for row in rows if row['_cell'] == cell))}")
    report = "\n".join(lines) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
