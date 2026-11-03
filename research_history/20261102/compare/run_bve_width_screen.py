#!/usr/bin/env python3
"""Screen width-weighted BVE on a frozen hard set."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from compare_runner import ExperimentRunner
from run_bve_full_campaign import balanced_shard


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", choices=("mc", "ric3"), required=True)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--weights", nargs="+", type=int, default=(0, 1, 2, 4))
    parser.add_argument("--seed", type=int, default=930001)
    parser.add_argument("--workers", type=int, default=7)
    parser.add_argument("--replicas", type=int, default=4)
    parser.add_argument("--bve-order", default="product-sum-high")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    return parser.parse_args()


def mc_config(binary: Path, weight: int) -> dict[str, object]:
    return {
        "id": f"mc_width_w{weight}",
        "label": f"MC 4xXAG role-aware width={weight}",
        "kind": "mc",
        "binary": str(binary),
        "mode": "xag",
        "direction": "forward",
        "forward_aig": 0,
        "forward_xag": 4,
        "deterministic_lanes": True,
        "ctg_depth": 1,
        "minisat_elim_order": "legacy",
        "minisat_translation_elim_order": "legacy",
        "minisat_lift_elim_order": "sum-high",
        "minisat_translation_width_weight": 0,
        "minisat_lift_width_weight": weight,
    }


def ric3_config(
    binary: Path, weight: int, seed: int, replicas: int, bve_order: str,
) -> dict[str, object]:
    return {
        "id": f"ric3_width_w{weight}",
        "label": f"rIC3 Native {bve_order} width={weight}",
        "kind": "ric3",
        "binary": str(binary),
        "engine": "ic3",
        "aig_encoding": "native",
        "global_args": f"--bve-order {bve_order}",
        "bve_width_weight": weight,
        "replicas": replicas,
        "seed": seed,
    }


def main() -> int:
    args = arguments()
    if any(weight < 0 for weight in args.weights):
        raise SystemExit("weights must be non-negative")
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise SystemExit("shard index must be in [0, shard count)")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    selected_ids = set(json.loads(args.selection.read_text(encoding="utf-8"))["ids"])
    selected = [model for model in manifest["models"] if model["id"] in selected_ids]
    selected = balanced_shard(selected, args.shard_index, args.shard_count)
    configs = [
        mc_config(args.binary, weight) if args.tool == "mc"
        else ric3_config(args.binary, weight, args.seed, args.replicas, args.bve_order)
        for weight in args.weights
    ]
    metadata = {
        model["path"]: {
            "model_id": model["id"],
            "family": model.get("family", model["id"]),
            "tier": model.get("tier", "unknown"),
            "seed_block": args.seed,
        }
        for model in selected
    }

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                f"tool={args.tool} shard={args.shard_index}/{args.shard_count} "
                f"models={event['total']} configs={len(configs)} workers={args.workers} "
                f"seed={args.seed} timeout={args.timeout:g}", flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            total = int(event["total"])
            if completed % 5 == 0 or completed == total:
                print(f"completed={completed}/{total}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed",
        "group": f"bve-width-{args.tool}",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": [model["path"] for model in selected],
        "model_metadata": metadata,
        "metadata_fields": ["model_id", "family", "tier", "seed_block"],
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
