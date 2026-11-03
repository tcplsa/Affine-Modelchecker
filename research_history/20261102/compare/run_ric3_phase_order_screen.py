#!/usr/bin/env python3
"""Screen all legacy/product-sum-high assignments across three BVE phases."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from compare_runner import ExperimentRunner
from run_bve_full_campaign import balanced_shard


SEQUENCES = ("LLL", "PLL", "LPL", "LLP", "PPL", "PLP", "LPP", "PPP")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=1150001)
    parser.add_argument("--workers", type=int, default=15)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    return parser.parse_args()


def config(binary: Path, sequence: str, seed: int) -> dict[str, object]:
    names = ["legacy" if value == "L" else "product-sum-high" for value in sequence]
    return {
        "id": f"phase_{sequence.lower()}",
        "label": f"rIC3 phase {sequence}",
        "kind": "ric3",
        "binary": str(binary),
        "engine": "ic3",
        "aig_encoding": "native",
        "global_args": (
            "--bve-order legacy --bve-order-sequence " + ",".join(names)
        ),
        "bve_width_weight": 0,
        "replicas": 1,
        "seed": seed,
    }


def main() -> int:
    args = arguments()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    selected_ids = set(json.loads(args.selection.read_text(encoding="utf-8"))["ids"])
    selected = [model for model in manifest if model["id"] in selected_ids]
    selected = balanced_shard(selected, args.shard_index, args.shard_count)
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
                f"configs={len(SEQUENCES)} workers={args.workers} timeout={args.timeout:g}",
                flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            if completed % 10 == 0 or completed == int(event["total"]):
                print(f"completed={completed}/{event['total']}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed",
        "group": "ric3-phase-order-screen",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": [model["path"] for model in selected],
        "model_metadata": metadata,
        "metadata_fields": ["model_id", "family", "tier", "seed_block"],
        "output": str(args.output),
        "timeout": args.timeout,
        "workers": args.workers,
        "skip_existing": True,
        "configs": [config(args.binary, sequence, args.seed) for sequence in SEQUENCES],
    }, progress)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    result = runner.run()
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
