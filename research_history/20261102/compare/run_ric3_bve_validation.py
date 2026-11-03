#!/usr/bin/env python3
"""Screen and validate deterministic BVE orders in rIC3."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path
from typing import Any

from compare_runner import ExperimentRunner
from run_cnf_elimination_screen import select_models


ORDERS = (
    ("legacy", "legacy"),
    ("product_low", "product-low"),
    ("product_high", "product-high"),
    ("product_sum_low", "product-sum-low"),
    ("product_sum_high", "product-sum-high"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--phase", choices=("screen", "portfolio"), required=True)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--seed", type=int, default=380001)
    parser.add_argument("--models-per-year", type=int, default=8)
    parser.add_argument("--exclude-models-per-year", type=int, default=0)
    return parser.parse_args()


def ric3_config(
    ident: str, label: str, binary: Path, encoding: str, order: str,
    portfolio: bool,
) -> dict[str, Any]:
    extra = ""
    if portfolio:
        extra = "--config bl_4core_control"
    return {
        "id": ident,
        "label": label,
        "kind": "ric3",
        "binary": str(binary),
        "engine": "portfolio" if portfolio else "ic3",
        "aig_encoding": encoding,
        "replicas": 1,
        "seed": 380001,
        "global_args": f"--bve-order {order}",
        "extra_args": extra,
    }


def configs_for_phase(phase: str, binary: Path) -> list[dict[str, Any]]:
    portfolio = phase == "portfolio"
    configs = [
        ric3_config(
            "aig_legacy", "rIC3 AIG legacy", binary, "aig", "legacy", portfolio,
        )
    ]
    configs.extend(
        ric3_config(
            f"xag_{ident}", f"rIC3 XAG {order}", binary, "xag", order, portfolio,
        )
        for ident, order in ORDERS
    )
    return configs


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
    configs = configs_for_phase(args.phase, args.binary)
    for config in configs:
        config["seed"] = args.seed

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            cores = 4 if args.phase == "portfolio" else 1
            print(
                f"phase={args.phase} models={event['total']} configs={len(configs)} "
                f"workers={args.workers} logical_cores={len(configs) * cores * args.workers}",
                flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            if completed % 4 == 0 or completed == int(event["total"]):
                print(f"completed={completed}/{event['total']}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed",
        "group": f"ric3-bve-{args.phase}",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": [model["path"] for model in models],
        "output": str(args.output),
        "timeout": args.timeout,
        "workers": args.workers,
        "skip_existing": True,
        "configs": configs,
    }, progress)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    result = runner.run()
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
