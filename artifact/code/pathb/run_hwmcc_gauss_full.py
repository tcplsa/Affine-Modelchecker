#!/usr/bin/env python3
"""Run a four-lane CMSat/Gaussian MC portfolio on the full HWMCC manifest."""

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
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--workers", type=int, default=28)
    parser.add_argument("--lanes", type=int, default=4)
    parser.add_argument("--seed", type=int, default=997001)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--gauss-disable-depth",
        type=int,
        default=-1,
        help="negative keeps Gaussian reasoning enabled for the whole run",
    )
    args = parser.parse_args()

    design = json.loads(args.manifest.read_text(encoding="utf-8"))
    models = design["models"]
    if args.limit > 0:
        models = models[: args.limit]

    env = {
        "MC_PDR_SOLVER": "cmsat",
        "MC_PDR_CMSAT_GAUSS": "1",
        "MC_PDR_CMSAT_SIMPLIFY": "0",
        "MC_PDR_AFFINE_AUTO": "1",
        "MC_PDR_AFFINE_CADICAL_MAX_SUPPORT": "0",
        "MC_PDR_GUARDED_AFFINE_AUTO": "1",
    }
    if args.gauss_disable_depth >= 0:
        env["MC_PDR_CMSAT_GAUSS_DISABLE_DEPTH"] = str(args.gauss_disable_depth)

    config = {
        "kind": "mc",
        "id": "mc_cmsat_gauss4",
        "label": "MC 4xCMSat native XOR + Gaussian",
        "binary": str(args.binary.resolve()),
        "ctg_depth": 1,
        "progress_seconds": 60,
        "deterministic_lanes": True,
        "forward_xag": args.lanes,
        "minisat_elim_order": "legacy",
        "extra_env": env,
    }
    metadata = {
        str(Path(model["path"]).resolve()): {
            "model_id": model["id"],
            "benchmark_year": model["year"],
            "family": model["family"],
            "tier": model["tier"],
            "baseline_status": model.get("baseline_status", ""),
            "baseline_seconds": model.get("baseline_seconds", ""),
            "recognized_xors": model.get("recognized_xors", ""),
            "next_xor_density": model.get("next_xor_density", ""),
            "bad_xor_density": model.get("bad_xor_density", ""),
        }
        for model in models
    }

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                "models=%s workers=%s lanes=%s timeout=%ss"
                % (event["total"], args.workers, args.lanes, args.timeout),
                flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            if completed % 10 == 0 or completed == int(event["total"]):
                print("completed=%s/%s" % (completed, event["total"]), flush=True)

    runner = ExperimentRunner({
        "year": "all",
        "group": "hwmcc-cmsat-gauss-full",
        "model_paths": [model["path"] for model in models],
        "model_metadata": metadata,
        "metadata_fields": [
            "model_id", "benchmark_year", "family", "tier",
            "baseline_status", "baseline_seconds", "recognized_xors",
            "next_xor_density", "bad_xor_density",
        ],
        "output": str(args.output),
        "timeout": args.timeout,
        "workers": args.workers,
        "skip_existing": True,
        "mc_seed": args.seed,
        "configs": [config],
    }, progress)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    result = runner.run()
    print(json.dumps(result, sort_keys=True), flush=True)
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
