#!/usr/bin/env python3
"""Collect a compact controlled XOR-policy experiment on hard instances."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from collect_mechanism_search import DEFAULT_BINARY, base_config
from compare_runner import ExperimentRunner, discover_models


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", required=True)
    parser.add_argument("--group", required=True)
    parser.add_argument("--groups-file", type=Path, required=True)
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--solver-seed", type=int, required=True)
    parser.add_argument("--ctg-depth", type=int, default=1)
    parser.add_argument("--lanes", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--profile", choices=["screen", "validate"], default="screen")
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skip-existing", action="store_true")
    return parser.parse_args()


def build_hard_xor_configs(
    binary: Path,
    ctg_depth: int,
    lanes: int,
    profile: str = "screen",
) -> list[dict]:
    configs: list[dict] = []

    def add(
        config_id: str,
        label: str,
        strategy: str,
        *,
        policy: str = "all",
        threshold: int = 2,
        fraction: float = 1.0,
        transform_seed: int = 0,
        aig: bool = False,
    ) -> None:
        config = base_config(
            config_id, label, binary, ctg_depth, strategy, transform_seed,
        )
        config["forward_aig" if aig else "forward_xag"] = lanes
        config["xag_policy"] = policy
        config["xag_min_fanout"] = threshold
        config["xag_fraction"] = fraction
        config["xag_seed"] = transform_seed or 1
        config["mechanism_axis"] = "xor"
        configs.append(config)

    add("aig", "AIG original", "aig", aig=True)
    add("xag_all", "XAG all", "all")
    add("xag_next", "XAG next cone", "next", policy="next")

    for threshold in (2, 3, 4, 5, 6, 8):
        add(
            f"xag_low_fanout_{threshold}",
            f"XAG fanout < {threshold}",
            f"low-fanout-{threshold}",
            policy="low-fanout",
            threshold=threshold,
        )
    for threshold in (2, 3, 4, 5, 6):
        add(
            f"xag_next_low_fanout_{threshold}",
            f"XAG next cone and fanout < {threshold}",
            f"next-low-fanout-{threshold}",
            policy="next-low-fanout",
            threshold=threshold,
        )
    for policy, strategy in (
        ("bad-low-fanout", "bad-low-fanout-4"),
        ("shared-low-fanout", "shared-low-fanout-4"),
        ("cone-low-fanout", "cone-low-fanout-4"),
    ):
        add(
            "xag_" + strategy.replace("-", "_"),
            "XAG " + strategy,
            strategy,
            policy=policy,
            threshold=4,
        )
    for transform_seed in (1, 5):
        add(
            f"xag_sample_90_t{transform_seed}",
            f"XAG sample 90% transform {transform_seed}",
            "sample-90",
            policy="sample",
            fraction=0.9,
            transform_seed=transform_seed,
        )
    if profile == "validate":
        keep = {
            "aig",
            "xag_all",
            "xag_low_fanout_2",
            "xag_low_fanout_4",
            "xag_next_low_fanout_2",
            "xag_next_low_fanout_3",
            "xag_next_low_fanout_4",
            "xag_next_low_fanout_5",
            "xag_next_low_fanout_6",
        }
        return [config for config in configs if config["id"] in keep]
    return configs


def main() -> int:
    args = parse_args()
    configs = build_hard_xor_configs(
        args.binary, args.ctg_depth, args.lanes, args.profile,
    )
    paths = discover_models({
        "year": args.year,
        "group": args.group,
        "groups_file": str(args.groups_file),
        "sort": "size",
        "limit": args.limit,
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    settings = {
        "name": f"hard_xor_{args.year}_{args.group}_s{args.solver_seed}",
        "year": args.year,
        "group": args.group,
        "timeout": args.timeout,
        "workers": args.workers,
        "mc_seed": args.solver_seed,
        "output": str(args.output),
        "skip_existing": args.skip_existing,
        "model_paths": [str(path) for path in paths],
        "configs": configs,
    }
    runner = ExperimentRunner(settings)
    design_path = args.output.with_name(args.output.stem + "_design.json")
    design_path.write_text(
        json.dumps({
            "version": 1,
            "axis": "xor",
            "campaign": "hard-xor",
            "profile": args.profile,
            "year": args.year,
            "group": args.group,
            "solver_seed": args.solver_seed,
            "transform_seeds": [1, 5],
            "timeout": args.timeout,
            "workers": args.workers,
            "lanes": args.lanes,
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
        result = runner.run()
    except KeyboardInterrupt:
        runner.cancel()
        return 130
    print(
        f"completed={result['completed']} total={result['total']} "
        f"cancelled={int(result['cancelled'])} output={args.output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
