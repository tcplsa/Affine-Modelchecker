#!/usr/bin/env python3
"""Summarize coverage, paired speed, and resulting CNF size for freeze policies."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

from run_cnf_freeze_campaign import policies_for_suite


VALID = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=("screen", "hard"), required=True)
    parser.add_argument("--input", required=True, type=Path, nargs="+")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def number(row: dict[str, str], key: str) -> float | None:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return None


def median(values: list[float]) -> str:
    return f"{statistics.median(values):.3f}" if values else "-"


def main() -> int:
    args = parse_args()
    rows: list[dict[str, str]] = []
    for campaign, path in enumerate(args.input):
        with path.open(encoding="utf-8") as handle:
            campaign_rows = list(csv.DictReader(handle, delimiter="\t"))
        for row in campaign_rows:
            row["__campaign"] = str(campaign)
        rows.extend(campaign_rows)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    model_index = {
        (Path(model["path"]).stem, str(model["size_bytes"])): model
        for model in manifest
    }

    policies = policies_for_suite(args.suite)
    baseline = "aig_none"

    def reference(config: str) -> str:
        return "xag_none" if config.startswith("xag_") else baseline

    def solved(row: dict[str, str], config: str) -> bool:
        return row.get(f"{config}_status") in VALID

    def model(row: dict[str, str]) -> dict[str, object]:
        return model_index[(row["name"].split("__")[-1], row["size_bytes"])]

    lines = [
        f"# CNF retention {args.suite} report", "", f"Models: {len(rows)}.", "",
        "| Configuration | Solved | SAFE | UNSAFE | Penalized cost | "
        "Only vs AIG | Lost vs AIG | Wins >2s | Losses >2s |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for config, label, *_rest in policies:
        both = [row for row in rows if solved(row, config) and solved(row, baseline)]
        only = sum(solved(row, config) and not solved(row, baseline) for row in rows)
        lost = sum(solved(row, baseline) and not solved(row, config) for row in rows)
        wins = sum(
            float(row[f"{config}_wall_seconds"]) + 2.0
            < float(row[f"{baseline}_wall_seconds"])
            for row in both
        )
        losses = sum(
            float(row[f"{baseline}_wall_seconds"]) + 2.0
            < float(row[f"{config}_wall_seconds"])
            for row in both
        )
        cost = sum(
            float(row[f"{config}_wall_seconds"])
            if solved(row, config) else 1.5 * float(row["timeout_seconds"])
            for row in rows
        )
        lines.append(
            f"| {label} | {sum(solved(row, config) for row in rows)} | "
            f"{sum(row.get(f'{config}_status') == 'SAFE' for row in rows)} | "
            f"{sum(row.get(f'{config}_status') == 'UNSAFE' for row in rows)} | "
            f"{cost:.1f} | {only} | {lost} | {wins} | {losses} |"
        )

    lines += [
        "", "## Paired trajectory and CNF statistics", "",
        "| Configuration | Common | Runtime ratio | Query ratio | CTI ratio | "
        "CNF clause ratio | Frozen vars |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for config, label, *_rest in policies:
        ref = reference(config)
        both = [row for row in rows if solved(row, config) and solved(row, ref)]
        ratios: dict[str, list[float]] = {
            "runtime": [], "queries": [], "cti": [], "clauses": [], "frozen": [],
        }
        for row in both:
            pairs = {
                "runtime": (number(row, f"{config}_wall_seconds"), number(row, f"{ref}_wall_seconds")),
                "queries": (number(row, f"{config}_queries"), number(row, f"{ref}_queries")),
                "cti": (number(row, f"{config}_cti"), number(row, f"{ref}_cti")),
                "clauses": (
                    number(row, f"{config}_translation_simplified_clauses"),
                    number(row, f"{ref}_translation_simplified_clauses"),
                ),
            }
            for key, (candidate, denominator) in pairs.items():
                if candidate is not None and denominator is not None and denominator > 0:
                    ratios[key].append(candidate / denominator)
            frozen = number(row, f"{config}_translation_frozen_gate_vars")
            if frozen is not None:
                ratios["frozen"].append(frozen)
        lines.append(
            f"| {label} | {len(both)} | {median(ratios['runtime'])} | "
            f"{median(ratios['queries'])} | {median(ratios['cti'])} | "
            f"{median(ratios['clauses'])} | {median(ratios['frozen'])} |"
        )

    if len(args.input) > 1:
        lines += [
            "", "## Cross-seed stability", "",
            "A stable win/loss requires a greater-than-two-second difference in every "
            "campaign, and both configurations must solve the model in every campaign.", "",
            "| Configuration | Comparable | Stable wins | Stable losses | Mixed/neutral | "
            "Candidate-only both seeds | Reference-only both seeds |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        row_groups: dict[tuple[str, str], list[dict[str, str]]] = {}
        for row in rows:
            key = (row["name"], row["size_bytes"])
            row_groups.setdefault(key, []).append(row)
        for config, label, *_rest in policies:
            ref = reference(config)
            comparable = stable_wins = stable_losses = mixed = 0
            candidate_only = reference_only = 0
            for group in row_groups.values():
                comparisons: list[int] = []
                for row in group:
                    if not solved(row, config) or not solved(row, ref):
                        continue
                    candidate = float(row[f"{config}_wall_seconds"])
                    base = float(row[f"{ref}_wall_seconds"])
                    comparisons.append(-1 if candidate + 2 < base else (1 if base + 2 < candidate else 0))
                candidate_solved = [solved(row, config) for row in group]
                reference_solved = [solved(row, ref) for row in group]
                if len(group) == len(args.input) and all(candidate_solved) and not any(reference_solved):
                    candidate_only += 1
                if len(group) == len(args.input) and all(reference_solved) and not any(candidate_solved):
                    reference_only += 1
                if len(comparisons) != len(args.input):
                    continue
                comparable += 1
                if all(value == -1 for value in comparisons):
                    stable_wins += 1
                elif all(value == 1 for value in comparisons):
                    stable_losses += 1
                else:
                    mixed += 1
            lines.append(
                f"| {label} | {comparable} | {stable_wins} | {stable_losses} | "
                f"{mixed} | {candidate_only} | {reference_only} |"
            )

    lines += ["", "## Coverage by historical tier", ""]
    tiers = ("medium", "slow", "timeout")
    lines.append("| Configuration | " + " | ".join(tiers) + " |")
    lines.append("|---|" + "---:|" * len(tiers))
    for config, label, *_rest in policies:
        counts = [
            sum(solved(row, config) for row in rows if model(row).get("tier") == tier)
            for tier in tiers
        ]
        lines.append(f"| {label} | " + " | ".join(map(str, counts)) + " |")

    conflicts = sum(row.get("outcome_conflict") == "1" for row in rows)
    lines += ["", f"Outcome conflicts: {conflicts}.", ""]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"rows={len(rows)} conflicts={conflicts} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
