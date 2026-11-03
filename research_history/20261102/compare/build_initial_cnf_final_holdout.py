#!/usr/bin/env python3
"""Build a second untouched holdout for AIG/XAG canonical-CNF validation."""

from __future__ import annotations

import json
from pathlib import Path

from build_initial_cnf_blind_validation import SOURCE, YEARS, diverse_pick


SCRIPT_DIR = Path(__file__).resolve().parent
EXCLUDES = (
    SCRIPT_DIR / "results" / "initial_cnf_factorial_design_v1" / "manifest.json",
    SCRIPT_DIR / "results" / "initial_cnf_blind_validation_design_v1" / "manifest.json",
)
OUTPUT = SCRIPT_DIR / "results" / "initial_cnf_final_holdout_design_v1" / "manifest.json"


def main() -> int:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    excluded: set[str] = set()
    for path in EXCLUDES:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        excluded.update(str(model["id"]) for model in manifest["models"])

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
            item["shard"] = "final-holdout"
            selected.append(item)

    payload = {
        "experiment": "initial_cnf_final_holdout_v1",
        "version": 1,
        "source": str(SOURCE),
        "excluded_manifests": [str(path) for path in EXCLUDES],
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
