#!/usr/bin/env python3
"""Build a deterministic cross-year representation/simplification benchmark."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_YEARS = ("2015", "2017", "2019", "2020", "2024", "2025")
TIER_COST = {"fast": 2.0, "medium": 20.0, "slow": 60.0, "timeout": 300.0}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", default=",".join(DEFAULT_YEARS))
    parser.add_argument("--per-cell", type=int, default=6)
    parser.add_argument(
        "--dataset-manifest", type=Path,
        default=SCRIPT_DIR / "results" / "initial_state_dataset_manifest60.tsv",
    )
    parser.add_argument(
        "--output", type=Path,
        default=SCRIPT_DIR / "results" / "representation_simplification_design_v1" / "manifest.json",
    )
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def spread_select(rows: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    """Select reproducible structural quantiles instead of random circuits."""
    ordered = sorted(rows, key=lambda row: (
        math.log1p(int(row["recognized_xors"])),
        float(row["and_reduction"]),
        float(row["next_xor_density"]),
        row["name"],
    ))
    if len(ordered) <= count:
        return ordered
    if count == 1:
        return [ordered[len(ordered) // 2]]
    indices = [round(index * (len(ordered) - 1) / (count - 1)) for index in range(count)]
    return [ordered[index] for index in indices]


def main() -> int:
    args = parse_args()
    years = [value.strip() for value in args.years.split(",") if value.strip()]
    dataset = read_tsv(args.dataset_manifest)
    selected: list[dict[str, object]] = []
    for year in years:
        features_path = SCRIPT_DIR / "results" / f"xag_struct_{year}.tsv"
        features = {row["name"]: row for row in read_tsv(features_path)}
        metadata = {
            row["name"]: row for row in dataset
            if row["year"] == year and row["duplicate"] == "0"
        }
        for tier in ("fast", "medium", "slow", "timeout"):
            candidates = []
            for name, row in metadata.items():
                feature = features.get(name)
                if row["tier"] != tier or feature is None:
                    continue
                if int(feature["recognized_xors"]) <= 0:
                    continue
                candidates.append({**feature, **row})
            for row in spread_select(candidates, args.per_cell):
                selected.append({
                    "id": f"{year}__{row['name']}",
                    "year": int(year),
                    "name": row["name"],
                    "family": row.get("family", row["name"]),
                    "path": str(Path(row["path"]).resolve()),
                    "tier": tier,
                    "baseline_status": row["status"],
                    "baseline_seconds": float(row["wall_seconds"] or 0.0),
                    "size_bytes": int(row["size_bytes"]),
                    "aig_ands": int(row["aig_ands"]),
                    "recognized_xors": int(row["recognized_xors"]),
                    "and_reduction": float(row["and_reduction"]),
                    "next_cone_xors": int(row["next_cone_xors"]),
                    "bad_cone_xors": int(row["bad_cone_xors"]),
                    "shared_cone_xors": int(row["shared_cone_xors"]),
                    "next_xor_density": float(row["next_xor_density"]),
                    "bad_xor_density": float(row["bad_xor_density"]),
                })

    loads = {"server-a": 0.0, "server-b": 0.0}
    for model in sorted(selected, key=lambda row: (-TIER_COST[str(row["tier"])], str(row["id"]))):
        shard = min(loads, key=lambda name: (loads[name], name))
        model["shard"] = shard
        loads[shard] += TIER_COST[str(model["tier"])]

    selected.sort(key=lambda row: (int(row["year"]), str(row["tier"]), str(row["name"])))
    payload = {
        "experiment": "representation_simplification_crossyear_v1",
        "version": 1,
        "selection": {
            "years": years,
            "tiers": ["fast", "medium", "slow", "timeout"],
            "per_cell": args.per_cell,
            "rule": "unique XOR-bearing structural quantiles; no random sampling",
        },
        "shard_loads": loads,
        "models": selected,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    counts: dict[tuple[int, str], int] = {}
    for model in selected:
        key = (int(model["year"]), str(model["tier"]))
        counts[key] = counts.get(key, 0) + 1
    print(f"models={len(selected)} shard_loads={loads} output={args.output}")
    print(" ".join(f"{year}/{tier}={count}" for (year, tier), count in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
