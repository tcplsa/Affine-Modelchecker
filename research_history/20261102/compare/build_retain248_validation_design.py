#!/usr/bin/env python3
"""Build a frozen, cross-year held-out validation set for retain248."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from extract_xor_gate_features import rows_for_model  # noqa: E402


EXCLUDED_NAMES = {
    "a16-p139",
    "yosyshq_appnote_123_veer_axi-p31",
    "zonotope_2",
}
EXCLUDED_PATH_MARKERS = (
    "/x-epic/a16-",
    "/appnote_123/veer_axi/",
    "/float-benchs/zonotope_2",
)
GROUP_WEIGHTS = {"fast": 5.0, "medium": 20.0, "slow": 60.0, "timeout": 600.0}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--years", default="2024,2025")
    parser.add_argument("--hard-per-year", type=int, default=80)
    parser.add_argument("--feature-workers", type=int, default=4)
    return parser.parse_args()


def load_structural_rows(year: int) -> dict[str, dict[str, str]]:
    path = SCRIPT_DIR / "results" / f"xag_struct_{year}.tsv"
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["name"]: row for row in csv.DictReader(handle, delimiter="\t")}


def excluded(row: dict[str, str]) -> bool:
    normalized = "/" + row["aig_path"].lstrip("/")
    return row["name"] in EXCLUDED_NAMES or any(
        marker in normalized for marker in EXCLUDED_PATH_MARKERS
    )


def evenly_spaced(rows: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    rows = sorted(rows, key=lambda row: (int(row["size_bytes"]), row["name"]))
    if count <= 0 or len(rows) <= count:
        return rows
    positions = [min(len(rows) - 1, int((index + 0.5) * len(rows) / count)) for index in range(count)]
    return [rows[position] for position in positions]


def tier_for(name: str, groups: dict[str, list[str]]) -> str:
    for tier in ("fast", "medium", "slow", "timeout"):
        if name in set(groups.get(f"{tier}_unique", [])):
            return tier
    raise ValueError(f"model is not in a supported group: {name}")


def retain248(rows: list[dict[str, str]]) -> tuple[set[int], set[int], dict[str, int]]:
    all_vars: set[int] = set()
    retained: set[int] = set()
    removed_buckets = {
        "f23_near_isolated": 0,
        "f23_near_adjacent": 0,
        "f23_far_isolated": 0,
    }
    parent_count = 0
    for row in rows:
        var = int(row["xor_var"])
        all_vars.add(var)
        fanout = int(row["fanout"])
        distance = int(row["distance_to_next"])
        adjacent = int(row["fanin_xor_count"]) + int(row["fanout_xor_count"]) > 0
        parent = (
            int(row["in_next"]) == 1
            and fanout >= 2
            and int(row["impl_child_external_fanouts"]) == 0
        )
        if parent:
            parent_count += 1
        keep = (
            not parent
            or fanout >= 4
            or (fanout in (2, 3) and distance > 8 and adjacent)
        )
        if keep:
            retained.add(var)
        elif distance <= 8 and adjacent:
            removed_buckets["f23_near_adjacent"] += 1
        elif distance <= 8:
            removed_buckets["f23_near_isolated"] += 1
        else:
            removed_buckets["f23_far_isolated"] += 1
    removed_buckets["parent_xors"] = parent_count
    return all_vars, retained, removed_buckets


def write_allowlist(path: Path, variables: set[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = sorted(variables) or [0]
    path.write_text("".join(f"{value}\n" for value in values), encoding="ascii")


def model_record(source: dict[str, Any], allowlist_dir: Path) -> dict[str, Any] | None:
    path = (Path("/home/wudl") / source["aig_path"]).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    rows = rows_for_model(path, support_limit=1)
    if not rows:
        return None
    all_vars, retained, bucket_counts = retain248(rows)
    removed = all_vars - retained
    if not removed:
        return None
    model_id = f"{source['year']}__{source['name']}"
    allowlist = allowlist_dir / f"{model_id}.allow"
    write_allowlist(allowlist, retained)
    return {
        "id": model_id,
        "name": source["name"],
        "year": source["year"],
        "family": source["family"],
        "group": source["group"],
        "path": str(path),
        "size_bytes": int(source["size_bytes"]),
        "total_xors": len(all_vars),
        "parent_xors": bucket_counts.pop("parent_xors"),
        "retained_xors": len(retained),
        "removed_xors": len(removed),
        "removed_buckets": bucket_counts,
        "allowlist": str(allowlist),
    }


def assign_shards(models: list[dict[str, Any]]) -> dict[str, float]:
    loads = {"server-a": 0.0, "server-b": 0.0}
    ordered = sorted(
        models,
        key=lambda model: (GROUP_WEIGHTS[model["group"]], model["size_bytes"]),
        reverse=True,
    )
    for model in ordered:
        shard = min(loads, key=lambda name: (loads[name], name))
        model["shard"] = shard
        loads[shard] += GROUP_WEIGHTS[model["group"]]
    models.sort(key=lambda model: (model["year"], model["group"], model["name"]))
    return loads


def main() -> int:
    args = parse_args()
    years = [int(value) for value in args.years.split(",") if value.strip()]
    if not years or args.hard_per_year < 0 or args.feature_workers < 1:
        raise SystemExit("invalid years, hard sample size, or worker count")

    candidates: list[dict[str, Any]] = []
    selection_counts: dict[str, dict[str, int]] = {}
    for year in years:
        group_path = SCRIPT_DIR / f"hwmcc{year}_groups_mc_60.json"
        group_data = json.loads(group_path.read_text(encoding="utf-8"))
        groups = group_data["groups"]
        structural = load_structural_rows(year)
        regular_names = set(groups["trainable_unique"])
        regular = [
            row for name, row in structural.items()
            if name in regular_names and int(row["recognized_xors"]) > 0 and not excluded(row)
        ]
        hard_names = set(groups["timeout_unique"])
        hard_pool = [
            row for name, row in structural.items()
            if name in hard_names and int(row["recognized_xors"]) > 0 and not excluded(row)
        ]
        hard = evenly_spaced(hard_pool, args.hard_per_year)
        selected = regular + hard
        for row in selected:
            candidates.append({
                **row,
                "year": year,
                "group": tier_for(row["name"], groups),
            })
        selection_counts[str(year)] = {
            "regular_with_xor": len(regular),
            "hard_pool_with_xor": len(hard_pool),
            "hard_static_sample": len(hard),
        }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    allowlist_dir = args.output_dir / "allowlists"
    models: list[dict[str, Any]] = []
    failures: list[str] = []
    # Gate-distance extraction is CPU-heavy Python; processes avoid serializing it on the GIL.
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.feature_workers) as pool:
        future_map = {
            pool.submit(model_record, source, allowlist_dir): source for source in candidates
        }
        completed = 0
        for future in concurrent.futures.as_completed(future_map):
            source = future_map[future]
            try:
                record = future.result()
                if record is not None:
                    models.append(record)
            except Exception as exc:  # Keep preparation auditable instead of silently shrinking it.
                failures.append(f"{source['year']}__{source['name']}: {exc}")
            completed += 1
            if completed % 25 == 0 or completed == len(candidates):
                print(f"features={completed}/{len(candidates)} retained_models={len(models)}", flush=True)

    loads = assign_shards(models)
    manifest = {
        "version": 1,
        "experiment": "retain248_crossyear_heldout",
        "frozen_rule": {
            "scope": "recognized XORs in next cone with fanout >=2 and private implementation",
            "keep": "all non-parent XORs; parent fanout>=4; parent fanout 2-3 iff distance_to_next>8 and XOR-adjacent",
            "remove": [
                "fanout_2_3__near_le8__isolated",
                "fanout_2_3__near_le8__adjacent",
                "fanout_2_3__far_gt8__isolated",
            ],
        },
        "selection": {
            "years": years,
            "regular": "all non-trivial <=60s unique models with recognized XORs",
            "hard": f"{args.hard_per_year} size-stratified old-MC 60s timeouts per year",
            "eligibility": "retain248 removes at least one recognized XOR",
            "excluded_phase5_names": sorted(EXCLUDED_NAMES),
            "excluded_phase5_direct_families": list(EXCLUDED_PATH_MARKERS),
            "counts_before_gate_filter": selection_counts,
            "feature_failures": failures,
        },
        "shard_loads": loads,
        "models": models,
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"models={len(models)} shard_a={sum(m['shard']=='server-a' for m in models)} "
          f"shard_b={sum(m['shard']=='server-b' for m in models)} failures={len(failures)}")
    print(f"manifest={manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
