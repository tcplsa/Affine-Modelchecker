#!/usr/bin/env python3
"""Freeze a runtime-stratified selection for the rIC3 A/A noise control."""

from __future__ import annotations

import argparse
import csv
import glob
import json
import statistics
from collections import defaultdict
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}
BINS = (("fast", 2.0, 10.0, 17), ("medium", 10.0, 60.0, 17), ("slow", 60.0, 300.0, 14))


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-glob", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    by_model: dict[str, list[float]] = defaultdict(list)
    metadata: dict[str, dict[str, str]] = {}
    for path in sorted(glob.glob(args.input_glob)):
        with open(path, encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if row.get("ric3_legacy_status") not in VALID:
                    continue
                model_id = row["model_id"]
                by_model[model_id].append(float(row["ric3_legacy_wall_seconds"]))
                metadata[model_id] = {
                    "model_id": model_id,
                    "name": row["name"],
                    "family": row["family"],
                    "year": row["year"],
                }

    selected = []
    for tier, low, high, count in BINS:
        candidates = [
            (model_id, statistics.median(times))
            for model_id, times in by_model.items()
            if len(times) == 3 and low <= statistics.median(times) < high
        ]
        candidates.sort(key=lambda item: item[1])
        # Evenly cover the runtime interval instead of selecting only its easy edge.
        indices = [round(i * (len(candidates) - 1) / (count - 1)) for i in range(count)]
        for index in indices:
            model_id, median_seconds = candidates[index]
            selected.append({
                **metadata[model_id],
                "tier": tier,
                "historical_median_seconds": median_seconds,
            })

    data = {
        "description": "Frozen same-seed rIC3 A/A wall-clock noise control",
        "selection_rule": "three legacy solves; runtime-stratified 2-300 seconds",
        "models": selected,
        "ids": [model["model_id"] for model in selected],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"selected={len(selected)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
