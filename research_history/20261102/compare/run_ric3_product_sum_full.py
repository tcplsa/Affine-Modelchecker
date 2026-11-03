#!/usr/bin/env python3
"""Run Native product-sum-high rIC3 on a stable full-campaign shard."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from compare_runner import ExperimentRunner
from run_bve_full_campaign import balanced_shard, ric3_config


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--shard-index", required=True, type=int)
    parser.add_argument("--shard-count", required=True, type=int)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--seed", type=int, default=730001)
    parser.add_argument("--ric3-config", default="bl_4core_control")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise SystemExit("shard index must be in [0, shard count)")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    models = balanced_shard(manifest["models"], args.shard_index, args.shard_count)
    config = ric3_config(
        "native_product_sum_high4", "rIC3-4 Native product-sum-high",
        args.binary, "native", "product-sum-high", args.ric3_config,
        args.seed, "replicas",
    )
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
            print(
                f"shard={args.shard_index}/{args.shard_count} "
                f"models={event['total']} workers={args.workers} "
                f"max_replicas={4 * args.workers} timeout={args.timeout:g}",
                flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            total = int(event["total"])
            if completed % 10 == 0 or completed == total:
                print(f"completed={completed}/{total}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed",
        "group": "ric3-product-sum-full",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": [model["path"] for model in models],
        "model_metadata": metadata,
        "metadata_fields": ["model_id", "family", "tier"],
        "output": str(args.output),
        "timeout": args.timeout,
        "workers": args.workers,
        "skip_existing": True,
        "configs": [config],
    }, progress)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    result = runner.run()
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
