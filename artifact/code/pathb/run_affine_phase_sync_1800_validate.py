#!/usr/bin/env python3
"""Validate one affine phase-sync separation at the 1,800-second frontier."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compare_runner import ExperimentRunner


TARGET_STEM = (
    "affine_phase_sync_delay3_inputs4_rounds3_seed840001_"
    "topologybalanced_weight15_width20"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--seed", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    models = json.loads(args.manifest.read_text(encoding="utf-8"))
    selected = [model for model in models if model.get("stem") == TARGET_STEM]
    if len(selected) != 1:
        raise ValueError("expected exactly one phase-sync validation benchmark")
    model = selected[0]

    metadata = {
        str(Path(model["paths"]["aag"]).resolve()): {
            "family": model["family"],
            "expected": model["expected"],
            **model["params"],
            "aag_sha256": model["aag_sha256"],
            "xor_density": model["xor_density"],
            "bad_cone_xor_density": model["bad_cone_xor_density"],
        }
    }
    common = {
        "kind": "mc",
        "binary": str(args.binary),
        "ctg_depth": 1,
        "progress_seconds": 30,
        "deterministic_lanes": True,
        "minisat_elim_order": "legacy",
    }
    cmsat_common = {
        "MC_PDR_SOLVER": "cmsat",
        "MC_PDR_CMSAT_SIMPLIFY": "0",
    }
    configs = [
        {
            **common,
            "id": "baseline_cadical_1x",
            "label": "MC 1xCaDiCaL XAG baseline",
            "forward_xag": 1,
            "extra_env": {"MC_PDR_SOLVER": "cadical"},
        },
        {
            **common,
            "id": "baseline_cadical_4x",
            "label": "MC 4xCaDiCaL XAG baseline",
            "forward_xag": 4,
            "extra_env": {
                "MC_PDR_SOLVER_LANES": "cadical,cadical,cadical,cadical",
            },
        },
        {
            **common,
            "id": "cmsat_native_no_gauss_1x",
            "label": "MC 1xCMSat native XOR no Gaussian",
            "forward_xag": 1,
            "extra_env": {**cmsat_common, "MC_PDR_CMSAT_GAUSS": "0"},
        },
        {
            **common,
            "id": "cmsat_native_gauss_1x",
            "label": "MC 1xCMSat native XOR Gaussian",
            "forward_xag": 1,
            "extra_env": {**cmsat_common, "MC_PDR_CMSAT_GAUSS": "1"},
        },
        {
            **common,
            "id": "mixed_cadical_cmsat_gauss_4x",
            "label": "MC 3xCaDiCaL + 1xCMSat Gaussian",
            "forward_xag": 4,
            "extra_env": {
                "MC_PDR_SOLVER_LANES": "cadical,cadical,cadical,cmsat",
                "MC_PDR_CMSAT_GAUSS": "1",
                "MC_PDR_CMSAT_SIMPLIFY": "0",
            },
        },
    ]

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                "target=%s seed=%s configs=%s timeout=%ss" % (
                    TARGET_STEM, args.seed, len(configs), args.timeout
                ),
                flush=True,
            )
        elif event.get("type") == "row":
            print("completed=%s/%s" % (event["completed"], event["total"]), flush=True)

    runner = ExperimentRunner(
        {
            "year": "generated",
            "group": "pathb-affine-phase-sync-1800",
            "data_dir": "/home/wudl/test_tools",
            "model_paths": [model["paths"]["aag"]],
            "model_metadata": metadata,
            "metadata_fields": [
                "family", "expected", "width", "weight", "rounds", "delay",
                "inputs", "topology", "aag_sha256", "xor_density",
                "bad_cone_xor_density",
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
