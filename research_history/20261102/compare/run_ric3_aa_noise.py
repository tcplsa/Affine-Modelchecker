#!/usr/bin/env python3
"""Run two identical four-replica rIC3 configurations concurrently."""

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
    parser.add_argument("--seed", type=int, default=1900001)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=300.0)
    return parser.parse_args()


def config(binary: Path, ident: str, seed: int) -> dict[str, object]:
    return {
        "id": ident,
        "label": f"rIC3 identical legacy {ident}",
        "kind": "ric3",
        "binary": str(binary),
        "engine": "ic3",
        "aig_encoding": "native",
        "global_args": "--bve-order legacy",
        "bve_width_weight": 0,
        "replicas": 4,
        "seed": seed,
    }


def main() -> int:
    args = arguments()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    selected = {model["model_id"]: model for model in selection["models"]}
    models = [model for model in manifest if model["id"] in selected]
    metadata = {
        model["path"]: {
            **selected[model["id"]],
            "repeat_seed": args.seed,
        }
        for model in models
    }

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                f"models={event['total']} identical_configs=2 replicas=4 "
                f"workers={args.workers} seed={args.seed} timeout={args.timeout:g}",
                flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            total = int(event["total"])
            if completed % 5 == 0 or completed == total:
                print(f"completed={completed}/{total}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed",
        "group": "ric3-aa-noise",
        "model_paths": [model["path"] for model in models],
        "model_metadata": metadata,
        "metadata_fields": [
            "model_id", "family", "tier", "historical_median_seconds", "repeat_seed",
        ],
        "output": str(args.output),
        "timeout": args.timeout,
        "workers": args.workers,
        "skip_existing": True,
        "configs": [config(args.binary, "aa_left", args.seed), config(args.binary, "aa_right", args.seed)],
    }, progress)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    result = runner.run()
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
