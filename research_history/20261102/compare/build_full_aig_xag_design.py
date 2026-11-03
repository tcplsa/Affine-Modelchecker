#!/usr/bin/env python3
"""Build the deduplicated all-year AIG/XAG benchmark manifest."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
YEARS = ("2015", "2017", "2019", "2020", "2024", "2025")
TIER_ORDER = {"trivial": 0, "fast": 1, "medium": 2, "slow": 3, "timeout": 4, "error": 5}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def int_value(value: str) -> int:
    return int(value) if value else 0


def float_value(value: str) -> float:
    return float(value) if value else 0.0


def main() -> int:
    dataset_path = SCRIPT_DIR / "results" / "initial_state_dataset_manifest60.tsv"
    output = SCRIPT_DIR / "results" / "full_aig_xag_all_years_v1" / "manifest.json"
    dataset = [row for row in read_tsv(dataset_path) if row["duplicate"] == "0"]
    features = {
        (year, row["name"]): row
        for year in YEARS
        for row in read_tsv(SCRIPT_DIR / "results" / f"xag_struct_{year}.tsv")
    }
    models = []
    for row in dataset:
        feature = features[(row["year"], row["name"])]
        models.append({
            "id": f"{row['year']}__{row['name']}",
            "year": int(row["year"]),
            "name": row["name"],
            "family": feature.get("family", row["name"]),
            "path": str(Path(row["path"]).resolve()),
            "tier": row["tier"],
            "shard": "full",
            "baseline_status": row["status"],
            "baseline_seconds": float(row["wall_seconds"] or 0.0),
            "size_bytes": int(row["size_bytes"]),
            "aig_ands": int_value(feature["aig_ands"]),
            "recognized_xors": int_value(feature["recognized_xors"]),
            "and_reduction": float_value(feature["and_reduction"]),
            "next_cone_xors": int_value(feature["next_cone_xors"]),
            "bad_cone_xors": int_value(feature["bad_cone_xors"]),
            "shared_cone_xors": int_value(feature["shared_cone_xors"]),
            "next_xor_density": float_value(feature["next_xor_density"]),
            "bad_xor_density": float_value(feature["bad_xor_density"]),
        })
    models.sort(key=lambda model: (
        TIER_ORDER.get(str(model["tier"]), 99), int(model["year"]), str(model["name"]),
    ))
    payload = {
        "experiment": "full_aig_xag_all_years_v1",
        "version": 1,
        "selection": {
            "years": list(YEARS),
            "deduplicated": True,
            "models": len(models),
            "order": "historical runtime tier, year, name",
        },
        "models": models,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"models={len(models)} tasks={len(models) * 2} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
