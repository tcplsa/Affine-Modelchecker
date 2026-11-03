#!/usr/bin/env python3
"""Collect controlled XOR-selection or input-order mechanism experiments."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from compare_runner import ExperimentRunner, discover_models


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
DEFAULT_BINARY = (
    ROOT / "Modelchecker-bidirectional" / "modelchecker" / "modelchecker"
)


def parse_ints(spec: str) -> list[int]:
    values = [int(item.strip()) for item in spec.split(",") if item.strip()]
    if not values or len(values) != len(set(values)):
        raise argparse.ArgumentTypeError("seeds must be a non-empty unique list")
    if any(value < 0 or value > 4294967295 for value in values):
        raise argparse.ArgumentTypeError("seeds must fit unsigned 32-bit")
    return values


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--axis", choices=["xor", "input"], required=True)
    parser.add_argument(
        "--year", choices=["2015", "2017", "2019", "2020", "2024", "2025"],
        required=True,
    )
    parser.add_argument("--group", required=True)
    parser.add_argument("--groups-file", type=Path, required=True)
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--solver-seed", type=int, required=True)
    parser.add_argument("--transform-seeds", type=parse_ints, default=list(range(1, 9)))
    parser.add_argument("--ctg-depth", type=int, default=1)
    parser.add_argument("--lanes", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skip-existing", action="store_true")
    return parser.parse_args()


def base_config(
    config_id: str,
    label: str,
    binary: Path,
    ctg_depth: int,
    strategy: str,
    transform_seed: int = 0,
) -> dict:
    return {
        "id": config_id,
        "kind": "mc",
        "label": label,
        "binary": str(binary),
        "ctg_depth": ctg_depth,
        "deterministic_lanes": True,
        "input_order": "original",
        "input_order_seed": 1,
        "xag_policy": "all",
        "xag_fraction": 1.0,
        "xag_seed": 1,
        "xag_deep_fraction": 0.5,
        "xag_min_fanout": 2,
        "perturb_modes": "",
        "perturb_seed": 1,
        "mechanism_strategy": strategy,
        "transform_seed": transform_seed,
    }


def build_xor_configs(
    binary: Path,
    ctg_depth: int,
    transform_seeds: list[int],
    lanes: int,
) -> list[dict]:
    configs = []

    def add(
        config_id: str,
        label: str,
        strategy: str,
        lane: str = "forward_xag",
        transform_seed: int = 0,
        **updates: object,
    ) -> None:
        config = base_config(
            config_id, label, binary, ctg_depth, strategy, transform_seed,
        )
        config[lane] = lanes
        config.update(updates)
        config["mechanism_axis"] = "xor"
        configs.append(config)

    add("aig", "AIG original", "aig", lane="forward_aig")
    add(
        "compact_aig", "Compact AIG", "compact-aig",
        lane="forward_compact_aig",
    )
    add(
        "lowered_xag", "Lowered XAG", "lowered-xag",
        lane="forward_lowered_xag",
    )
    for policy in (
        "all", "next", "bad", "shared", "next-only", "bad-only", "cone",
    ):
        add(
            "xag_" + policy.replace("-", "_"),
            "XAG " + policy,
            policy,
            xag_policy=policy,
        )
    for policy in ("deep", "shallow"):
        for fraction in (0.25, 0.5, 0.75):
            suffix = int(fraction * 100)
            add(
                f"xag_{policy}_{suffix}",
                f"XAG {policy} threshold {fraction:g}",
                f"{policy}-{suffix}",
                xag_policy=policy,
                xag_deep_fraction=fraction,
            )
    for policy in ("high-fanout", "low-fanout"):
        for threshold in (2, 4, 8):
            add(
                f"xag_{policy.replace('-', '_')}_{threshold}",
                f"XAG {policy} threshold {threshold}",
                f"{policy}-{threshold}",
                xag_policy=policy,
                xag_min_fanout=threshold,
            )
    for fraction in (0.1, 0.25, 0.5, 0.75, 0.9):
        suffix = int(fraction * 100)
        for transform_seed in transform_seeds:
            add(
                f"xag_sample_{suffix}_t{transform_seed}",
                f"XAG sample {fraction:g} transform {transform_seed}",
                f"sample-{suffix}",
                transform_seed=transform_seed,
                xag_policy="sample",
                xag_fraction=fraction,
                xag_seed=transform_seed,
            )
    return configs


def build_input_configs(
    binary: Path,
    ctg_depth: int,
    transform_seeds: list[int],
    lanes: int,
) -> list[dict]:
    configs = []

    def add(
        representation: str,
        order: str,
        transform_seed: int = 0,
    ) -> None:
        lane = "forward_aig" if representation == "aig" else "forward_xag"
        suffix = order.replace("-", "_")
        if transform_seed:
            suffix += f"_t{transform_seed}"
        config = base_config(
            f"{representation}_{suffix}",
            f"{representation.upper()} input {order}"
            + (f" transform {transform_seed}" if transform_seed else ""),
            binary,
            ctg_depth,
            f"{representation}-{order}",
            transform_seed,
        )
        config[lane] = lanes
        config["input_order"] = order
        config["input_order_seed"] = transform_seed or 1
        config["mechanism_axis"] = "input"
        config["representation_family"] = representation
        configs.append(config)

    deterministic_orders = (
        "original", "fanout-desc", "fanout-asc",
        "bad-first", "bad-last",
        "next-first", "next-last",
        "shared-first", "shared-last",
    )
    for representation in ("aig", "xag"):
        for order in deterministic_orders:
            add(representation, order)
        for order in ("swap", "random"):
            for transform_seed in transform_seeds:
                add(representation, order, transform_seed)
    return configs


def build_configs(args: argparse.Namespace) -> list[dict]:
    builder = build_xor_configs if args.axis == "xor" else build_input_configs
    return builder(args.binary, args.ctg_depth, args.transform_seeds, args.lanes)


def main() -> int:
    args = parse_args()
    if args.timeout <= 0 or args.workers <= 0 or args.lanes <= 0:
        raise SystemExit("timeout, workers, and lanes must be positive")
    discovery = {
        "year": args.year,
        "group": args.group,
        "groups_file": str(args.groups_file),
        "sort": "size",
    }
    paths = discover_models(discovery)
    if args.limit:
        paths = paths[: args.limit]
    configs = build_configs(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    settings = {
        "name": f"mechanism_{args.axis}_{args.year}_{args.group}_s{args.solver_seed}",
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

    def progress(event: dict) -> None:
        if event["type"] == "started":
            print(
                f"running {event['total']} models x {len(configs)} configs; "
                f"max processes~{args.workers * len(configs) * args.lanes}",
                flush=True,
            )
        elif event["type"] == "row":
            completed = event["completed"]
            if completed <= 5 or completed % 10 == 0 or completed == event["total"]:
                print(
                    f"[{completed}/{event['total']}] "
                    f"{event['row']['name']} winner={event['row']['winner']}",
                    flush=True,
                )

    runner = ExperimentRunner(settings, progress=progress)
    design_path = args.output.with_name(args.output.stem + "_design.json")
    design_path.write_text(
        json.dumps(
            {
                "version": 1,
                "axis": args.axis,
                "year": args.year,
                "group": args.group,
                "solver_seed": args.solver_seed,
                "transform_seeds": args.transform_seeds,
                "timeout": args.timeout,
                "workers": args.workers,
                "lanes": args.lanes,
                "configs": runner.configs,
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
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
