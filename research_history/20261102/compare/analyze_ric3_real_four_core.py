#!/usr/bin/env python3
"""Summarize the real rIC3 four-worker control."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path


CONFIGS = [
    ("ric3_4_noshare", "rIC3-4 no sharing"),
    ("ric3_4_share", "rIC3-4 shared lemmas"),
]
VALID = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = list(csv.DictReader(args.input.open(encoding="utf-8"), delimiter="\t"))
    lines = [
        "# Real rIC3 four-core control", "", f"Models: {len(rows)}.", "",
        "| Configuration | Solved | SAFE | UNSAFE | Penalized cost |",
        "|---|---:|---:|---:|---:|",
    ]
    for cfg, label in CONFIGS:
        solved = safe = unsafe = 0
        cost = 0.0
        for row in rows:
            status = row[f"{cfg}_status"]
            if status in VALID:
                solved += 1
                safe += status == "SAFE"
                unsafe += status == "UNSAFE"
                cost += float(row[f"{cfg}_wall_seconds"])
            else:
                cost += 1.5 * float(row["timeout_seconds"])
        lines.append(f"| {label} | {solved} | {safe} | {unsafe} | {cost:.1f} |")
    conflicts = sum(row.get("outcome_conflict") == "1" for row in rows)
    no_share, share = (cfg for cfg, _label in CONFIGS)
    both = [
        row for row in rows
        if row[f"{no_share}_status"] in VALID and row[f"{share}_status"] in VALID
    ]
    no_only = sum(
        row[f"{no_share}_status"] in VALID and row[f"{share}_status"] not in VALID
        for row in rows
    )
    share_only = sum(
        row[f"{share}_status"] in VALID and row[f"{no_share}_status"] not in VALID
        for row in rows
    )
    lines += [
        "", "## Paired comparison", "",
        f"Both solved: {len(both)}; no-sharing only: {no_only}; sharing only: {share_only}.", "",
        "| Minimum gap | No-sharing wins | Sharing wins | Ties |",
        "|---:|---:|---:|---:|",
    ]
    for gap in (0.0, 2.0):
        no_wins = sum(
            float(row[f"{no_share}_wall_seconds"]) + gap
            < float(row[f"{share}_wall_seconds"])
            for row in both
        )
        share_wins = sum(
            float(row[f"{share}_wall_seconds"]) + gap
            < float(row[f"{no_share}_wall_seconds"])
            for row in both
        )
        lines.append(f"| {gap:.0f}s | {no_wins} | {share_wins} | {len(both) - no_wins - share_wins} |")
    ratios = [
        math.log(
            float(row[f"{share}_wall_seconds"])
            / float(row[f"{no_share}_wall_seconds"])
        )
        for row in both
        if float(row[f"{no_share}_wall_seconds"]) > 0
        and float(row[f"{share}_wall_seconds"]) > 0
    ]
    if ratios:
        no_total = sum(float(row[f"{no_share}_wall_seconds"]) for row in both)
        share_total = sum(float(row[f"{share}_wall_seconds"]) for row in both)
        lines += [
            "",
            f"Both-solved total time: {no_total:.1f}s without sharing, "
            f"{share_total:.1f}s with sharing.",
            f"Median sharing/no-sharing time ratio: {math.exp(statistics.median(ratios)):.3f}.",
        ]

    if args.manifest:
        models = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
        model_index = {
            (Path(model["path"]).stem, str(model["size_bytes"])): model
            for model in models
        }

        def tier(row: dict[str, str]) -> str:
            stem = row["name"].split("__")[-1]
            return str(model_index[(stem, row["size_bytes"])]["tier"])

        lines += [
            "", "## Difficulty tiers", "",
            "| Tier | Models | No sharing | Sharing | Sharing-only | No-sharing-only |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for tier_name in ("medium", "slow", "timeout"):
            tier_rows = [row for row in rows if tier(row) == tier_name]
            no_solved = sum(row[f"{no_share}_status"] in VALID for row in tier_rows)
            share_solved = sum(row[f"{share}_status"] in VALID for row in tier_rows)
            tier_share_only = sum(
                row[f"{share}_status"] in VALID and row[f"{no_share}_status"] not in VALID
                for row in tier_rows
            )
            tier_no_only = sum(
                row[f"{no_share}_status"] in VALID and row[f"{share}_status"] not in VALID
                for row in tier_rows
            )
            lines.append(
                f"| {tier_name} | {len(tier_rows)} | {no_solved} | {share_solved} | "
                f"{tier_share_only} | {tier_no_only} |"
            )

    lines += ["", f"Outcome conflicts: {conflicts}.", ""]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"rows={len(rows)} conflicts={conflicts} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
