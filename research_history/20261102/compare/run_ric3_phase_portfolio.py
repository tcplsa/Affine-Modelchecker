#!/usr/bin/env python3
"""Run equal-budget four-lane portfolios of phase-specific BVE orders."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from compare_runner import ExperimentRunner
from run_bve_full_campaign import balanced_shard


ORDERS = {
    "LLL": "legacy,legacy,legacy",
    "LPP": "legacy,product-sum-high,product-sum-high",
    "PLP": "product-sum-high,legacy,product-sum-high",
    "PPP": "product-sum-high,product-sum-high,product-sum-high",
}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=1160001)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    return parser.parse_args()


def config(binary: Path, sequence: str, replicas: int, seed: int) -> dict[str, object]:
    return {
        "id": f"phase_{sequence.lower()}{replicas}",
        "label": f"rIC3 {replicas}x{sequence}",
        "kind": "ric3",
        "binary": str(binary),
        "engine": "ic3",
        "aig_encoding": "native",
        "global_args": f"--bve-order legacy --bve-order-sequence {ORDERS[sequence]}",
        "bve_width_weight": 0,
        "replicas": replicas,
        "seed": seed,
    }


def main() -> int:
    args = arguments()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    selected_ids = set(json.loads(args.selection.read_text(encoding="utf-8"))["ids"])
    selected = balanced_shard(
        [model for model in manifest if model["id"] in selected_ids],
        args.shard_index,
        args.shard_count,
    )
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
                f"shard={args.shard_index}/{args.shard_count} models={event['total']} "
                f"workers={args.workers} max_processes={14 * args.workers} timeout={args.timeout:g}",
                flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            if completed % 10 == 0 or completed == int(event["total"]):
                print(f"completed={completed}/{event['total']}", flush=True)

    configs = [
        config(args.binary, "PPP", 4, args.seed),
        config(args.binary, "LLL", 4, args.seed),
        config(args.binary, "PPP", 2, args.seed),
        config(args.binary, "LPP", 2, args.seed),
        config(args.binary, "PLP", 2, args.seed),
    ]
    runner = ExperimentRunner({
        "year": "mixed",
        "group": "ric3-phase-portfolio",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": [model["path"] for model in selected],
        "model_metadata": metadata,
        "metadata_fields": ["model_id", "family", "tier", "seed_block"],
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
