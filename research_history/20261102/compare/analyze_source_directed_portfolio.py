#!/usr/bin/env python3
"""Analyze source-directed predecessor portfolio retention."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from run_source_directed_portfolio import POLICIES


VALID = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = list(csv.DictReader(args.input.open(encoding="utf-8"), delimiter="\t"))
    models = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    model_index = {
        (Path(model["path"]).stem, str(model["size_bytes"])): model
        for model in models
    }

    def model(row: dict[str, str]) -> dict[str, object]:
        return model_index[(row["name"].split("__")[-1], row["size_bytes"])]

    def solved(row: dict[str, str], cfg: str) -> bool:
        return row[f"{cfg}_status"] in VALID

    baseline = POLICIES[0][0]
    baseline_count = sum(solved(row, baseline) for row in rows)
    lines = [
        "# Source-directed predecessor portfolio", "", f"Models: {len(rows)}.", "",
        "| Configuration | Solved | SAFE | UNSAFE | Penalized cost | Net |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for cfg, label, _lanes in POLICIES:
        count = sum(solved(row, cfg) for row in rows)
        safe = sum(row[f"{cfg}_status"] == "SAFE" for row in rows)
        unsafe = sum(row[f"{cfg}_status"] == "UNSAFE" for row in rows)
        cost = sum(
            float(row[f"{cfg}_wall_seconds"])
            if solved(row, cfg) else 1.5 * float(row["timeout_seconds"])
            for row in rows
        )
        lines.append(
            f"| {label} | {count} | {safe} | {unsafe} | {cost:.1f} | "
            f"{count - baseline_count:+d} |"
        )

    lines += [
        "", "## Paired against default", "",
        "| Configuration | Candidate-only | Default-only | Wins >2s | Losses >2s |",
        "|---|---:|---:|---:|---:|",
    ]
    for cfg, label, _lanes in POLICIES[1:]:
        candidate_only = [row for row in rows if solved(row, cfg) and not solved(row, baseline)]
        default_only = [row for row in rows if solved(row, baseline) and not solved(row, cfg)]
        both = [row for row in rows if solved(row, baseline) and solved(row, cfg)]
        wins = sum(
            float(row[f"{cfg}_wall_seconds"]) + 2.0
            < float(row[f"{baseline}_wall_seconds"])
            for row in both
        )
        losses = sum(
            float(row[f"{baseline}_wall_seconds"]) + 2.0
            < float(row[f"{cfg}_wall_seconds"])
            for row in both
        )
        lines.append(
            f"| {label} | {len(candidate_only)} | {len(default_only)} | {wins} | {losses} |"
        )
        if candidate_only:
            lines.append(
                f"\nCandidate-only ({label}): "
                + ", ".join(str(model(row)["id"]) for row in candidate_only)
                + "."
            )
        if default_only:
            lines.append(
                f"\nDefault-only ({label}): "
                + ", ".join(str(model(row)["id"]) for row in default_only)
                + "."
            )

    lines += [
        "", "## Difficulty tiers", "",
        "| Configuration | Medium | Slow | Timeout |",
        "|---|---:|---:|---:|",
    ]
    for cfg, label, _lanes in POLICIES:
        counts = [
            sum(
                solved(row, cfg)
                for row in rows if model(row)["tier"] == tier_name
            )
            for tier_name in ("medium", "slow", "timeout")
        ]
        lines.append(f"| {label} | {counts[0]} | {counts[1]} | {counts[2]} |")

    conflicts = sum(row.get("outcome_conflict") == "1" for row in rows)
    lines += ["", f"Outcome conflicts: {conflicts}.", ""]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"rows={len(rows)} conflicts={conflicts} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
