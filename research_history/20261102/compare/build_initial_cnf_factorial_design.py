#!/usr/bin/env python3
"""Select a balanced cross-year set for input/CNF factorial experiments."""

from __future__ import annotations

import json
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE = SCRIPT_DIR / "results" / "representation_simplification_design_v1" / "manifest.json"
OUTPUT = SCRIPT_DIR / "results" / "initial_cnf_factorial_design_v1" / "manifest.json"
PICKS = {
    "medium": (0, 2, 5),
    "slow": (0, 2, 5),
    "timeout": (1, 4),
}


def main() -> int:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    grouped = {}
    for model in source["models"]:
        grouped.setdefault((model["year"], model["tier"]), []).append(model)
    selected = []
    for year in (2015, 2017, 2019, 2020, 2024, 2025):
        for tier in ("medium", "slow", "timeout"):
            models = sorted(grouped[(year, tier)], key=lambda model: (
                model["recognized_xors"], model["and_reduction"], model["name"],
            ))
            for index in PICKS[tier]:
                model = dict(models[index])
                model["shard"] = "current"
                selected.append(model)
    payload = {
        "experiment": "initial_cnf_factorial_v1",
        "version": 1,
        "source": str(SOURCE),
        "selection": {
            "models": len(selected),
            "per_year": 8,
            "tiers": {"medium": 3, "slow": 3, "timeout": 2},
            "randomized": False,
        },
        "models": selected,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"models={len(selected)} tasks={len(selected) * 2 * 2 * 3 * 4} output={OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
