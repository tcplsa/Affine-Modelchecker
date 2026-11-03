#!/usr/bin/env python3
"""Screen native four-lane PPP/LPP allocations with shared termination."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from compare_runner import ExperimentRunner
from run_ric3_phase_portfolio import ORDERS


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--tiers", default="slow,timeout")
    return parser.parse_args()


def lane_args(sequence: str) -> str:
    return f"--bve-order legacy --bve-order-sequence {ORDERS[sequence]}"


def allocation(binary: Path, ppp: int, lpp: int, seed: int) -> dict[str, object]:
    name = f"{ppp}p{lpp}l"
    return {
        "id": f"phase_{name}",
        "label": f"rIC3 {ppp}xPPP+{lpp}xLPP",
        "kind": "ric3",
        "binary": str(binary),
        "engine": "ic3",
        "aig_encoding": "native",
        "global_args": lane_args("PPP"),
        "replica_global_args": [lane_args("PPP")] * ppp + [lane_args("LPP")] * lpp,
        "bve_width_weight": 0,
        "replicas": ppp + lpp,
        "seed": seed,
    }


def main() -> int:
    args = arguments()
    tiers = {value.strip() for value in args.tiers.split(",") if value.strip()}
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    selected_ids = set(json.loads(args.selection.read_text(encoding="utf-8"))["ids"])
    selected = [
        model for model in manifest
        if model["id"] in selected_ids and model["tier"] in tiers
    ]
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
                f"models={event['total']} seed={args.seed} tiers={','.join(sorted(tiers))} "
                f"workers={args.workers} max_processes={20 * args.workers} "
                f"timeout={args.timeout:g}", flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            if completed % 10 == 0 or completed == int(event["total"]):
                print(f"completed={completed}/{event['total']}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed",
        "group": "ric3-phase-allocation",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": [model["path"] for model in selected],
        "model_metadata": metadata,
        "metadata_fields": ["model_id", "family", "tier", "seed_block"],
        "output": str(args.output),
        "timeout": args.timeout,
        "workers": args.workers,
        "skip_existing": True,
        "configs": [allocation(args.binary, ppp, 4 - ppp, args.seed) for ppp in range(4, -1, -1)],
    }, progress)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    result = runner.run()
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
