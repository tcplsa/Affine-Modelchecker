#!/usr/bin/env python3
"""Run the preregistered AIG-hard BVE domain experiment in MC or rIC3."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from compare_runner import ExperimentRunner


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--tool", choices=("mc", "ric3"), required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--domain", choices=("all", "rich", "poor"), default="all")
    return parser.parse_args()


def mc_config(binary: Path, order: str) -> dict[str, object]:
    config_id = {
        "legacy": "mc_legacy4",
        "high": "mc_high4",
        "sum-high": "mc_sumhigh4",
    }[order]
    return {
        "id": config_id,
        "label": f"MC 4xXAG {order}",
        "kind": "mc",
        "binary": str(binary),
        "forward_xag": 4,
        "ctg_depth": 1,
        "deterministic_lanes": True,
        "minisat_elim_order": order,
    }


def mc_aig_config(binary: Path) -> dict[str, object]:
    return {
        "id": "mc_aig4",
        "label": "MC 4xAIG legacy",
        "kind": "mc",
        "binary": str(binary),
        "forward_aig": 4,
        "ctg_depth": 1,
        "deterministic_lanes": True,
        "minisat_elim_order": "legacy",
    }


def ric3_config(binary: Path, order: str, seed: int) -> dict[str, object]:
    config_id = {
        "legacy": "ric3_legacy4",
        "product-high": "ric3_high4",
        "product-sum-high": "ric3_sumhigh4",
    }[order]
    return {
        "id": config_id,
        "label": f"rIC3 Native {order}",
        "kind": "ric3",
        "binary": str(binary),
        "engine": "ic3",
        "aig_encoding": "native",
        "global_args": f"--bve-order {order}",
        "bve_width_weight": 0,
        "replicas": 4,
        "seed": seed,
    }


def ric3_aig_config(binary: Path, seed: int) -> dict[str, object]:
    return {
        "id": "ric3_aig4",
        "label": "rIC3 AIG legacy",
        "kind": "ric3",
        "binary": str(binary),
        "engine": "ic3",
        "aig_encoding": "aig",
        "global_args": "--bve-order legacy",
        "bve_width_weight": 0,
        "replicas": 4,
        "seed": seed,
    }


def main() -> int:
    args = arguments()
    if not 0 <= args.shard_index < args.shard_count:
        raise SystemExit("shard index must be in [0, shard count)")
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    models = selection["models"]
    if args.domain != "all":
        suffix = "xor-rich" if args.domain == "rich" else "xor-poor"
        models = [model for model in models if str(model["domain"]).endswith(suffix)]
    models = [
        model for index, model in enumerate(models)
        if index % args.shard_count == args.shard_index
    ]
    metadata = {
        str(model["path"]): {
            "model_id": model["id"],
            "family": model["family"],
            "tier": model["tier"],
            "domain": model["domain"],
            "match_id": model["match_id"],
            "baseline_status": model["baseline_status"],
            "baseline_seconds": model["baseline_seconds"],
            "bad_xor_density": model["bad_xor_density"],
            "aig_ands": model["aig_ands"],
            "seed_block": args.seed,
        }
        for model in models
    }
    if args.tool == "mc":
        configs = [mc_aig_config(args.binary)] + [
            mc_config(args.binary, order) for order in ("legacy", "high", "sum-high")
        ]
    else:
        configs = [ric3_aig_config(args.binary, args.seed)] + [
            ric3_config(args.binary, order, args.seed)
            for order in ("legacy", "product-high", "product-sum-high")
        ]

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                f"tool={args.tool} models={event['total']} configs=4 workers={args.workers} "
                f"seed={args.seed} shard={args.shard_index}/{args.shard_count} "
                f"timeout={args.timeout:g}", flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            total = int(event["total"])
            if completed % 5 == 0 or completed == total:
                print(f"completed={completed}/{total}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed",
        "group": f"bve-aig-hard-{args.tool}",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": [str(model["path"]) for model in models],
        "model_metadata": metadata,
        "metadata_fields": [
            "model_id", "family", "tier", "domain", "match_id",
            "baseline_status", "baseline_seconds", "bad_xor_density",
            "aig_ands", "seed_block",
        ],
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
