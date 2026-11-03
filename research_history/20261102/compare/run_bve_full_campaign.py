#!/usr/bin/env python3
"""Run the final MC/rIC3 BVE-order campaign on a stable manifest shard."""

from __future__ import annotations

import argparse
import json
import signal
from collections import defaultdict
from pathlib import Path
from typing import Any

from compare_runner import ExperimentRunner


TIERS = ("trivial", "fast", "medium", "slow", "timeout", "error")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", choices=("mc", "ric3"), required=True)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--seed", type=int, default=730001)
    parser.add_argument(
        "--xag-order", default="sum-high",
        choices=("low", "high", "sum-low", "sum-high",
                 "product-low", "product-high", "product-sum-low", "product-sum-high"),
    )
    parser.add_argument("--ric3-config", default="bl_4core_control")
    parser.add_argument(
        "--ric3-mode", choices=("replicas", "portfolio"), default="replicas",
        help="Use four independent IC3 replicas or rIC3's IPC portfolio",
    )
    return parser.parse_args()


def balanced_shard(
    models: list[dict[str, Any]], index: int, count: int,
) -> list[dict[str, Any]]:
    """Round-robin every year/tier stratum after sorting by baseline cost."""
    strata: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for model in models:
        strata[(str(model["year"]), str(model.get("tier", "unknown")))].append(model)
    selected: list[dict[str, Any]] = []
    cursor = 0
    for key in sorted(strata):
        ordered = sorted(
            strata[key],
            key=lambda model: (float(model.get("baseline_seconds", 0.0)), model["id"]),
        )
        selected.extend(
            model for offset, model in enumerate(ordered)
            if (cursor + offset) % count == index
        )
        cursor = (cursor + len(ordered)) % count
    tier_rank = {tier: rank for rank, tier in enumerate(TIERS)}
    selected.sort(key=lambda model: (
        tier_rank.get(str(model.get("tier")), len(TIERS)),
        float(model.get("baseline_seconds", 0.0)),
        str(model["year"]), model["id"],
    ))
    return selected


def mc_config(
    ident: str, label: str, binary: Path, representation: str, order: str,
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "id": ident,
        "label": label,
        "kind": "mc",
        "binary": str(binary),
        "ctg_depth": 1,
        "deterministic_lanes": True,
        "minisat_elim_order": order,
        "forward_aig": 0,
        "forward_xag": 0,
    }
    config[f"forward_{representation}"] = 4
    return config


def ric3_config(
    ident: str, label: str, binary: Path, representation: str,
    order: str, portfolio: str, seed: int, mode: str,
) -> dict[str, Any]:
    use_portfolio = mode == "portfolio"
    return {
        "id": ident,
        "label": label,
        "kind": "ric3",
        "binary": str(binary),
        "engine": "portfolio" if use_portfolio else "ic3",
        "aig_encoding": representation,
        "replicas": 1 if use_portfolio else 4,
        "seed": seed,
        "global_args": f"--bve-order {order}",
        "extra_args": f"--config {portfolio}" if use_portfolio else "",
    }


def make_configs(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.tool == "mc":
        return [
            mc_config("aig_legacy4", "MC 4xAIG legacy", args.binary, "aig", "legacy"),
            mc_config("xag_legacy4", "MC 4xXAG legacy", args.binary, "xag", "legacy"),
            mc_config("xag_best4", f"MC 4xXAG {args.xag_order}", args.binary, "xag", args.xag_order),
        ]
    return [
        ric3_config(
            "native_legacy4", "rIC3-4 Native legacy", args.binary, "native", "legacy",
            args.ric3_config, args.seed, args.ric3_mode,
        ),
        ric3_config(
            "native_product_high4", "rIC3-4 Native product-high", args.binary,
            "native", "product-high",
            args.ric3_config, args.seed, args.ric3_mode,
        ),
        ric3_config(
            "native_local4", "rIC3-4 Native native-local", args.binary,
            "native", "native-local",
            args.ric3_config, args.seed, args.ric3_mode,
        ),
    ]


def main() -> int:
    args = parse_args()
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise SystemExit("shard index must be in [0, shard count)")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    models = balanced_shard(manifest["models"], args.shard_index, args.shard_count)
    configs = make_configs(args)
    metadata = {
        model["path"]: {
            "year": model["year"],
            "tier": model.get("tier", "unknown"),
            "group": model.get("tier", "unknown"),
            "model_id": model["id"],
            "family": model.get("family", model["id"]),
        }
        for model in models
    }

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                f"tool={args.tool} shard={args.shard_index}/{args.shard_count} "
                f"models={event['total']} configs={len(configs)} workers={args.workers} "
                f"logical_cores={12 * args.workers} timeout={args.timeout:g}",
                flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            total = int(event["total"])
            if completed % 10 == 0 or completed == total:
                print(f"completed={completed}/{total}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed",
        "group": "unknown",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": [model["path"] for model in models],
        "model_metadata": metadata,
        "metadata_fields": ["model_id", "family", "tier"],
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
