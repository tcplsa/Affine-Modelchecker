#!/usr/bin/env python3
"""Confirm strict Gaussian-only CRC candidates with pure four-lane backends."""

from __future__ import annotations

import argparse
import csv
import json
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compare_runner import ExperimentRunner


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--screen", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()

    with args.screen.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    strict = {
        row["name"] for row in rows
        if row["xag_cadical_status"] != "SAFE"
        and row["xag_cmsat_no_gauss_status"] != "SAFE"
        and row["xag_cmsat_gauss_status"] == "SAFE"
    }
    models = json.loads(args.manifest.read_text(encoding="utf-8"))
    selected = [model for model in models if model["stem"] in strict]
    if not selected:
        print("no strict Gaussian-only candidates", flush=True)
        return 0

    metadata = {
        str(Path(model["paths"]["aag"]).resolve()): {
            "family": model["family"],
            "expected": model["expected"],
            **model["params"],
            "aag_sha256": model["aag_sha256"],
            "xor_density": model["xor_density"],
            "bad_cone_xor_density": model["bad_cone_xor_density"],
        }
        for model in selected
    }
    common = {
        "kind": "mc",
        "binary": str(args.binary),
        "ctg_depth": 1,
        "progress_seconds": 30,
        "deterministic_lanes": True,
        "forward_xag": 4,
        "minisat_elim_order": "legacy",
    }
    configs = [
        {
            **common,
            "id": "cadical_4x",
            "label": "MC 4xCaDiCaL XAG",
            "extra_env": {"MC_PDR_SOLVER_LANES": "cadical,cadical,cadical,cadical"},
        },
        {
            **common,
            "id": "cmsat_no_gauss_4x",
            "label": "MC 4xCMSat native XOR no Gauss",
            "extra_env": {
                "MC_PDR_SOLVER_LANES": "cmsat,cmsat,cmsat,cmsat",
                "MC_PDR_CMSAT_GAUSS": "0",
                "MC_PDR_CMSAT_SIMPLIFY": "0",
            },
        },
        {
            **common,
            "id": "cmsat_gauss_4x",
            "label": "MC 4xCMSat native XOR Gaussian",
            "extra_env": {
                "MC_PDR_SOLVER_LANES": "cmsat,cmsat,cmsat,cmsat",
                "MC_PDR_CMSAT_GAUSS": "1",
                "MC_PDR_CMSAT_SIMPLIFY": "0",
            },
        },
    ]

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                f"candidates={len(selected)} seed={args.seed} "
                f"configs={len(configs)} timeout={args.timeout}s",
                flush=True,
            )
        elif event.get("type") == "row":
            print(f"completed={event['completed']}/{event['total']}", flush=True)

    runner = ExperimentRunner({
        "year": "generated",
        "group": "crc-gauss-pure-1800-confirm",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": [model["paths"]["aag"] for model in selected],
        "model_metadata": metadata,
        "metadata_fields": [
            "family", "expected", "width", "polynomial", "symbol_bits",
            "aag_sha256", "xor_density", "bad_cone_xor_density",
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
