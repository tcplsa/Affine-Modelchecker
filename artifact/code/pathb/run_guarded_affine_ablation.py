#!/usr/bin/env python3
"""Compare gate-level and guarded-affine transition encodings."""

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
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--seed", type=int, default=996031)
    parser.add_argument("--confirmation", action="store_true")
    parser.add_argument(
        "--families", nargs="*", default=["crc_frame_align", "affine_phase_sync"]
    )
    args = parser.parse_args()
    models = [
        model
        for model in json.loads(args.manifest.read_text(encoding="utf-8"))
        if model["family"] in set(args.families)
    ]

    def config(identifier: str, gauss: bool, controls: int | None) -> dict:
        env = {
            "MC_PDR_SOLVER": "cmsat",
            "MC_PDR_CMSAT_GAUSS": "1" if gauss else "0",
            "MC_PDR_CMSAT_SIMPLIFY": "0",
        }
        if controls is not None:
            env.update(
                {
                    "MC_PDR_GUARDED_AFFINE": "1",
                    "MC_PDR_GUARDED_AFFINE_MAX_CONTROLS": str(controls),
                }
            )
        return {
            "kind": "mc",
            "id": identifier,
            "label": identifier,
            "binary": str(args.binary),
            "ctg_depth": 1,
            "deterministic_lanes": True,
            "forward_xag": 1,
            "minisat_elim_order": "legacy",
            "extra_env": env,
        }

    if args.confirmation:
        configs = [
            config("gauss_gate", True, None),
            config("guarded_2", True, 2),
            config("guarded_2_nogauss", False, 2),
        ]
    else:
        configs = [
            config("gauss_gate", True, None),
            config("guarded_1", True, 1),
            config("guarded_2", True, 2),
            config("guarded_3", True, 3),
            config("guarded_2_nogauss", False, 2),
        ]
    metadata = {
        str(Path(model["paths"]["aag"]).resolve()): {
            "family": model["family"],
            "expected": model["expected"],
            "category": model.get("classification", {}).get("category", ""),
        }
        for model in models
    }

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print("models=%s workers=%s" % (event["total"], args.workers), flush=True)
        elif event.get("type") == "row":
            print("completed=%s/%s" % (event["completed"], event["total"]), flush=True)

    runner = ExperimentRunner(
        {
            "year": "generated",
            "group": "guarded-affine-ablation",
            "data_dir": "/home/wudl",
            "model_paths": [model["paths"]["aag"] for model in models],
            "model_metadata": metadata,
            "metadata_fields": ["family", "category", "expected"],
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
