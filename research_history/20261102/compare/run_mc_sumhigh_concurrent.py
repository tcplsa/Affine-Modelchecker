#!/usr/bin/env python3
"""Run concurrent four-lane MC legacy versus sum-high confirmation."""

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
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=1800.0)
    return parser.parse_args()


def config(binary: Path, order: str) -> dict[str, object]:
    return {
        "id": "xag_legacy4" if order == "legacy" else "xag_sumhigh4",
        "label": f"MC 4xXAG {order}",
        "kind": "mc",
        "binary": str(binary),
        "forward_xag": 4,
        "ctg_depth": 1,
        "deterministic_lanes": True,
        "minisat_elim_order": order,
    }


def main() -> int:
    args = arguments()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    selected_ids = set(json.loads(args.selection.read_text(encoding="utf-8"))["ids"])
    selected = [model for model in manifest if model["id"] in selected_ids]
    if len(selected) != len(selected_ids):
        missing = selected_ids - {model["id"] for model in selected}
        raise ValueError(f"selection contains {len(missing)} models absent from manifest")
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
                f"models={event['total']} seed={args.seed} workers={args.workers} "
                f"configs=2 lanes_per_config=4 max_lane_threads={8 * args.workers} "
                f"timeout={args.timeout:g}", flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            if completed % 10 == 0 or completed == int(event["total"]):
                print(f"completed={completed}/{event['total']}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed",
        "group": "mc-sumhigh-concurrent",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": [model["path"] for model in selected],
        "model_metadata": metadata,
        "metadata_fields": ["model_id", "family", "tier", "seed_block"],
        "output": str(args.output),
        "timeout": args.timeout,
        "workers": args.workers,
        "skip_existing": True,
        "mc_seed": args.seed,
        "configs": [config(args.binary, "legacy"), config(args.binary, "sum-high")],
    }, progress)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    result = runner.run()
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
