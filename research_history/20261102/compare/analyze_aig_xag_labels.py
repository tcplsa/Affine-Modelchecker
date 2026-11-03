#!/usr/bin/env python3
"""Summarize direct multi-seed AIG/full-XAG measurements."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", nargs="+", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--timeout-multiplier", type=float, default=1.5)
    parser.add_argument("--min-gap", type=float, default=2.0)
    return parser.parse_args()


def number(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def main() -> int:
    args = parse_args()
    rows = []
    for path in args.results:
        design = json.loads(path.with_name(path.stem + "_design.json").read_text(encoding="utf-8"))
        seed = int(design["solver_seed"])
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                penalty = number(row.get("timeout_seconds", "300"), 300.0) * args.timeout_multiplier
                aig_solved = row.get("state_000_status") in SOLVED
                xag_solved = row.get("state_001_status") in SOLVED
                aig = number(row.get("state_000_wall_seconds", ""), penalty) if aig_solved else penalty
                xag = number(row.get("state_001_wall_seconds", ""), penalty) if xag_solved else penalty
                rows.append({
                    "seed": seed,
                    "name": row["name"],
                    "aig": aig,
                    "xag": xag,
                    "aig_solved": aig_solved,
                    "xag_solved": xag_solved,
                    "conflict": row.get("outcome_conflict") == "1",
                })
    summaries = []
    for scope, members in [("all", rows)] + [
        (f"seed{seed}", [row for row in rows if row["seed"] == seed])
        for seed in sorted({row["seed"] for row in rows})
    ]:
        aig_total = sum(row["aig"] for row in members)
        xag_total = sum(row["xag"] for row in members)
        jointly = [row for row in members if row["aig_solved"] and row["xag_solved"]]
        jointly_aig = sum(row["aig"] for row in jointly)
        jointly_xag = sum(row["xag"] for row in jointly)
        summaries.append({
            "scope": scope,
            "samples": len(members),
            "xag_gain_percent": 100.0 * (aig_total - xag_total) / aig_total if aig_total else 0.0,
            "joint_gain_percent": 100.0 * (jointly_aig - jointly_xag) / jointly_aig if jointly_aig else 0.0,
            "xag_wins": sum(row["aig"] - row["xag"] > args.min_gap for row in members),
            "aig_wins": sum(row["xag"] - row["aig"] > args.min_gap for row in members),
            "aig_only": sum(row["aig_solved"] and not row["xag_solved"] for row in members),
            "xag_only": sum(row["xag_solved"] and not row["aig_solved"] for row in members),
            "both_solved": len(jointly),
            "both_timeout": sum(not row["aig_solved"] and not row["xag_solved"] for row in members),
            "conflicts": sum(row["conflict"] for row in members),
        })
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "summary.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(summaries)
    lines = [
        "# AIG versus XAG Labels",
        "",
        "| Scope | Samples | XAG gain | Joint gain | XAG/AIG wins | AIG-only/XAG-only | Both timeout |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summaries:
        lines.append(
            f"| {row['scope']} | {row['samples']} | {row['xag_gain_percent']:.3f}% | "
            f"{row['joint_gain_percent']:.3f}% | {row['xag_wins']}/{row['aig_wins']} | "
            f"{row['aig_only']}/{row['xag_only']} | {row['both_timeout']} |"
        )
    (args.output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows={len(rows)} output={args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

