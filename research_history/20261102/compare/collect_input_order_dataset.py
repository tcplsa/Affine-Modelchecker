#!/usr/bin/env python3
"""Collect original/fanout input-order results with the shared benchmark runner."""

from __future__ import annotations

import argparse
import signal
from pathlib import Path

from compare_runner import ExperimentRunner


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect deterministic input-order labels without solver logs."
    )
    parser.add_argument(
        "--year", choices=["2015", "2017", "2019", "2020", "2024", "2025"],
        default="2015",
    )
    parser.add_argument("--group", choices=["regular", "hard", "all"], default="regular")
    parser.add_argument("--mode", choices=["aig", "xag", "auto"], default="aig")
    parser.add_argument(
        "--policies",
        default="original,fanout-desc,fanout-asc",
        help="comma-separated subset of original,fanout-desc,fanout-asc",
    )
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--workers", type=int, default=40)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sort", choices=["name", "size", "random"], default="random")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--ctg-depth", type=int, default=1)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--groups-file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-existing", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    allowed = {"original", "fanout-desc", "fanout-asc"}
    policies = [item.strip() for item in args.policies.split(",") if item.strip()]
    if not policies or any(policy not in allowed for policy in policies):
        raise SystemExit("--policies must contain original, fanout-desc, and/or fanout-asc")

    binary = args.binary or (
        ROOT / "Modelchecker-bidirectional" / "modelchecker" / "modelchecker"
    )
    output = args.output or (
        SCRIPT_DIR / "results" / f"mc_input_order_{args.mode}_hwmcc{args.year}_{args.group}.tsv"
    )
    lane = {"aig": "forward_aig", "xag": "forward_xag", "auto": "forward_auto"}[args.mode]
    configs = []
    for policy in policies:
        config = {
            "id": policy.replace("-", "_"),
            "kind": "mc",
            "label": f"MC {args.mode} {policy}",
            "binary": str(binary),
            "ctg_depth": args.ctg_depth,
            "input_order": policy,
            lane: 1,
        }
        configs.append(config)

    settings = {
        "name": f"input_order_{args.mode}_{args.year}_{args.group}",
        "year": args.year,
        "group": args.group,
        "timeout": args.timeout,
        "workers": args.workers,
        "limit": args.limit,
        "sort": args.sort,
        "mc_seed": args.seed,
        "output": str(output),
        "skip_existing": args.skip_existing,
        "configs": configs,
    }
    if args.data_dir:
        settings["data_dir"] = str(args.data_dir)
    if args.groups_file:
        settings["groups_file"] = str(args.groups_file)

    def progress(event: dict) -> None:
        if event["type"] == "started":
            print(
                f"running {event['total']} models x {len(configs)} policies, "
                f"workers={args.workers}, output={output}",
                flush=True,
            )
        elif event["type"] == "row":
            completed = event["completed"]
            if completed <= 10 or completed % 10 == 0 or completed == event["total"]:
                row = event["row"]
                statuses = ", ".join(
                    f"{config['id']}={row[config['id'] + '_status']}"
                    for config in configs
                )
                print(f"[{completed}/{event['total']}] {row['name']} {statuses}", flush=True)

    runner = ExperimentRunner(settings, progress=progress)

    def stop(_signum: int, _frame: object) -> None:
        runner.cancel()
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        result = runner.run()
    except KeyboardInterrupt:
        runner.cancel()
        print(f"cancelled output={output}", flush=True)
        return 130
    print(
        f"completed={result['completed']} total={result['total']} "
        f"cancelled={int(result['cancelled'])} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
