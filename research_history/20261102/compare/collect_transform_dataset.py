#!/usr/bin/env python3
"""Progressively collect input-order and selective-XAG transformation labels."""

from __future__ import annotations

import argparse
import csv
import signal
from pathlib import Path

from compare_runner import ExperimentRunner, discover_models, model_name


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
SWAP_SEEDS = (2654435761, 2246822519, 3266489917, 668265263, 374761393, 1274126177)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a progressive portfolio of semantics-preserving input transformations."
    )
    parser.add_argument(
        "--year", choices=["2015", "2017", "2019", "2020", "2024", "2025"],
        default="2015",
    )
    parser.add_argument("--group", choices=["regular", "hard", "all"], default="regular")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--ctg-depth", type=int, default=1)
    parser.add_argument("--swap-count", type=int, default=2, choices=range(0, 7))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--groups-file", type=Path)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--baseline-results", type=Path)
    parser.add_argument("--baseline-prefix", default="mc_a")
    parser.add_argument("--min-baseline-seconds", type=float, default=0.0)
    parser.add_argument("--max-baseline-seconds", type=float, default=float("inf"))
    parser.add_argument("--include-missing-baseline", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-existing", action="store_true")
    return parser.parse_args()


def baseline_times(path: Path, prefix: str) -> dict[str, float]:
    result = {}
    status_column = f"{prefix}_status" if prefix else "status"
    time_column = f"{prefix}_wall_seconds" if prefix else "wall_seconds"
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row.get(status_column) not in {"SAFE", "UNSAFE"}:
                continue
            try:
                result[row["name"]] = float(row[time_column])
            except (KeyError, ValueError):
                continue
    return result


def mc_config(
    config_id: str,
    label: str,
    binary: Path,
    ctg_depth: int,
    mode: str,
    input_order: str = "original",
    input_order_seed: int = 1,
    xag_policy: str = "all",
) -> dict:
    config = {
        "id": config_id,
        "kind": "mc",
        "label": label,
        "binary": str(binary),
        "ctg_depth": ctg_depth,
        "input_order": input_order,
        "input_order_seed": input_order_seed,
        "xag_policy": xag_policy,
    }
    config["forward_aig" if mode == "aig" else "forward_xag"] = 1
    return config


def main() -> int:
    args = parse_args()
    binary = args.binary or (
        ROOT / "Modelchecker-bidirectional" / "modelchecker" / "modelchecker"
    )
    discovery = {"year": args.year, "group": args.group, "sort": "size"}
    if args.data_dir:
        discovery["data_dir"] = str(args.data_dir)
    if args.groups_file:
        discovery["groups_file"] = str(args.groups_file)
    paths = discover_models(discovery)

    times = {}
    if args.baseline_results:
        times = baseline_times(args.baseline_results, args.baseline_prefix)
        selected = []
        for path in paths:
            value = times.get(model_name(path, discovery))
            if value is None:
                if args.include_missing_baseline:
                    selected.append(path)
                continue
            if args.min_baseline_seconds <= value <= args.max_baseline_seconds:
                selected.append(path)
        paths = sorted(selected, key=lambda path: (times.get(path.stem, float("inf")), path.name))
    if args.limit:
        paths = paths[: args.limit]

    configs = [
        mc_config("aig_original", "AIG original", binary, args.ctg_depth, "aig"),
        mc_config(
            "aig_fanout_desc", "AIG fanout desc", binary, args.ctg_depth,
            "aig", input_order="fanout-desc",
        ),
        mc_config(
            "aig_fanout_asc", "AIG fanout asc", binary, args.ctg_depth,
            "aig", input_order="fanout-asc",
        ),
    ]
    for index, swap_seed in enumerate(SWAP_SEEDS[: args.swap_count], 1):
        configs.append(mc_config(
            f"aig_swap_{index}", f"AIG random swap {index}", binary, args.ctg_depth,
            "aig", input_order="swap", input_order_seed=swap_seed,
        ))
    for policy in ("all", "next", "bad", "shared", "deep"):
        configs.append(mc_config(
            f"xag_{policy}", f"XAG {policy}", binary, args.ctg_depth,
            "xag", xag_policy=policy,
        ))

    tier = (
        f"{args.min_baseline_seconds:g}_{args.max_baseline_seconds:g}"
        if args.baseline_results else "size_order"
    ).replace("inf", "up")
    output = args.output or (
        SCRIPT_DIR / "results" /
        f"mc_transform_hwmcc{args.year}_{args.group}_{tier}.tsv"
    )
    settings = {
        "name": f"transform_{args.year}_{args.group}_{tier}",
        "year": args.year,
        "group": args.group,
        "timeout": args.timeout,
        "workers": args.workers,
        "mc_seed": args.seed,
        "output": str(output),
        "skip_existing": args.skip_existing,
        "model_paths": [str(path) for path in paths],
        "configs": configs,
    }
    if args.data_dir:
        settings["data_dir"] = str(args.data_dir)

    def progress(event: dict) -> None:
        if event["type"] == "started":
            print(
                f"running {event['total']} models x {len(configs)} transforms; "
                f"max processes~{args.workers * len(configs)}, output={output}",
                flush=True,
            )
        elif event["type"] == "row":
            completed = event["completed"]
            if completed <= 10 or completed % 10 == 0 or completed == event["total"]:
                row = event["row"]
                print(
                    f"[{completed}/{event['total']}] {row['name']} "
                    f"baseline={row['aig_original_status']}/"
                    f"{row['aig_original_wall_seconds']} winner={row['winner']}",
                    flush=True,
                )

    runner = ExperimentRunner(settings, progress=progress)

    def stop(_signum: int, _frame: object) -> None:
        runner.cancel()
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
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
