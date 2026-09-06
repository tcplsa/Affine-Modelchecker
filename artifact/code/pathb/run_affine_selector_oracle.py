#!/usr/bin/env python3
"""Run each backend path once for offline affine-selector replay."""

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
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--seed", type=int, default=996101)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--mode", choices=("oracle", "online"), default="oracle")
    args = parser.parse_args()
    models = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    if args.limit:
        models = models[: args.limit]

    base = {
        "kind": "mc",
        "binary": str(args.binary),
        "ctg_depth": 1,
        "deterministic_lanes": True,
        "forward_xag": 1,
        "minisat_elim_order": "legacy",
    }
    cmsat = {
        "MC_PDR_SOLVER": "cmsat",
        "MC_PDR_CMSAT_GAUSS": "1",
        "MC_PDR_CMSAT_SIMPLIFY": "0",
        "MC_PDR_PROGRESS_SECONDS": "1",
    }
    configs = [
        dict(base, id="cadical", label="CaDiCaL", extra_env={
            "MC_PDR_SOLVER": "cadical", "MC_PDR_PROGRESS_SECONDS": "1",
        }),
        dict(base, id="cadical_hints", label="CaDiCaL affine hints", extra_env={
            "MC_PDR_SOLVER": "cadical", "MC_PDR_CADICAL_AFFINE_HINTS": "1",
            "MC_PDR_PROGRESS_SECONDS": "1",
        }),
        dict(base, id="gauss_global", label="CMSat Gaussian global summary", extra_env={
            **cmsat, "MC_PDR_AFFINE_SUMMARY": "1",
        }),
    ]
    for cap in (1, 2, 3):
        configs.append(dict(
            base,
            id=f"gauss_guard{cap}",
            label=f"CMSat Gaussian guarded summary cap {cap}",
            extra_env={
                **cmsat,
                "MC_PDR_GUARDED_AFFINE": "1",
                "MC_PDR_GUARDED_AFFINE_MAX_CONTROLS": str(cap),
            },
        ))
    if args.mode == "online":
        configs = [dict(
            base,
            id="auto_default",
            label="Online affine selector 32/0.75/2",
            extra_env={
                "MC_PDR_SOLVER": "cadical",
                "MC_PDR_CMSAT_GAUSS": "1",
                "MC_PDR_CMSAT_SIMPLIFY": "0",
                "MC_PDR_AFFINE_AUTO": "1",
                "MC_PDR_AFFINE_CADICAL_MAX_SUPPORT": "32",
                "MC_PDR_GUARDED_AFFINE_AUTO": "1",
                "MC_PDR_GUARDED_AFFINE_AUTO_MIN_COVERAGE": "0.75",
                "MC_PDR_GUARDED_AFFINE_MAX_CONTROLS": "2",
                "MC_PDR_PROGRESS_SECONDS": "1",
            },
        )]

    metadata = {
        str(Path(model["path"]).resolve()): {
            key: model.get(key, "")
            for key in ("scope", "family", "category", "expected", "split",
                        "split_basis", "structure_group", "scale")
        }
        for model in models
    }

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(f"models={event['total']} workers={args.workers} timeout={args.timeout}", flush=True)
        elif event.get("type") == "row":
            completed = int(event["completed"])
            if completed % 5 == 0 or completed == int(event["total"]):
                print(f"completed={completed}/{event['total']}", flush=True)

    runner = ExperimentRunner({
        "year": "generated",
        "group": f"affine-selector-{args.mode}",
        "model_paths": [model["path"] for model in models],
        "model_metadata": metadata,
        "metadata_fields": [
            "scope", "family", "category", "expected", "split", "split_basis",
            "structure_group", "scale",
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
