#!/usr/bin/env python3
"""Confirm 1,800-second Gaussian-only candidates at a four-thread budget."""

from __future__ import annotations

import argparse
import csv
import json
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compare_runner import ExperimentRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--screen", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--seed", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with args.screen.open(newline="", encoding="utf-8") as handle:
        screen_rows = list(csv.DictReader(handle, delimiter="\t"))
    candidate_names = {
        row["name"]
        for row in screen_rows
        if row.get("xag_cmsat_gauss_status") == "SAFE"
        and row.get("xag_cadical_status") != "SAFE"
        and row.get("xag_cmsat_no_gauss_status") != "SAFE"
    }
    models = json.loads(args.manifest.read_text(encoding="utf-8"))
    selected = [
        model
        for model in models
        if Path(model["paths"]["aag"]).stem in candidate_names
    ]
    if not selected:
        print("no strict Gaussian-only candidates in screen", flush=True)
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
            "id": "baseline_cadical_4x",
            "label": "MC 4xCaDiCaL XAG baseline",
            "extra_env": {
                "MC_PDR_SOLVER_LANES": "cadical,cadical,cadical,cadical",
            },
        },
        {
            **common,
            "id": "mixed_cadical_cmsat_gauss_4x",
            "label": "MC 3xCaDiCaL + 1xCMSat Gaussian",
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
                "candidates=%s seed=%s configs=%s timeout=%ss" % (
                    len(selected), args.seed, len(configs), args.timeout
                ),
                flush=True,
            )
        elif event.get("type") == "row":
            print("completed=%s/%s" % (event["completed"], event["total"]), flush=True)

    runner = ExperimentRunner(
        {
            "year": "generated",
            "group": "pathb-affine-phase-sync-1800-confirm",
            "data_dir": "/home/wudl/test_tools",
            "model_paths": [model["paths"]["aag"] for model in selected],
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
