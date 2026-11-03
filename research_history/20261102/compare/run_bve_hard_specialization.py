#!/usr/bin/env python3
"""Test role-specific BVE orders and an order-diverse XAG portfolio on hard models."""

from __future__ import annotations

import argparse
import csv
import json
import signal
from collections import defaultdict
from pathlib import Path
from typing import Any

from compare_runner import ExperimentRunner


VALID = {"SAFE", "UNSAFE"}
BASELINES = ("aig_legacy4", "xag_legacy4", "xag_best4")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--baseline-inputs", nargs="+", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--seed", type=int, default=730001)
    parser.add_argument("--min-solved-runtime", type=float, default=300.0)
    parser.add_argument("--unknown-sample", type=int, default=42)
    parser.add_argument("--select-only", action="store_true")
    parser.add_argument(
        "--config-set",
        choices=("all", "role", "portfolio", "coverage", "role-replica", "observable"),
        default="all",
    )
    return parser.parse_args()


def read_baselines(paths: list[Path]) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                model_id = row.get("model_id") or row["name"]
                if model_id in rows:
                    raise ValueError(f"duplicate baseline model {model_id}")
                rows[model_id] = row
    return rows


def solved(row: dict[str, str], config: str) -> bool:
    return row.get(f"{config}_status") in VALID


def stable_unknown_sample(
    models: list[dict[str, Any]], count: int,
) -> list[dict[str, Any]]:
    """Round-robin years and families so exploration is not one-family dominated."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for model in models:
        groups[(str(model["year"]), str(model.get("family", model["id"])))].append(model)
    for values in groups.values():
        values.sort(key=lambda model: model["id"])
    keys = sorted(groups)
    selected: list[dict[str, Any]] = []
    offset = 0
    while keys and len(selected) < count:
        key = keys[offset % len(keys)]
        selected.append(groups[key].pop(0))
        if not groups[key]:
            keys.remove(key)
            offset -= 1
        offset += 1
    return selected


def select_models(
    manifest: dict[str, Any], baselines: dict[str, dict[str, str]],
    min_runtime: float, unknown_count: int,
) -> list[dict[str, Any]]:
    by_id = {model["id"]: model for model in manifest["models"]}
    informative: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    for model_id, row in baselines.items():
        if row.get("tier") != "timeout" or model_id not in by_id:
            continue
        statuses = [solved(row, config) for config in BASELINES]
        if any(statuses):
            solved_times = [
                float(row[f"{config}_wall_seconds"])
                for config, is_solved in zip(BASELINES, statuses) if is_solved
            ]
            if not all(statuses) or max(solved_times) >= min_runtime:
                informative.append(by_id[model_id])
        else:
            unknown.append(by_id[model_id])
    selected = informative + stable_unknown_sample(unknown, unknown_count)
    selected.sort(key=lambda model: (str(model["year"]), model["id"]))
    return selected


def make_config(
    ident: str, label: str, binary: Path, translation: str = "",
    lift: str = "", lane_orders: str = "", forward_aig: int = 0,
    forward_xag: int = 4,
) -> dict[str, Any]:
    return {
        "id": ident,
        "label": label,
        "kind": "mc",
        "binary": str(binary),
        "forward_aig": forward_aig,
        "forward_xag": forward_xag,
        "ctg_depth": 1,
        "deterministic_lanes": True,
        "preprocessor": "minisat",
        "minisat_elim_order": "legacy",
        "minisat_elim_order_lanes": lane_orders,
        "minisat_translation_elim_order": translation,
        "minisat_lift_elim_order": lift,
    }


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    baselines = read_baselines(args.baseline_inputs)
    if args.selection.exists():
        selected_ids = set(json.loads(args.selection.read_text(encoding="utf-8"))["ids"])
        models = [model for model in manifest["models"] if model["id"] in selected_ids]
    else:
        models = select_models(
            manifest, baselines, args.min_solved_runtime, args.unknown_sample,
        )
        args.selection.parent.mkdir(parents=True, exist_ok=True)
        args.selection.write_text(json.dumps({
            "description": "Hard BVE role-split set frozen before candidate runs",
            "min_solved_runtime": args.min_solved_runtime,
            "unknown_sample": args.unknown_sample,
            "ids": [model["id"] for model in models],
        }, indent=2) + "\n", encoding="utf-8")
    models.sort(key=lambda model: (str(model["year"]), model["id"]))
    if args.select_only:
        print(f"selected={len(models)} selection={args.selection}")
        return 0

    role_configs = [
        make_config(
            "xag_translation_sum_lift_legacy4",
            "4xXAG translation=sum-high lift=legacy", args.binary,
            translation="sum-high", lift="legacy",
        ),
        make_config(
            "xag_translation_legacy_lift_sum4",
            "4xXAG translation=legacy lift=sum-high", args.binary,
            translation="legacy", lift="sum-high",
        ),
    ]
    portfolio_configs = [
        make_config(
            "xag_split_order4",
            "4xXAG seed-mapped legacy/sum-high portfolio", args.binary,
            lane_orders="sum-high,legacy,legacy,sum-high",
        ),
    ]
    coverage_configs = [
        make_config(
            "xag_role3_legacy1",
            "3xXAG role + 1xXAG legacy rescue", args.binary,
            translation="legacy",
            lane_orders="sum-high,sum-high,sum-high,legacy",
        ),
        make_config(
            "aig1_xag_role3",
            "1xAIG legacy + 3xXAG role", args.binary,
            translation="legacy",
            lane_orders="legacy,sum-high,sum-high,sum-high",
            forward_aig=1, forward_xag=3,
        ),
        make_config(
            "aig1_xag_role2_legacy1",
            "1xAIG legacy + 2xXAG role + 1xXAG legacy", args.binary,
            translation="legacy",
            lane_orders="legacy,sum-high,sum-high,legacy",
            forward_aig=1, forward_xag=3,
        ),
    ]
    role_replica_configs = [
        make_config(
            "xag_role4_replica",
            "4xXAG translation=legacy lift=sum-high seed replica", args.binary,
            translation="legacy", lift="sum-high",
        ),
    ]
    observable_configs = [
        make_config(
            "xag_observe_legacy4",
            "4xXAG observed translation=legacy lift=legacy", args.binary,
            translation="legacy", lift="legacy",
        ),
        make_config(
            "xag_observe_role4",
            "4xXAG observed translation=legacy lift=sum-high", args.binary,
            translation="legacy", lift="sum-high",
        ),
    ]
    config_sets = {
        "role": role_configs,
        "portfolio": portfolio_configs,
        "coverage": coverage_configs,
        "role-replica": role_replica_configs,
        "observable": observable_configs,
        "all": role_configs + portfolio_configs,
    }
    configs = config_sets[args.config_set]
    metadata = {
        model["path"]: {
            "year": model["year"],
            "tier": model.get("tier", "unknown"),
            "group": model.get("tier", "unknown"),
            "model_id": model["id"],
            "family": model.get("family", model["id"]),
        }
        for model in models
    }

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            lanes_per_model = sum(
                int(config.get("forward_aig", 0))
                + int(config.get("forward_xag", 0))
                for config in configs
            )
            print(
                f"models={event['total']} configs={len(configs)} workers={args.workers} "
                f"logical_cores={lanes_per_model * args.workers} "
                f"timeout={args.timeout:g}", flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            total = int(event["total"])
            if completed % 5 == 0 or completed == total:
                print(f"completed={completed}/{total}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed",
        "group": "bve-hard-specialization",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": [model["path"] for model in models],
        "model_metadata": metadata,
        "metadata_fields": ["model_id", "family", "tier"],
        "output": str(args.output),
        "timeout": args.timeout,
        "workers": args.workers,
        "skip_existing": True,
        "mc_seed": args.seed,
        "configs": configs,
    }, progress)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    result = runner.run()
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
