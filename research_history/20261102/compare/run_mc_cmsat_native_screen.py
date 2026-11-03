#!/usr/bin/env python3
"""Screen a native-XOR CryptoMiniSat lane on MC's SAT-heavy hard frontier."""

from __future__ import annotations

import argparse
import csv
import json
import signal
from pathlib import Path

from compare_runner import ExperimentRunner


def enabled(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--atlas", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=840001)
    parser.add_argument("--progress-seconds", type=int, default=60)
    parser.add_argument(
        "--suite", choices=("native-one", "lane-sweep"), default="native-one",
        help="native-one compares 0/1 CMSat lanes; lane-sweep compares 0/2/4.",
    )
    return parser.parse_args()


def build_manifest(atlas: Path, output: Path) -> list[dict[str, object]]:
    with atlas.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))

    models: list[dict[str, object]] = []
    for row in rows:
        labels = set(filter(None, row["failure_labels"].split(",")))
        if "sat-heavy-query" not in labels:
            continue
        if row["status"] in {"SAFE", "UNSAFE"} or enabled(row["mc_aig_solved"]):
            continue
        models.append({
            "id": row["model_id"],
            "name": row["name"],
            "year": int(row["year"]),
            "family": row["family"],
            "path": row["path"],
            "recognized_xors": int(row["recognized_xors"]),
            "next_xor_density": float(row["next_xor_density"]),
            "structural_class": row["structural_class"],
            "diagnostic_depth": float(row["depth"]),
            "failure_labels": sorted(labels),
        })

    models.sort(key=lambda model: (int(model["year"]), str(model["id"])))
    payload = {
        "schema": "mc-cmsat-native-screen-v1",
        "selection": {
            "source": str(atlas),
            "rule": "unresolved MC-AIG model with sat-heavy-query diagnostic label",
            "families": len({str(model["family"]) for model in models}),
            "models": len(models),
        },
        "models": models,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return models


def main() -> int:
    args = parse_args()
    models = build_manifest(args.atlas, args.manifest)
    metadata = {
        str(Path(str(model["path"])).resolve()): {
            "year": model["year"],
            "group": "ric3-hard-3600-sat-heavy",
            "model_id": model["id"],
            "family": model["family"],
            "structural_class": model["structural_class"],
            "recognized_xors": model["recognized_xors"],
            "next_xor_density": model["next_xor_density"],
        }
        for model in models
    }

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                "models=%s workers=%s max_pdr_lanes=%s timeout=%ss" % (
                    event["total"], args.workers, 12 * args.workers, args.timeout
                ),
                flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            total = int(event["total"])
            if completed % 2 == 0 or completed == total:
                print("completed=%s/%s" % (completed, total), flush=True)

    common = {
        "kind": "mc",
        "binary": str(args.binary),
        "ctg_depth": 1,
        "progress_seconds": args.progress_seconds,
        "deterministic_lanes": True,
        "forward_xag": 4,
        "minisat_elim_order": "legacy",
    }
    baseline = {
        **common,
        "id": "xag4_cadical",
        "label": "MC 4xCaDiCaL XAG",
        "extra_env": {
            "MC_PDR_SOLVER_LANES": "cadical,cadical,cadical,cadical",
        },
    }
    if args.suite == "native-one":
        configs = [
            baseline,
            {
                **common,
                "id": "xag3_cadical_1_cmsat_gauss",
                "label": "MC 3xCaDiCaL + 1xCMSat native XOR Gauss",
                "extra_env": {
                    "MC_PDR_SOLVER_LANES": "cadical,cadical,cadical,cmsat",
                    "MC_PDR_CMSAT_GAUSS": "1",
                    "MC_PDR_CMSAT_SIMPLIFY": "0",
                },
            },
            {
                **common,
                "id": "xag3_cadical_1_cmsat_no_gauss",
                "label": "MC 3xCaDiCaL + 1xCMSat native XOR no Gauss",
                "extra_env": {
                    "MC_PDR_SOLVER_LANES": "cadical,cadical,cadical,cmsat",
                    "MC_PDR_CMSAT_GAUSS": "0",
                    "MC_PDR_CMSAT_SIMPLIFY": "0",
                },
            },
        ]
    else:
        configs = [
            baseline,
            {
                **common,
                "id": "xag2_cadical_2_cmsat_gauss",
                "label": "MC 2xCaDiCaL + 2xCMSat native XOR Gauss",
                "extra_env": {
                    "MC_PDR_SOLVER_LANES": "cadical,cadical,cmsat,cmsat",
                    "MC_PDR_CMSAT_GAUSS": "1",
                    "MC_PDR_CMSAT_SIMPLIFY": "0",
                },
            },
            {
                **common,
                "id": "xag4_cmsat_gauss",
                "label": "MC 4xCMSat native XOR Gauss",
                "extra_env": {
                    "MC_PDR_SOLVER_LANES": "cmsat,cmsat,cmsat,cmsat",
                    "MC_PDR_CMSAT_GAUSS": "1",
                    "MC_PDR_CMSAT_SIMPLIFY": "0",
                },
            },
        ]
    runner = ExperimentRunner(
        {
            "year": "mixed",
            "group": "ric3-hard-3600-sat-heavy",
            "data_dir": "/home/wudl/test_tools",
            "model_paths": [str(model["path"]) for model in models],
            "model_metadata": metadata,
            "metadata_fields": [
                "model_id", "family", "structural_class",
                "recognized_xors", "next_xor_density",
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
