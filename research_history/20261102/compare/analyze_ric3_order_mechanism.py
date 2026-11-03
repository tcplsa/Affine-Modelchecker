#!/usr/bin/env python3
"""Summarize paired BVE telemetry by performance category."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path


CANDIDATE = "ric3_product_sum_high"
REFERENCE = "ric3_legacy"
FIELDS = (
    ("bve_attempted", "BVE attempts"),
    ("bve_eliminated", "Variables eliminated"),
    ("bve_rejected_growth", "Growth rejections"),
    ("bve_removed_clauses", "Clauses removed"),
    ("bve_resolvents", "Kept resolvents"),
    ("bve_resolvent_literals", "Resolvent literals"),
    ("bve_merge_checks", "Estimated merge checks"),
    ("bve_output_clauses", "Residual clauses"),
    ("bve_output_literals", "Residual literals"),
    ("bve_max_resolvent_size", "Maximum resolvent width"),
    ("bve_simplify_seconds", "Simplification time"),
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def ratio(row: dict[str, str], field: str) -> float | None:
    candidate = row.get(f"{CANDIDATE}_{field}", "")
    reference = row.get(f"{REFERENCE}_{field}", "")
    if not candidate or not reference:
        return None
    candidate_value = float(candidate)
    reference_value = float(reference)
    if candidate_value <= 0 or reference_value <= 0:
        return None
    return candidate_value / reference_value


def main() -> int:
    args = arguments()
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    category = {model["id"]: model["category"] for model in selection["models"]}
    with args.input.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    categories = ("stable-fast", "stable-slow", "neutral", "candidate-coverage", "legacy-coverage")
    lines = [
        "# rIC3 BVE-order mechanism telemetry", "",
        f"Models: {len(rows)}. Values are product-sum-high / legacy geometric ratios; values below 1 mean less work.",
    ]
    for name in ("all", *categories):
        selected = rows if name == "all" else [row for row in rows if category.get(row["model_id"]) == name]
        lines += ["", f"## {name}", "", "| Observable | Ratio | Pairs |", "|---|---:|---:|"]
        for field, label in FIELDS:
            values = [value for row in selected if (value := ratio(row, field)) is not None]
            aggregate = math.exp(statistics.mean(map(math.log, values))) if values else math.nan
            lines.append(f"| {label} | {aggregate:.3f} | {len(values)} |")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows={len(rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
