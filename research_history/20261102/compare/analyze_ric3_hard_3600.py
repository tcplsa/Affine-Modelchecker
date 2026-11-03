#!/usr/bin/env python3
"""Classify the completed 3600-second stock rIC3 screen."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}
PREFIX = "stock_native_legacy4"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--result", required=True, action="append", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    source = json.loads(args.manifest.read_text(encoding="utf-8"))
    by_id = {str(model["id"]): model for model in source["models"]}
    rows: list[dict[str, str]] = []
    for result in args.result:
        with result.open("r", encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle, delimiter="\t"))

    completed = {row["model_id"]: row for row in rows}
    missing = sorted(set(by_id) - set(completed))
    frontier_ids = {
        model_id for model_id, row in completed.items()
        if row[f"{PREFIX}_status"] in VALID
    }
    hard_ids = set(completed) - frontier_ids

    def emit_manifest(filename: str, ids: set[str], tier: str) -> None:
        models = []
        for model_id in sorted(ids):
            model = dict(by_id[model_id])
            row = completed[model_id]
            model["hardness_tier"] = tier
            model["stock_ric3_3600"] = {
                "status": row[f"{PREFIX}_status"],
                "wall_seconds": float(row[f"{PREFIX}_wall_seconds"]),
                "replica": row[f"{PREFIX}_replica"],
            }
            models.append(model)
        payload = {
            "schema": "ric3-hardness-v1",
            "tier": tier,
            "source_manifest": str(args.manifest),
            "source_results": [str(path) for path in args.result],
            "models": models,
        }
        (args.output_dir / filename).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    emit_manifest("frontier_1800_3600.json", frontier_ids, "frontier_1800_3600")
    emit_manifest("ric3_4_hard_3600.json", hard_ids, "ric3_4_hard_3600")

    hard_family = Counter(str(by_id[i].get("family", "unknown")) for i in hard_ids)
    hard_year = Counter(str(by_id[i]["year"]) for i in hard_ids)
    lines = [
        "# Stock rIC3 3600-second hard-instance screen",
        "",
        f"- Input candidates: {len(by_id)}",
        f"- Completed: {len(completed)}",
        f"- Missing: {len(missing)}",
        f"- Frontier solves between 1800 and 3600 seconds: {len(frontier_ids)}",
        f"- rIC3-4 hard at 3600 seconds: {len(hard_ids)}",
        "",
        "## Hard cases by year",
        "",
        "| Year | Count |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {year} | {count} |" for year, count in sorted(hard_year.items()))
    lines.extend(["", "## Largest hard families", "", "| Family | Count |", "| --- | ---: |"])
    lines.extend(f"| `{family}` | {count} |" for family, count in hard_family.most_common(40))
    if missing:
        lines.extend(["", "## Missing model IDs", ""] + [f"- `{value}`" for value in missing])
    (args.output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"frontier={len(frontier_ids)} hard={len(hard_ids)} missing={len(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
