#!/usr/bin/env python3
"""Collect direct AIG versus full-XAG labels on a fixed benchmark group."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from collect_mechanism_search import base_config
from compare_runner import ExperimentRunner, discover_models


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", required=True)
    parser.add_argument("--group", required=True)
    parser.add_argument("--groups-file", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--workers", type=int, default=80)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--ctg-depth", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    aig = base_config("state_000", "AIG original", args.binary, args.ctg_depth, "aig", 0)
    aig["forward_aig"] = 1
    aig["design_family"] = "aig"
    xag = base_config("state_001", "Native XAG all", args.binary, args.ctg_depth, "all", 0)
    xag["forward_xag"] = 1
    xag["design_family"] = "native-xag"
    paths = discover_models({
        "year": args.year,
        "group": args.group,
        "groups_file": str(args.groups_file),
        "sort": "size",
    })
    settings = {
        "name": f"aig_xag_labels_{args.year}_{args.group}_s{args.seed}",
        "year": args.year,
        "group": args.group,
        "timeout": args.timeout,
        "workers": args.workers,
        "mc_seed": args.seed,
        "output": str(args.output),
        "skip_existing": True,
        "model_paths": [str(path) for path in paths],
        "configs": [aig, xag],
    }
    runner = ExperimentRunner(settings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_name(args.output.stem + "_design.json").write_text(
        json.dumps({
            "version": 1,
            "axis": "aig-xag-labels",
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

