#!/usr/bin/env python3
"""Build a deterministic, structurally diverse blind set for CNF/input validation."""

from __future__ import annotations

import json
import math
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE = SCRIPT_DIR / "results" / "full_aig_xag_all_years_v1" / "manifest.json"
TRAINING = SCRIPT_DIR / "results" / "initial_cnf_factorial_design_v1" / "manifest.json"
OUTPUT = SCRIPT_DIR / "results" / "initial_cnf_blind_validation_design_v1" / "manifest.json"
YEARS = (2015, 2017, 2019, 2020, 2024, 2025)
FEATURES = (
    "aig_ands", "recognized_xors", "and_reduction", "next_xor_density",
    "bad_xor_density", "shared_cone_xors", "baseline_seconds",
)


def feature_value(model: dict[str, object], feature: str) -> float:
    value = float(model.get(feature, 0.0))
    if feature in {"aig_ands", "recognized_xors", "shared_cone_xors", "baseline_seconds"}:
        return math.log1p(max(0.0, value))
    return value


def diverse_pick(models: list[dict[str, object]], count: int) -> list[dict[str, object]]:
    ordered = sorted(models, key=lambda model: str(model["id"]))
    columns = [[feature_value(model, feature) for model in ordered] for feature in FEATURES]
    bounds = [(min(column), max(column)) for column in columns]
    vectors = []
    for model in ordered:
        vector = []
        for feature, (low, high) in zip(FEATURES, bounds):
            value = feature_value(model, feature)
            vector.append((value - low) / (high - low) if high > low else 0.0)
        vectors.append(vector)

    centroid = [sum(vector[i] for vector in vectors) / len(vectors) for i in range(len(FEATURES))]
    first = min(
        range(len(ordered)),
        key=lambda i: (sum((vectors[i][j] - centroid[j]) ** 2 for j in range(len(FEATURES))), str(ordered[i]["id"])),
    )
    selected = [first]
    remaining = set(range(len(ordered))) - {first}
    while remaining and len(selected) < min(count, len(ordered)):
        next_index = max(
            remaining,
            key=lambda i: (
                min(sum((vectors[i][j] - vectors[k][j]) ** 2 for j in range(len(FEATURES))) for k in selected),
                str(ordered[i]["id"]),
            ),
        )
        selected.append(next_index)
        remaining.remove(next_index)
    return [ordered[index] for index in selected]


def main() -> int:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    training = json.loads(TRAINING.read_text(encoding="utf-8"))
    excluded = {str(model["id"]) for model in training["models"]}
    selected: list[dict[str, object]] = []
    counts: dict[str, dict[str, int]] = {}
    for year in YEARS:
        solved_pool = [
            model for model in source["models"]
            if int(model["year"]) == year
            and model["tier"] in {"medium", "slow"}
            and str(model["id"]) not in excluded
        ]
        timeout_pool = [
            model for model in source["models"]
            if int(model["year"]) == year
            and model["tier"] == "timeout"
            and str(model["id"]) not in excluded
        ]
        solved = diverse_pick(solved_pool, 20)
        timeout = diverse_pick(timeout_pool, 16)
        counts[str(year)] = {"medium_slow": len(solved), "timeout": len(timeout)}
        for model in solved + timeout:
            item = dict(model)
            item["shard"] = "blind"
            selected.append(item)

    payload = {
        "experiment": "initial_cnf_blind_validation_v1",
        "version": 1,
        "source": str(SOURCE),
        "excluded_training_manifest": str(TRAINING),
        "selection": {
            "models": len(selected),
            "randomized": False,
            "method": "normalized structural maximin",
            "per_year": counts,
        },
        "models": selected,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"models={len(selected)} tasks={len(selected) * 4 * 2} output={OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
