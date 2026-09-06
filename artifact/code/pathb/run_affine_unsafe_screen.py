#!/usr/bin/env python3
"""Compare CDCL, Gaussian, and depth-gated Gaussian on UNSAFE affine models."""

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
    parser.add_argument("--ric3-binary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--seed", type=int, default=1400001)
    parser.add_argument("--gate-depths", default="4,16")
    args = parser.parse_args()

    models = json.loads(args.manifest.read_text(encoding="utf-8"))
    if any(model.get("expected") != "UNSAFE" for model in models):
        raise ValueError("the UNSAFE screen requires only UNSAFE models")
    paths = [str(Path(model["paths"]["aag"]).resolve()) for model in models]
    metadata = {
        path: {
            "family": model["family"],
            "category": model.get("classification", {}).get("category", ""),
            "expected": model["expected"],
            "witness_depth": model["params"]["witness_depth"],
            "width": model["params"].get(
                "width", model["params"].get("check_bits", 58)
            ),
            "symbol_bits": model["params"].get(
                "symbol_bits", model["params"].get("data_bits", 0)
            ),
        }
        for path, model in zip(paths, models)
    }

    common = {
        "kind": "mc",
        "binary": str(args.binary.resolve()),
        "ctg_depth": 1,
        "progress_seconds": 0,
        "deterministic_lanes": True,
        "forward_xag": 1,
        "minisat_elim_order": "legacy",
    }
    auto = {
        "MC_PDR_SOLVER": "cadical",
        "MC_PDR_CMSAT_SIMPLIFY": "0",
        "MC_PDR_AFFINE_AUTO": "1",
        "MC_PDR_GUARDED_AFFINE_AUTO": "1",
    }
    configs = [
        {
            **common,
            "id": "xag_cadical",
            "label": "MC 1xCaDiCaL XAG",
            "extra_env": {"MC_PDR_SOLVER": "cadical"},
        },
        {
            **common,
            "id": "cmsat_native_no_gauss",
            "label": "CMSat native XOR, no summary, no Gaussian",
            "extra_env": {
                "MC_PDR_SOLVER": "cmsat",
                "MC_PDR_CMSAT_GAUSS": "0",
                "MC_PDR_CMSAT_SIMPLIFY": "0",
            },
        },
        {
            **common,
            "id": "cmsat_native_gauss",
            "label": "CMSat native XOR, no summary, Gaussian",
            "extra_env": {
                "MC_PDR_SOLVER": "cmsat",
                "MC_PDR_CMSAT_GAUSS": "1",
                "MC_PDR_CMSAT_SIMPLIFY": "0",
            },
        },
        {
            **common,
            "id": "auto_no_gauss",
            "label": "Affine auto, CMSat summary, no Gaussian",
            "extra_env": {**auto, "MC_PDR_CMSAT_GAUSS": "0"},
        },
        {
            **common,
            "id": "auto_gauss",
            "label": "Affine auto, Gaussian always on",
            "extra_env": {**auto, "MC_PDR_CMSAT_GAUSS": "1"},
        },
    ]
    for depth in (int(item) for item in args.gate_depths.split(",") if item.strip()):
        configs.append({
            **common,
            "id": f"auto_gate_f{depth}",
            "label": f"Affine auto, disable Gaussian at frame {depth}",
            "extra_env": {
                **auto,
                "MC_PDR_CMSAT_GAUSS": "1",
                "MC_PDR_CMSAT_GAUSS_DISABLE_DEPTH": str(depth),
            },
        })
    if args.ric3_binary:
        command = (
            f"{args.ric3_binary.resolve()} check --ui false {{model}} "
            "ic3 --rseed {seed}"
        )
        configs.append({
            "kind": "custom",
            "id": "ric3_4",
            "label": "stock rIC3 four independent IC3 replicas",
            "command": command,
            "replicas": 4,
            "seed": args.seed,
        })

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                f"models={event['total']} configs={len(configs)} workers={args.workers}",
                flush=True,
            )
        elif event.get("type") == "row":
            print(f"completed={event['completed']}/{event['total']}", flush=True)

    runner = ExperimentRunner({
        "year": "generated",
        "group": "affine-unsafe-depth-screen",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": paths,
        "model_metadata": metadata,
        "metadata_fields": [
            "family", "category", "expected", "witness_depth", "width",
            "symbol_bits",
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
