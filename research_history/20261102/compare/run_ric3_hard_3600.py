#!/usr/bin/env python3
"""Run a clean stock rIC3 four-replica baseline on hard candidates."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from compare_runner import ExperimentRunner
from run_bve_full_campaign import balanced_shard


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=28)
    parser.add_argument("--timeout", type=float, default=3600.0)
    parser.add_argument("--seed", type=int, default=730001)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise SystemExit("shard index must be in [0, shard count)")
    if not args.binary.is_file():
        raise SystemExit(f"missing stock rIC3 binary: {args.binary}")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    models = balanced_shard(manifest["models"], args.shard_index, args.shard_count)
    metadata = {
        str(Path(model["path"]).resolve()): {
            "year": model["year"],
            "group": "hard_candidate_1800",
            "model_id": model["id"],
            "family": model.get("family", model["id"]),
            "hardness_tier": "candidate_1800",
        }
        for model in models
    }
    binary = str(args.binary.resolve())
    config = {
        "id": "stock_native_legacy4",
        "label": "stock rIC3-4 native legacy",
        "kind": "custom",
        "command": (
            f"{binary} check --ui false {{model}} ic3 --rseed {{seed}}"
        ),
        "replicas": 4,
        "seed": args.seed,
    }

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                f"models={event['total']} workers={args.workers} replicas=4 "
                f"timeout={args.timeout:g}s stock_binary={binary}",
                flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            total = int(event["total"])
            if completed % 5 == 0 or completed == total:
                print(f"completed={completed}/{total}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed",
        "group": "hard_candidate_1800",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": [model["path"] for model in models],
        "model_metadata": metadata,
        "metadata_fields": ["model_id", "family", "hardness_tier"],
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
