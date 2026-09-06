#!/usr/bin/env python3
"""Compare single-lane MC XAG solving with and without CMSat Gaussian XOR."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compare_runner import ExperimentRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=840001)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    models = json.loads(args.manifest.read_text(encoding="utf-8"))
    if any(model.get("expected") != "SAFE" for model in models):
        raise ValueError("the Gauss-only screen accepts SAFE benchmarks only")

    metadata = {
        str(Path(model["paths"]["aag"]).resolve()): {
            "family": model["family"],
            "expected": model["expected"],
            "category": model.get("classification", {}).get("category", ""),
            "width": model["params"].get(
                "width", model["params"].get("lane_width", 0)
            ),
            "rounds": model["params"].get(
                "rounds", model["params"].get("updates", 1)
            ),
            "delay": model["params"].get("delay", 0),
            "xor_density": model["xor_density"],
            "bad_cone_xor_density": model["bad_cone_xor_density"],
        }
        for model in models
    }

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                "models=%s workers=%s pdr_lanes_per_job=3 timeout=%ss" % (
                    event["total"], args.workers, args.timeout
                ),
                flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            total = int(event["total"])
            print("completed=%s/%s" % (completed, total), flush=True)

    common = {
        "kind": "mc",
        "binary": str(args.binary),
        "ctg_depth": 1,
        "progress_seconds": 0,
        "deterministic_lanes": True,
        "forward_xag": 1,
        "minisat_elim_order": "legacy",
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
            "id": "xag_cmsat_no_gauss",
            "label": "MC 1xCMSat native XOR no Gauss",
            "extra_env": {
                "MC_PDR_SOLVER": "cmsat",
                "MC_PDR_CMSAT_GAUSS": "0",
                "MC_PDR_CMSAT_SIMPLIFY": "0",
            },
        },
        {
            **common,
            "id": "xag_cmsat_gauss",
            "label": "MC 1xCMSat native XOR Gauss",
            "extra_env": {
                "MC_PDR_SOLVER": "cmsat",
                "MC_PDR_CMSAT_GAUSS": "1",
                "MC_PDR_CMSAT_SIMPLIFY": "0",
            },
        },
    ]
    runner = ExperimentRunner(
        {
            "year": "generated",
            "group": "pathb-gauss-single",
            "data_dir": "/home/wudl/test_tools",
            "model_paths": [model["paths"]["aag"] for model in models],
            "model_metadata": metadata,
            "metadata_fields": [
                "family", "category", "expected", "width", "rounds", "delay",
                "xor_density", "bad_cone_xor_density",
            ],
            "output": str(args.output),
            "timeout": args.timeout,
            "workers": args.workers,
            "skip_existing": True,
            "mc_seed": args.seed,
            "configs": configs,
        },
        progress,
    )
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    result = runner.run()
    print(json.dumps(result, sort_keys=True), flush=True)
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
