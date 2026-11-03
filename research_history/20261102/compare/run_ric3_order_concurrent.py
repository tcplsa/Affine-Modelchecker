#!/usr/bin/env python3
"""Run Native legacy and product-sum-high concurrently within each model."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from compare_runner import ExperimentRunner


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--workers", type=int, default=14)
    parser.add_argument("--replicas", type=int, default=4)
    parser.add_argument("--collect-stats", action="store_true")
    parser.add_argument("--timeout", type=float, default=1800.0)
    return parser.parse_args()


def config(
    binary: Path, order: str, seed: int, replicas: int, collect_stats: bool,
) -> dict[str, object]:
    config_id = "ric3_legacy" if order == "legacy" else "ric3_product_sum_high"
    return {
        "id": config_id,
        "label": f"rIC3 Native {order}",
        "kind": "ric3",
        "binary": str(binary),
        "engine": "ic3",
        "aig_encoding": "native",
        "global_args": f"--bve-order {order}",
        "bve_width_weight": 0,
        "replicas": replicas,
        "seed": seed,
        "collect_stats": collect_stats,
    }


def main() -> int:
    args = arguments()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    selected_ids = set(selection["ids"])
    selected = [model for model in manifest if model["id"] in selected_ids]
    metadata = {
        model["path"]: {
            "model_id": model["id"],
            "family": model.get("family", model["id"]),
            "tier": model["tier"],
            "seed_block": args.seed,
        }
        for model in selected
    }

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                f"models={event['total']} configs=2 workers={args.workers} "
                f"replicas={args.replicas} seed={args.seed} timeout={args.timeout:g}",
                flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            total = int(event["total"])
            if completed % 10 == 0 or completed == total:
                print(f"completed={completed}/{total}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed",
        "group": "ric3-order-concurrent",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": [model["path"] for model in selected],
        "model_metadata": metadata,
        "metadata_fields": ["model_id", "family", "tier", "seed_block"],
        "output": str(args.output),
        "timeout": args.timeout,
        "workers": args.workers,
        "skip_existing": True,
        "configs": [
            config(args.binary, "legacy", args.seed, args.replicas, args.collect_stats),
            config(args.binary, "product-sum-high", args.seed, args.replicas, args.collect_stats),
        ],
    }, progress)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    result = runner.run()
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
