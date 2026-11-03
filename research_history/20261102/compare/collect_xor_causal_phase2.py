#!/usr/bin/env python3
"""Run complementary interventions inside the next-state fanout-2/3 region."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from collect_mechanism_search import base_config
from compare_runner import ExperimentRunner, discover_models


BUCKETS = (
    "f23_next_only", "f23_shared",
    "f23_near", "f23_far",
    "f23_private_impl", "f23_reused_impl",
    "f23_shallow", "f23_deep",
    "f23_isolated", "f23_adjacent",
    "f23_support_disjoint", "f23_support_overlap",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", required=True)
    parser.add_argument("--groups-file", required=True, type=Path)
    parser.add_argument("--allowlist-dir", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--workers", type=int, default=80)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--ctg-depth", type=int, default=1)
    parser.add_argument("--group", default="phase2")
    return parser.parse_args()


def configs(args: argparse.Namespace) -> list[dict]:
    result = []
    aig = base_config("aig", "AIG original", args.binary, args.ctg_depth, "aig", 0)
    aig["forward_aig"] = 1
    aig["mechanism_axis"] = "xor-causal-f23"
    result.append(aig)
    full = base_config("xag_all", "XAG all", args.binary, args.ctg_depth, "all", 0)
    full["forward_xag"] = 1
    full["mechanism_axis"] = "xor-causal-f23"
    result.append(full)
    for bucket in BUCKETS:
        for mode in ("only", "except"):
            config_id = f"xag_{mode}_{bucket}"
            strategy = f"{mode}-{bucket}"
            config = base_config(config_id, strategy, args.binary, args.ctg_depth, strategy, 0)
            config["forward_xag"] = 1
            config["xag_allowlist"] = str(args.allowlist_dir / f"{{name}}__{mode}_{bucket}.allow")
            config["mechanism_axis"] = "xor-causal-f23"
            result.append(config)
    return result


def main() -> int:
    args = parse_args()
    paths = discover_models({
        "year": args.year,
        "group": args.group,
        "groups_file": str(args.groups_file),
        "sort": "size",
    })
    settings = {
        "name": f"xor_causal_phase2_{args.year}_s{args.seed}",
        "year": args.year,
        "group": args.group,
        "timeout": args.timeout,
        "workers": args.workers,
        "mc_seed": args.seed,
        "output": str(args.output),
        "skip_existing": True,
        "model_paths": [str(path) for path in paths],
        "configs": configs(args),
    }
    runner = ExperimentRunner(settings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_name(args.output.stem + "_design.json").write_text(
        json.dumps({
            "version": 1,
            "axis": "xor",
            "campaign": "xor-causal-f23",
            "year": args.year,
            "group": args.group,
            "timeout": args.timeout,
            "solver_seed": args.seed,
            "configs": runner.configs,
        }, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    def stop(_signum: int, _frame: object) -> None:
        runner.cancel()
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        outcome = runner.run()
    except KeyboardInterrupt:
        runner.cancel()
        return 130
    print(outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
