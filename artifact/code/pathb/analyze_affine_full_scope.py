#!/usr/bin/env python3
"""Analyze the full affine scope and freeze a long-limit confirmation set."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path


CONFIGS = ("mc_xag", "mc_affine_auto", "ric3_ic3", "ric3_4")


def solved(row: dict[str, str], config: str) -> bool:
    return row[f"{config}_status"] in {"SAFE", "UNSAFE"}


def evenly_spaced(rows: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    rows = sorted(rows, key=lambda row: (int(row["size_bytes"]), row["name"]))
    if len(rows) <= count:
        return rows
    if count == 1:
        return [rows[len(rows) // 2]]
    indices = {round(index * (len(rows) - 1) / (count - 1)) for index in range(count)}
    return [rows[index] for index in sorted(indices)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--confirmation", type=Path, required=True)
    args = parser.parse_args()
    with args.input.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    source = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]

    lines = [
        "# Full affine-datapath scope: 120-second screen",
        "",
        f"Models: {len(rows)}. All four configurations use the same external limit.",
        "MC configurations are single-lane; `ric3_4` is four independent stock-rIC3",
        "IC3 replicas with shared termination.",
        "",
        "| Scope | Models | MC XAG | MC affine auto | rIC3-1 | rIC3-4 | Auto-only vs rIC3-4 | rIC3-4-only |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for scope in ("target", "boundary", "all"):
        group = rows if scope == "all" else [row for row in rows if row["scope"] == scope]
        counts = [sum(solved(row, config) for row in group) for config in CONFIGS]
        auto_only = sum(solved(row, "mc_affine_auto") and not solved(row, "ric3_4") for row in group)
        ric3_only = sum(solved(row, "ric3_4") and not solved(row, "mc_affine_auto") for row in group)
        lines.append(
            f"| {scope} | {len(group)} | {counts[0]} | {counts[1]} | {counts[2]} | {counts[3]} | {auto_only} | {ric3_only} |"
        )

    lines += [
        "",
        "## Target families",
        "",
        "| Family | Models | MC XAG | MC auto | rIC3-4 | Auto solved / rIC3 timeout | rIC3 errors |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    target = [row for row in rows if row["scope"] == "target"]
    for family in sorted({row["family"] for row in target}):
        group = [row for row in target if row["family"] == family]
        lines.append(
            "| %s | %d | %d | %d | %d | %d | %d |"
            % (
                family,
                len(group),
                sum(solved(row, "mc_xag") for row in group),
                sum(solved(row, "mc_affine_auto") for row in group),
                sum(solved(row, "ric3_4") for row in group),
                sum(
                    solved(row, "mc_affine_auto")
                    and row["ric3_4_status"] == "TIMEOUT"
                    for row in group
                ),
                sum(row["ric3_4_status"] == "ERROR" for row in group),
            )
        )

    common = [row for row in target if solved(row, "mc_affine_auto") and solved(row, "ric3_4")]
    ratios = [
        float(row["mc_affine_auto_wall_seconds"]) / float(row["ric3_4_wall_seconds"])
        for row in common
    ]
    lines += [
        "",
        "## Runtime and validity",
        "",
        f"- Common target solves: {len(common)}.",
        f"- Geometric end-to-end wall ratio MC-auto/rIC3-4: {math.exp(sum(map(math.log, ratios)) / len(ratios)):.3f}.",
        f"- Median paired ratio: {statistics.median(ratios):.3f}.",
        f"- Outcome conflicts: {sum(row['outcome_conflict'] not in {'', '0'} for row in rows)}.",
        "- Stock rIC3 exits with code 2 on the generated LFSR family; these are",
        "  reported as unsupported/errors and are not counted as rIC3 timeouts.",
        "",
        "## Selector choices",
        "",
        f"Target: `{dict(Counter(row.get('mc_affine_auto_affine_auto_choice', '') for row in target))}`.",
        "",
        "The screen is followed by an 1,800-second stratified confirmation of",
        "models solved by MC-auto for which rIC3-4 actually timed out.",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    quotas = {
        ("target", "crc_frame_align"): 12,
        ("target", "crc_frame_lock"): 8,
        ("target", "scrambler_equiv"): 6,
        ("target", "syndrome_equiv"): 1,
        ("boundary", "affine_phase_sync"): 3,
    }
    selected: list[dict[str, str]] = []
    for key, quota in quotas.items():
        candidates = [
            row
            for row in rows
            if (row["scope"], row["family"]) == key
            and solved(row, "mc_affine_auto")
            and row["ric3_4_status"] == "TIMEOUT"
        ]
        selected.extend(evenly_spaced(candidates, quota))
    # TSV rows store only the stem; resolve through the unique manifest name.
    by_name = {model["name"]: model for model in source}
    confirmation_models = [by_name[row["name"]] for row in selected]
    args.confirmation.parent.mkdir(parents=True, exist_ok=True)
    args.confirmation.write_text(
        json.dumps(
            {
                "schema": 1,
                "description": "Stratified 1800-second rIC3 timeout confirmation",
                "models": confirmation_models,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"rows": len(rows), "confirmation": len(confirmation_models)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
