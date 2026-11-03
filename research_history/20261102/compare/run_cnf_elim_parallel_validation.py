#!/usr/bin/env python3
"""Validate promising elimination orders with fixed-seed four-lane PDR."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path
from typing import Any

from compare_runner import ExperimentRunner
from run_cnf_elimination_screen import select_models


CONFIGS = [
    ("aig_legacy4", "4x AIG legacy", "aig", "legacy", ""),
    ("aig_high4", "4x AIG high-ID", "aig", "high", ""),
    ("xag_legacy4", "4x XAG legacy", "xag", "legacy", ""),
    ("xag_high4", "4x XAG high-ID", "xag", "high", ""),
    ("xag_sumhigh4", "4x XAG product/sum high-ID", "xag", "sum-high", ""),
    ("xag_diverse4", "4x XAG elimination portfolio", "xag", "legacy",
     "legacy,low,high,sum-high"),
]

CORE_CONFIG_IDS = {"aig_legacy4", "xag_legacy4", "xag_sumhigh4", "xag_diverse4"}


def configs_for_set(config_set: str) -> list[tuple[str, str, str, str, str]]:
    if config_set == "all":
        return CONFIGS
    return [config for config in CONFIGS if config[0] in CORE_CONFIG_IDS]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--seed", type=int, default=270001)
    parser.add_argument("--models-per-year", type=int, default=8)
    parser.add_argument("--exclude-models-per-year", type=int, default=0)
    parser.add_argument("--config-set", choices=("all", "core"), default="all")
    return parser.parse_args()


def make_config(spec: tuple[str, str, str, str, str], binary: Path) -> dict[str, Any]:
    ident, label, representation, order, lane_orders = spec
    return {
        "id": ident,
        "label": label,
        "kind": "mc",
        "binary": str(binary),
        "forward_aig": 4 if representation == "aig" else 0,
        "forward_xag": 4 if representation == "xag" else 0,
        "ctg_depth": 1,
        "deterministic_lanes": True,
        "preprocessor": "minisat",
        "minisat_elim_order": order,
        "minisat_elim_order_lanes": lane_orders,
    }


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.exclude_models_per_year:
        excluded = {
            model["id"] for model in select_models(manifest, args.exclude_models_per_year)
        }
        manifest = dict(manifest)
        manifest["models"] = [
            model for model in manifest["models"] if model["id"] not in excluded
        ]
    models = select_models(manifest, args.models_per_year)
    configs = [make_config(spec, args.binary) for spec in configs_for_set(args.config_set)]

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                f"models={event['total']} configs={len(configs)} workers={args.workers} "
                f"logical_lanes={len(configs) * 4 * args.workers}", flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            if completed % 4 == 0 or completed == int(event["total"]):
                print(f"completed={completed}/{event['total']}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed",
        "group": "cnf-elimination-parallel-validation",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": [model["path"] for model in models],
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
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
