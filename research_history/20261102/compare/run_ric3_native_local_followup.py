#!/usr/bin/env python3
"""Run a paired, disjoint-seed ablation of rIC3 native-local BVE ordering."""

from __future__ import annotations

import argparse
import csv
import json
import random
import signal
from collections import defaultdict
from pathlib import Path
from typing import Any

from compare_runner import ExperimentRunner


VALID = {"SAFE", "UNSAFE"}
BASELINE_CONFIGS = ("native_legacy4", "native_product_high4", "native_local4")
ORDERS = (
    ("legacy4_seed2", "legacy"),
    ("product_high4_seed2", "product-high"),
    ("product_sum_high4_seed2", "product-sum-high"),
    ("native_boundary4_seed2", "native-boundary"),
    ("native_local4_seed2", "native-local"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--baseline-inputs", nargs="+", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--seed", type=int, default=930001)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--hard-common", type=int, default=27)
    parser.add_argument("--unknown", type=int, default=30)
    return parser.parse_args()


def load_baselines(paths: list[Path]) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                model_id = row["model_id"]
                if model_id in rows:
                    raise ValueError(f"duplicate baseline row: {model_id}")
                rows[model_id] = row
    return rows


def diverse_take(
    rows: list[dict[str, str]], count: int, score: Any, seed: int,
) -> list[dict[str, str]]:
    """Prefer one model per year/family before filling remaining slots."""
    rng = random.Random(seed)
    shuffled = list(rows)
    rng.shuffle(shuffled)
    ordered = sorted(shuffled, key=score, reverse=True)
    selected: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in ordered:
        key = (row["year"], row.get("family", row["model_id"]))
        if key not in seen:
            selected.append(row)
            seen.add(key)
            if len(selected) == count:
                return selected
    selected_ids = {row["model_id"] for row in selected}
    selected.extend(row for row in ordered if row["model_id"] not in selected_ids)
    return selected[:count]


def create_selection(
    baselines: dict[str, dict[str, str]], hard_common: int, unknown: int,
) -> dict[str, Any]:
    def solved(row: dict[str, str], config: str) -> bool:
        return row.get(f"{config}_status") in VALID

    rows = list(baselines.values())
    solve_counts = {
        row["model_id"]: sum(solved(row, config) for config in BASELINE_CONFIGS)
        for row in rows
    }
    discordant = sorted(
        (row for row in rows if solve_counts[row["model_id"]] in (1, 2)),
        key=lambda row: (row["year"], row["model_id"]),
    )
    common = [row for row in rows if solve_counts[row["model_id"]] == 3]
    common_selected = diverse_take(
        common,
        hard_common,
        lambda row: min(float(row[f"{config}_wall_seconds"]) for config in BASELINE_CONFIGS),
        930027,
    )
    unsolved = [row for row in rows if solve_counts[row["model_id"]] == 0]
    unknown_selected = diverse_take(
        unsolved,
        unknown,
        lambda row: (float(row.get("size_bytes", 0)), row["model_id"]),
        930030,
    )
    buckets = {
        "baseline_discordant": [row["model_id"] for row in discordant],
        "hard_common": [row["model_id"] for row in common_selected],
        "all_baseline_unsolved": [row["model_id"] for row in unknown_selected],
    }
    ids = [model_id for values in buckets.values() for model_id in values]
    if len(ids) != len(set(ids)):
        raise ValueError("selection buckets overlap")
    return {
        "description": (
            "Frozen rIC3 native-local follow-up: all 43 baseline-discordant models, "
            "27 family-diverse hard common solves, and 30 family-diverse models "
            "unsolved by all three original BVE orders."
        ),
        "baseline_configs": list(BASELINE_CONFIGS),
        "buckets": buckets,
        "ids": ids,
    }


def config(ident: str, order: str, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "id": ident,
        "label": f"rIC3-4 Native {order} seed2",
        "kind": "ric3",
        "binary": str(args.binary),
        "engine": "ic3",
        "aig_encoding": "native",
        "replicas": 4,
        "seed": args.seed,
        "global_args": f"--bve-order {order}",
    }


def main() -> int:
    args = parse_args()
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise SystemExit("shard index must be in [0, shard count)")
    baselines = load_baselines(args.baseline_inputs)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    manifest_models = {model["id"]: model for model in manifest["models"]}
    if args.selection.exists():
        selection = json.loads(args.selection.read_text(encoding="utf-8"))
    else:
        selection = create_selection(baselines, args.hard_common, args.unknown)
        args.selection.parent.mkdir(parents=True, exist_ok=True)
        args.selection.write_text(json.dumps(selection, indent=2) + "\n", encoding="utf-8")
    selected_ids = [
        model_id for offset, model_id in enumerate(selection["ids"])
        if offset % args.shard_count == args.shard_index
    ]
    models = [manifest_models[model_id] for model_id in selected_ids]
    bucket_by_id = {
        model_id: bucket
        for bucket, ids in selection["buckets"].items()
        for model_id in ids
    }
    metadata = {
        model["path"]: {
            "year": model["year"],
            "group": bucket_by_id[model["id"]],
            "model_id": model["id"],
            "family": model.get("family", model["id"]),
            "tier": model.get("tier", "unknown"),
        }
        for model in models
    }
    configs = [config(ident, order, args) for ident, order in ORDERS]

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                f"shard={args.shard_index}/{args.shard_count} models={event['total']} "
                f"configs={len(configs)} workers={args.workers} "
                f"max_cores={20 * args.workers} seed={args.seed}",
                flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            if completed % 5 == 0 or completed == int(event["total"]):
                print(f"completed={completed}/{event['total']}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed",
        "group": "ric3-native-local-followup",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": [model["path"] for model in models],
        "model_metadata": metadata,
        "metadata_fields": ["model_id", "family", "tier"],
        "output": str(args.output),
        "timeout": args.timeout,
        "workers": args.workers,
        "skip_existing": True,
        "configs": configs,
    }, progress)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    result = runner.run()
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
