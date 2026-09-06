#!/usr/bin/env python3
"""Ablate gate-level XOR, Gaussian reasoning, and affine summaries."""

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
    parser.add_argument("--seed", type=int, default=996001)
    args = parser.parse_args()
    models = json.loads(args.manifest.read_text(encoding="utf-8"))

    def config(identifier: str, solver: str, gauss: bool, summary: bool) -> dict:
        env = {"MC_PDR_SOLVER": solver}
        if solver == "cmsat":
            env.update({
                "MC_PDR_CMSAT_GAUSS": "1" if gauss else "0",
                "MC_PDR_CMSAT_SIMPLIFY": "0",
                "MC_PDR_AFFINE_SUMMARY": "1" if summary else "0",
            })
        return {
            "kind": "mc", "id": identifier, "label": identifier,
            "binary": str(args.binary), "ctg_depth": 1,
            "deterministic_lanes": True, "forward_xag": 1,
            "minisat_elim_order": "legacy", "extra_env": env,
        }

    configs = [
        config("cadical_gate", "cadical", False, False),
        config("cmsat_gate", "cmsat", False, False),
        config("gauss_gate", "cmsat", True, False),
        config("cmsat_summary", "cmsat", False, True),
        config("gauss_summary", "cmsat", True, True),
    ]
    metadata = {
        str(Path(model["paths"]["aag"]).resolve()): {
            "family": model["family"], "expected": model["expected"],
            "category": model.get("classification", {}).get("category", ""),
        }
        for model in models
    }

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print("models=%s workers=%s" % (event["total"], args.workers), flush=True)
        elif event.get("type") == "row":
            print("completed=%s/%s" % (event["completed"], event["total"]), flush=True)

    runner = ExperimentRunner({
        "year": "generated", "group": "affine-summary-ablation",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": [model["paths"]["aag"] for model in models],
        "model_metadata": metadata,
        "metadata_fields": ["family", "category", "expected"],
        "output": str(args.output), "timeout": args.timeout,
        "workers": args.workers, "skip_existing": True,
        "mc_seed": args.seed, "configs": configs,
    }, progress)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    result = runner.run()
    print(json.dumps(result, sort_keys=True), flush=True)
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

