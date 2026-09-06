#!/usr/bin/env python3
"""Evaluate static affine selection and the online Gaussian stop gate."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compare_runner import ExperimentRunner  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--seed", type=int, default=997001)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    models = payload["models"] if isinstance(payload, dict) else payload
    if args.limit:
        models = models[: args.limit]
    paths = [
        str(Path(model.get("path") or model["paths"]["aag"]).resolve())
        for model in models
    ]
    metadata = {
        path: {
            "scope": model.get("scope", ""),
            "family": model["family"],
            "category": model.get("category", ""),
            "expected": model["expected"],
            "width": model.get("params", {}).get("width", ""),
            "rounds": model.get("params", {}).get("rounds", ""),
            "delay": model.get("params", {}).get("delay", ""),
        }
        for path, model in zip(paths, models)
    }
    common = {
        "kind": "mc",
        "binary": str(args.binary.resolve()),
        "ctg_depth": 1,
        "deterministic_lanes": True,
        "forward_xag": 1,
        "minisat_elim_order": "legacy",
        "progress_seconds": 30,
    }
    cmsat = {
        "MC_PDR_SOLVER": "cmsat",
        "MC_PDR_CMSAT_SIMPLIFY": "0",
    }
    gate = {
        "MC_PDR_CMSAT_GAUSS": "1",
        "MC_PDR_CMSAT_GAUSS_AUTO_GATE": "1",
        "MC_PDR_CMSAT_GAUSS_AUTO_PATIENCE": "1",
    }
    configs = [
        {
            **common,
            "id": "cadical",
            "label": "CaDiCaL XAG",
            "extra_env": {"MC_PDR_SOLVER": "cadical"},
        },
        {
            **common,
            "id": "cmsat_no_gauss",
            "label": "CMSat native XOR, no Gaussian",
            "extra_env": {**cmsat, "MC_PDR_CMSAT_GAUSS": "0"},
        },
        {
            **common,
            "id": "cmsat_gauss",
            "label": "CMSat Gaussian always on",
            "extra_env": {**cmsat, "MC_PDR_CMSAT_GAUSS": "1"},
        },
        {
            **common,
            "id": "cmsat_dynamic",
            "label": "CMSat Gaussian dynamic stop",
            "extra_env": {**cmsat, **gate},
        },
        {
            **common,
            "id": "two_stage_static",
            "label": "Static affine selector, Gaussian always on",
            "extra_env": {
                "MC_PDR_SOLVER": "cadical",
                "MC_PDR_CMSAT_GAUSS": "1",
                "MC_PDR_CMSAT_SIMPLIFY": "0",
                "MC_PDR_AFFINE_AUTO": "1",
                "MC_PDR_GUARDED_AFFINE_AUTO": "1",
                "MC_PDR_GUARDED_AFFINE_VALIDATE": "1",
            },
        },
        {
            **common,
            "id": "two_stage_auto",
            "label": "Static affine selector plus dynamic stop",
            "extra_env": {
                "MC_PDR_SOLVER": "cadical",
                "MC_PDR_CMSAT_SIMPLIFY": "0",
                "MC_PDR_AFFINE_AUTO": "1",
                "MC_PDR_GUARDED_AFFINE_AUTO": "1",
                "MC_PDR_GUARDED_AFFINE_VALIDATE": "1",
                **gate,
            },
        },
    ]

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                f"models={event['total']} configs={len(configs)} "
                f"workers={args.workers}",
                flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            if completed % 5 == 0 or completed == int(event["total"]):
                print(f"completed={completed}/{event['total']}", flush=True)

    runner = ExperimentRunner({
        "year": "generated",
        "group": "affine-dynamic-gate",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": paths,
        "model_metadata": metadata,
        "metadata_fields": [
            "scope", "family", "category", "expected", "width", "rounds",
            "delay",
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
    print(json.dumps(result, sort_keys=True), flush=True)
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
