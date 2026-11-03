#!/usr/bin/env python3
"""Build two disjoint cross-year manifests for variable-order experiments."""

from __future__ import annotations

import json
from pathlib import Path

from build_initial_cnf_blind_validation import YEARS, diverse_pick


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "results" / "full_aig_xag_all_years_v1" / "manifest.json"
FINAL = ROOT / "results" / "initial_cnf_final_holdout_design_v1" / "manifest.json"
OUT_ROOT = ROOT / "results" / "variable_order_overnight_design_v1"


def main() -> int:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))["models"]
    excluded = {
        str(model["id"])
        for model in json.loads(FINAL.read_text(encoding="utf-8"))["models"]
    }
    shards: dict[str, list[dict[str, object]]] = {"server-b": [], "server-c": []}
    counts: dict[str, dict[str, dict[str, int]]] = {name: {} for name in shards}
    for year in YEARS:
        eligible = [
            model for model in source
            if int(model["year"]) == year and str(model["id"]) not in excluded
        ]
        solved = diverse_pick(
            [model for model in eligible if model["tier"] in {"medium", "slow"}], 60
        )
        timeout = diverse_pick(
            [model for model in eligible if model["tier"] == "timeout"], 60
        )
        for index, model in enumerate(solved):
            shard = "server-b" if index % 2 == 0 else "server-c"
            item = dict(model)
            item["shard"] = shard
            shards[shard].append(item)
        for index, model in enumerate(timeout):
            shard = "server-c" if index % 2 == 0 else "server-b"
            item = dict(model)
            item["shard"] = shard
            shards[shard].append(item)
        for shard in shards:
            counts[shard][str(year)] = {
                "medium_slow": sum(
                    int(model["year"]) == year and model["tier"] in {"medium", "slow"}
                    for model in shards[shard]
                ),
                "timeout": sum(
                    int(model["year"]) == year and model["tier"] == "timeout"
                    for model in shards[shard]
                ),
            }

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    for shard, models in shards.items():
        payload = {
            "experiment": "variable_order_overnight_v1",
            "version": 1,
            "source": str(SOURCE),
            "excluded_manifest": str(FINAL),
            "selection": {
                "models": len(models),
                "method": "normalized structural maximin, alternating disjoint shards",
                "per_year": counts[shard],
            },
            "models": sorted(models, key=lambda model: (int(model["year"]), str(model["id"]))),
        }
        output = OUT_ROOT / f"manifest_{shard}.json"
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"{shard}: models={len(models)} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
