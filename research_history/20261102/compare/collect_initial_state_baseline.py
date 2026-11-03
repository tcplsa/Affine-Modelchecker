#!/usr/bin/env python3
"""Collect a fixed-seed single-AIG baseline for initial-state search tiers."""

from __future__ import annotations

import argparse
import signal
from pathlib import Path

from compare_runner import ExperimentRunner, ROOT


SCRIPT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one fixed-seed forward-AIG baseline over an HWMCC set."
    )
    parser.add_argument(
        "--year",
        choices=["2015", "2017", "2019", "2020", "2024", "2025"],
        required=True,
    )
    parser.add_argument("--group", default="all")
    parser.add_argument("--groups-file", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--workers", type=int, default=90)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--ctg-depth", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-existing", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    binary = args.binary or (
        ROOT / "Modelchecker-bidirectional" / "modelchecker" / "modelchecker"
    )
    output = args.output or (
        SCRIPT_DIR / "results"
        / f"mc_initial_state_baseline_hwmcc{args.year}_{args.group}.tsv"
    )
    config = {
        "id": "aig_base",
        "label": "AIG baseline",
        "kind": "mc",
        "binary": str(binary),
        "forward_aig": 1,
        "ctg_depth": args.ctg_depth,
    }
    settings = {
        "name": f"initial_state_baseline_{args.year}_{args.group}",
        "year": args.year,
        "group": args.group,
        "timeout": args.timeout,
        "workers": args.workers,
        "mc_seed": args.seed,
        "limit": args.limit,
        "sort": "size",
        "output": str(output),
        "skip_existing": args.skip_existing,
        "configs": [config],
    }
    if args.groups_file:
        settings["groups_file"] = str(args.groups_file)
    if args.data_dir:
        settings["data_dir"] = str(args.data_dir)

    def progress(event: dict) -> None:
        if event["type"] == "started":
            print(
                f"running {event['total']} AIG baselines with "
                f"{args.workers} workers; output={output}",
                flush=True,
            )
        elif event["type"] == "row":
            completed = event["completed"]
            if completed <= 10 or completed % 25 == 0 or completed == event["total"]:
                row = event["row"]
                print(
                    f"[{completed}/{event['total']}] {row['name']} "
                    f"status={row['aig_base_status']} "
                    f"wall={row['aig_base_wall_seconds']}s",
                    flush=True,
                )

    runner = ExperimentRunner(settings, progress=progress)

    def stop(_signum: int, _frame: object) -> None:
        runner.cancel()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    result = runner.run()
    print(
        f"completed={result['completed']} total={result['total']} "
        f"cancelled={int(result['cancelled'])} output={output}"
    )
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
