#!/usr/bin/env python3
"""Run a recoverable multi-year controlled mechanism campaign."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from collect_mechanism_search import (
    DEFAULT_BINARY,
    build_input_configs,
    build_xor_configs,
    parse_ints,
)


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_TIMEOUTS = {
    "fast_unique": 10.0,
    "medium_unique": 30.0,
    "slow_unique": 60.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--axis", choices=["xor", "input"], required=True)
    parser.add_argument(
        "--years", nargs="+", default=["2015", "2017", "2019", "2020"],
    )
    parser.add_argument(
        "--tiers", nargs="+",
        default=["fast_unique", "medium_unique", "slow_unique"],
    )
    parser.add_argument("--solver-seeds", nargs="+", type=int, default=[1, 2, 3, 4, 5])
    parser.add_argument("--transform-seeds", type=parse_ints, default=list(range(1, 9)))
    parser.add_argument("--core-budget", type=int, default=128)
    parser.add_argument("--ctg-depth", type=int, default=1)
    parser.add_argument("--lanes", type=int, default=1)
    parser.add_argument("--baseline-timeout", type=int, default=60)
    parser.add_argument(
        "--timeout", action="append", default=[], metavar="TIER=SECONDS",
    )
    parser.add_argument(
        "--group-pattern", default="hwmcc{year}_groups_mc_{baseline_timeout}.json",
    )
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-jobs", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def timeout_map(overrides: list[str]) -> dict[str, float]:
    result = dict(DEFAULT_TIMEOUTS)
    for spec in overrides:
        try:
            tier, raw = spec.split("=", 1)
            value = float(raw)
        except ValueError as error:
            raise SystemExit(f"invalid timeout {spec!r}") from error
        if value <= 0:
            raise SystemExit("timeouts must be positive")
        result[tier] = value
    return result


def main() -> int:
    args = parse_args()
    builder = build_xor_configs if args.axis == "xor" else build_input_configs
    config_count = len(builder(
        args.binary, args.ctg_depth, args.transform_seeds, args.lanes,
    ))
    processes_per_model = config_count * args.lanes
    if processes_per_model > args.core_budget:
        raise SystemExit(
            f"{processes_per_model} processes per benchmark exceed "
            f"the {args.core_budget} core budget"
        )
    workers = max(1, args.core_budget // processes_per_model)
    timeouts = timeout_map(args.timeout)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    state_path = args.output_dir / "campaign_state.json"
    jobs = [
        {
            "year": year,
            "tier": tier,
            "solver_seed": solver_seed,
            "timeout": timeouts[tier],
        }
        for tier in args.tiers
        for year in args.years
        for solver_seed in args.solver_seeds
    ]
    if args.max_jobs:
        jobs = jobs[: args.max_jobs]
    state = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "settings": {
            "axis": args.axis,
            "years": args.years,
            "tiers": args.tiers,
            "solver_seeds": args.solver_seeds,
            "transform_seeds": args.transform_seeds,
            "config_count": config_count,
            "lanes": args.lanes,
            "workers": workers,
            "core_budget": args.core_budget,
            "max_processes": workers * processes_per_model,
            "timeouts": timeouts,
            "binary": str(args.binary),
        },
        "jobs": [],
    }
    write_json(state_path, state)
    active: subprocess.Popen[bytes] | None = None
    stop_requested = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True
        if active is not None and active.poll() is None:
            os.killpg(active.pid, signal.SIGTERM)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    failures = 0
    for index, job in enumerate(jobs, 1):
        output = args.output_dir / (
            f"hwmcc{job['year']}_{job['tier']}_{args.axis}"
            f"_s{job['solver_seed']}.tsv"
        )
        groups_file = SCRIPT_DIR / args.group_pattern.format(
            year=job["year"], baseline_timeout=args.baseline_timeout,
        )
        command = [
            sys.executable,
            str(SCRIPT_DIR / "collect_mechanism_search.py"),
            "--axis", args.axis,
            "--year", job["year"],
            "--group", job["tier"],
            "--groups-file", str(groups_file),
            "--timeout", str(job["timeout"]),
            "--workers", str(workers),
            "--solver-seed", str(job["solver_seed"]),
            "--transform-seeds", ",".join(map(str, args.transform_seeds)),
            "--ctg-depth", str(args.ctg_depth),
            "--lanes", str(args.lanes),
            "--binary", str(args.binary),
            "--output", str(output),
            "--skip-existing",
        ]
        record = {
            **job,
            "output": str(output),
            "status": "dry-run" if args.dry_run else "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        state["jobs"].append(record)
        state["updated_at"] = record["started_at"]
        write_json(state_path, state)
        print(
            f"[job {index}/{len(jobs)}] axis={args.axis} year={job['year']} "
            f"tier={job['tier']} solver={job['solver_seed']} "
            f"configs={config_count} workers={workers} "
            f"max_processes={workers * processes_per_model}",
            flush=True,
        )
        if args.dry_run:
            print(" ".join(command), flush=True)
            continue
        active = subprocess.Popen(command, start_new_session=True)
        return_code = active.wait()
        active = None
        record["return_code"] = return_code
        record["status"] = "completed" if return_code == 0 else "failed"
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        state["updated_at"] = record["finished_at"]
        write_json(state_path, state)
        if stop_requested:
            record["status"] = "cancelled"
            write_json(state_path, state)
            return 130
        if return_code:
            failures += 1
    print(f"campaign jobs={len(jobs)} failures={failures} state={state_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
