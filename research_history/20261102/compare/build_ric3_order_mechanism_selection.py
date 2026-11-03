#!/usr/bin/env python3
"""Select stable wins, losses, neutral cases, and coverage-discordant models."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}
CANDIDATE = "ric3_product_sum_high"
REFERENCE = "ric3_legacy"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--inputs", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--per-runtime-group", type=int, default=24)
    parser.add_argument("--per-coverage-group", type=int, default=12)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    source = json.loads(args.selection.read_text(encoding="utf-8"))
    metadata = {model["id"]: model for model in source["models"]}
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for path in args.inputs:
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                grouped[row["model_id"]].append(row)
    runtime = []
    coverage = []
    for model_id, rows in grouped.items():
        ratios = []
        candidate_only = 0
        reference_only = 0
        for row in rows:
            candidate_ok = row[f"{CANDIDATE}_status"] in VALID
            reference_ok = row[f"{REFERENCE}_status"] in VALID
            candidate_only += candidate_ok and not reference_ok
            reference_only += reference_ok and not candidate_ok
            if candidate_ok and reference_ok:
                ratios.append(
                    float(row[f"{CANDIDATE}_wall_seconds"])
                    / float(row[f"{REFERENCE}_wall_seconds"])
                )
        if len(ratios) >= 2:
            runtime.append((statistics.median(map(math.log, ratios)), model_id, len(ratios)))
        if candidate_only != reference_only:
            coverage.append((candidate_only - reference_only, model_id, candidate_only, reference_only))
    runtime.sort()
    selected: dict[str, str] = {}
    n = args.per_runtime_group
    for _score, model_id, _count in runtime[:n]:
        selected[model_id] = "stable-fast"
    for _score, model_id, _count in runtime[-n:]:
        selected[model_id] = "stable-slow"
    for _score, model_id, _count in sorted(runtime, key=lambda item: abs(item[0]))[:n]:
        selected.setdefault(model_id, "neutral")
    candidate_coverage = sorted((item for item in coverage if item[0] > 0), reverse=True)
    legacy_coverage = sorted(item for item in coverage if item[0] < 0)
    for _delta, model_id, _only, _lost in candidate_coverage[:args.per_coverage_group]:
        selected[model_id] = "candidate-coverage"
    for _delta, model_id, _only, _lost in legacy_coverage[:args.per_coverage_group]:
        selected[model_id] = "legacy-coverage"
    models = []
    for model_id, category in selected.items():
        model = dict(metadata[model_id])
        model["category"] = category
        models.append(model)
    models.sort(key=lambda model: (model["category"], model["id"]))
    payload = {
        "version": 1,
        "description": "Mechanism sample selected from three-seed concurrent order validation",
        "ids": [model["id"] for model in models],
        "models": models,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"selected={len(models)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
