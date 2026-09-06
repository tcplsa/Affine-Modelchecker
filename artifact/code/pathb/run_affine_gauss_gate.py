#!/usr/bin/env python3
"""Compare always-on Gaussian reasoning with reproducible frame gates."""

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
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=991337)
    parser.add_argument("--depths", default="2,4,8")
    args = parser.parse_args()

    models = json.loads(args.manifest.read_text(encoding="utf-8"))
    paths = [str(Path(model["paths"]["aag"]).resolve()) for model in models]
    metadata = {
        path: {
            "family": model["family"],
            "category": model.get("classification", {}).get("category", ""),
            "expected": model["expected"],
        }
        for path, model in zip(paths, models)
    }
    depths = [int(item) for item in args.depths.split(",") if item.strip()]

    common = {
        "kind": "mc",
        "binary": str(args.binary.resolve()),
        "ctg_depth": 1,
        "deterministic_lanes": True,
        "forward_xag": 1,
        "minisat_elim_order": "legacy",
    }
    base_env = {
        "MC_PDR_SOLVER": "cadical",
        "MC_PDR_CMSAT_GAUSS": "1",
        "MC_PDR_CMSAT_SIMPLIFY": "0",
        "MC_PDR_AFFINE_AUTO": "1",
        "MC_PDR_GUARDED_AFFINE_AUTO": "1",
    }
    configs = [
        {
            **common,
            "id": "gauss_always",
            "label": "Affine auto: Gauss always on",
            "extra_env": base_env,
        }
    ]
    for depth in depths:
        configs.append({
            **common,
            "id": f"gauss_gate_f{depth}",
            "label": f"Affine auto: disable Gauss at frame {depth}",
            "extra_env": {
                **base_env,
                "MC_PDR_CMSAT_GAUSS_DISABLE_DEPTH": str(depth),
            },
        })

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                "models=%s configs=%s workers=%s"
                % (event["total"], len(configs), args.workers),
                flush=True,
            )
        elif event.get("type") == "row":
            print("completed=%s/%s" % (event["completed"], event["total"]), flush=True)

    runner = ExperimentRunner({
        "year": "generated",
        "group": "affine-gauss-depth-gate",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": paths,
        "model_metadata": metadata,
        "metadata_fields": ["family", "category", "expected"],
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
