#!/usr/bin/env python3
"""Collect PDR-free structural BVE probes for every model and lift order."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from compare_runner import ExperimentRunner


ORDERS = ("legacy", "low", "high", "sum-low", "sum-high")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=300.0)
    return parser.parse_args()


def config(binary: Path, order: str) -> dict[str, object]:
    ident = order.replace("-", "_")
    return {
        "id": f"xag_probe_lift_{ident}",
        "label": f"XAG preprocessing probe lift={order}",
        "kind": "mc",
        "binary": str(binary),
        "mode": "xag",
        "direction": "forward",
        "preprocess_only": True,
        "preprocessor": "minisat",
        "minisat_elim_order": "legacy",
        "minisat_translation_elim_order": "legacy",
        "minisat_lift_elim_order": order,
        "forward_aig": 0,
        "forward_xag": 0,
        "ctg_depth": 0,
    }


def main() -> int:
    args = arguments()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    models = manifest["models"]
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
                f"models={event['total']} orders={len(ORDERS)} "
                f"workers={args.workers} max_processes={len(ORDERS) * args.workers} "
                f"timeout={args.timeout:g}", flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            total = int(event["total"])
            if completed % 50 == 0 or completed == total:
                print(f"completed={completed}/{total}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed",
        "group": "bve-preprocess-probe",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": [model["path"] for model in models],
        "model_metadata": metadata,
        "metadata_fields": ["model_id", "family", "tier"],
        "output": str(args.output),
        "timeout": args.timeout,
        "workers": args.workers,
        "skip_existing": True,
        "configs": [config(args.binary, order) for order in ORDERS],
    }, progress)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    result = runner.run()
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
