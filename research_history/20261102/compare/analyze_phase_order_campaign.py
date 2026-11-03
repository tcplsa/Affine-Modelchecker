#!/usr/bin/env python3
"""Analyze the 2x2 transition/lift variable-order experiment."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}
TREATMENTS = (
    "first__first", "numeric__first", "first__numeric", "numeric__numeric",
)


def cost(row: dict[str, str], penalty: float) -> float:
    if row["status"] in SOLVED:
        return float(row["wall_seconds"])
    return penalty * float(row["timeout_seconds"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout-penalty", type=float, default=1.5)
    parser.add_argument("--min-difference", type=float, default=2.0)
    args = parser.parse_args()

    cells: dict[tuple[str, str, str, str], dict[str, str]] = {}
    duplicates = 0
    for path in args.inputs:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = (row["model_id"], row["run"], row["config"], row["treatment"])
                duplicates += key in cells
                cells[key] = row

    lines = [
        "# Translation/Lift Presentation Campaign", "",
        f"Rows: {len(cells)}; duplicates replaced: {duplicates}; timeout penalty: "
        f"{args.timeout_penalty:.2f}x; small-difference threshold: "
        f"{args.min_difference:.2f}s.", "",
    ]
    configs = sorted({key[2] for key in cells})
    for config in configs:
        config_cells = {key: row for key, row in cells.items() if key[2] == config}
        complete_keys = sorted({
            (key[0], key[1]) for key in config_cells
            if all((key[0], key[1], config, treatment) in cells for treatment in TREATMENTS)
        })
        retained = [
            key for key in complete_keys
            if any(cells[(key[0], key[1], config, treatment)]["status"] in SOLVED
                   for treatment in TREATMENTS)
        ]
        lines.extend([
            f"## {config}", "",
            f"Complete model/run cells: {len(complete_keys)}; retained non-all-timeout: {len(retained)}.", "",
            "| Rank | Translation | Lift | Solved | Penalized s | Gap vs best | Wins >2s |",
            "|---:|---|---|---:|---:|---:|---:|",
        ])
        summaries = []
        for treatment in TREATMENTS:
            rows = [cells[(model, run, config, treatment)] for model, run in retained]
            total = sum(cost(row, args.timeout_penalty) for row in rows)
            solved = sum(row["status"] in SOLVED for row in rows)
            wins = 0
            for model, run in retained:
                treatment_costs = {
                    item: cost(cells[(model, run, config, item)], args.timeout_penalty)
                    for item in TREATMENTS
                }
                if max(treatment_costs.values()) - min(treatment_costs.values()) > args.min_difference:
                    wins += treatment_costs[treatment] == min(treatment_costs.values())
            summaries.append((total, treatment, solved, wins))
        best = min(item[0] for item in summaries) if summaries else math.nan
        for rank, (total, treatment, solved, wins) in enumerate(sorted(summaries), 1):
            translation, lift = treatment.split("__")
            gap = 100.0 * (total - best) / best if best else 0.0
            lines.append(
                f"| {rank} | {translation} | {lift} | {solved}/{len(retained)} | "
                f"{total:.2f} | {gap:+.2f}% | {wins} |"
            )

        baseline = "first__first"
        lines.extend([
            "", "### Versus first/first", "",
            "| Candidate | Retained | Joint | Base/candidate only | Penalized reduction | Joint reduction | Median base/candidate | Wins >2s (base/candidate) |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for treatment in TREATMENTS[1:]:
            pairs = [
                (cells[(model, run, config, baseline)], cells[(model, run, config, treatment)])
                for model, run in complete_keys
            ]
            eligible = [pair for pair in pairs if pair[0]["status"] in SOLVED or pair[1]["status"] in SOLVED]
            joint = [pair for pair in pairs if pair[0]["status"] in SOLVED and pair[1]["status"] in SOLVED]
            base_total = sum(cost(base, args.timeout_penalty) for base, _ in eligible)
            candidate_total = sum(cost(candidate, args.timeout_penalty) for _, candidate in eligible)
            base_joint = sum(float(base["wall_seconds"]) for base, _ in joint)
            candidate_joint = sum(float(candidate["wall_seconds"]) for _, candidate in joint)
            base_only = sum(base["status"] in SOLVED and candidate["status"] not in SOLVED for base, candidate in pairs)
            candidate_only = sum(candidate["status"] in SOLVED and base["status"] not in SOLVED for base, candidate in pairs)
            ratios = [float(base["wall_seconds"]) / max(float(candidate["wall_seconds"]), 1e-9) for base, candidate in joint]
            base_wins = sum(float(base["wall_seconds"]) + args.min_difference < float(candidate["wall_seconds"]) for base, candidate in joint)
            candidate_wins = sum(float(candidate["wall_seconds"]) + args.min_difference < float(base["wall_seconds"]) for base, candidate in joint)
            reduction = 100.0 * (base_total - candidate_total) / base_total if base_total else 0.0
            joint_reduction = 100.0 * (base_joint - candidate_joint) / base_joint if base_joint else 0.0
            lines.append(
                f"| {treatment.replace('__', '/')} | {len(eligible)} | {len(joint)} | "
                f"{base_only}/{candidate_only} | {reduction:+.2f}% | {joint_reduction:+.2f}% | "
                f"{statistics.median(ratios) if ratios else math.nan:.3f} | "
                f"{base_wins}/{candidate_wins} |"
            )

        lines.extend([
            "", "### Per-run penalized reduction versus first/first", "",
            "| Run | numeric/first | first/numeric | numeric/numeric |",
            "|---:|---:|---:|---:|",
        ])
        runs = sorted({key[1] for key in config_cells}, key=int)
        for run in runs:
            values = []
            for treatment in TREATMENTS[1:]:
                pairs = []
                for model, candidate_run in complete_keys:
                    if candidate_run != run:
                        continue
                    base = cells[(model, run, config, baseline)]
                    candidate = cells[(model, run, config, treatment)]
                    if base["status"] in SOLVED or candidate["status"] in SOLVED:
                        pairs.append((base, candidate))
                base_total = sum(cost(base, args.timeout_penalty) for base, _ in pairs)
                candidate_total = sum(cost(candidate, args.timeout_penalty) for _, candidate in pairs)
                values.append(100.0 * (base_total - candidate_total) / base_total if base_total else math.nan)
            lines.append(f"| {run} | {values[0]:+.2f}% | {values[1]:+.2f}% | {values[2]:+.2f}% |")

        status = Counter(row["status"] for row in config_cells.values())
        lines.extend(["", f"Status counts: {dict(status)}", ""])

    report = "\n".join(lines) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
