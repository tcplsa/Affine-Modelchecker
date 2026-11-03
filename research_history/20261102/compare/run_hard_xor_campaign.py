#!/usr/bin/env python3
"""Run recoverable fixed-seed hard-instance XOR policy experiments."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from collect_hard_xor_search import build_hard_xor_configs
from collect_mechanism_search import DEFAULT_BINARY


SCRIPT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", required=True)
    parser.add_argument("--group", required=True)
    parser.add_argument("--solver-seeds", nargs="+", type=int, default=[1, 2, 3, 4, 5])
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--core-budget", type=int, default=128)
    parser.add_argument("--ctg-depth", type=int, default=1)
    parser.add_argument("--lanes", type=int, default=1)
    parser.add_argument("--profile", choices=["screen", "validate"], default="screen")
    parser.add_argument(
        "--groups-pattern", default="hwmcc{year}_groups_xag_hard.json",
    )
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    if args.timeout <= 0 or args.core_budget <= 0 or args.lanes <= 0:
        raise SystemExit("timeout, core budget, and lanes must be positive")
    configs = build_hard_xor_configs(
        args.binary, args.ctg_depth, args.lanes, args.profile,
    )
    groups_files: dict[str, Path] = {}
    for year in args.years:
        groups_file = SCRIPT_DIR / args.groups_pattern.format(year=year)
        if not groups_file.is_file():
            raise SystemExit(f"groups file not found: {groups_file}")
        groups_payload = json.loads(groups_file.read_text(encoding="utf-8"))
        group = groups_payload.get("groups", {}).get(args.group)
        if not isinstance(group, list) or not group:
            raise SystemExit(
                f"group {args.group!r} is missing or empty in {groups_file}"
            )
        groups_files[year] = groups_file
    processes_per_model = len(configs) * args.lanes
    if processes_per_model > args.core_budget:
        raise SystemExit(
            f"{processes_per_model} processes per model exceed "
            f"core budget {args.core_budget}"
        )
    workers = max(1, args.core_budget // processes_per_model)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    state_path = args.output_dir / "campaign_state.json"
    jobs = [
        {"year": year, "solver_seed": seed}
        for year in args.years
        for seed in args.solver_seeds
    ]
    state = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "settings": {
            "years": args.years,
            "group": args.group,
            "solver_seeds": args.solver_seeds,
            "timeout": args.timeout,
            "profile": args.profile,
            "config_count": len(configs),
            "lanes": args.lanes,
            "workers": workers,
            "core_budget": args.core_budget,
            "max_processes": workers * processes_per_model,
            "groups_pattern": args.groups_pattern,
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
        year = job["year"]
        seed = job["solver_seed"]
        output = args.output_dir / (
            f"hwmcc{year}_{args.group}_hardxor_s{seed}.tsv"
        )
        groups_file = groups_files[year]
        command = [
            sys.executable,
            str(SCRIPT_DIR / "collect_hard_xor_search.py"),
            "--year", year,
            "--group", args.group,
            "--groups-file", str(groups_file),
            "--timeout", str(args.timeout),
            "--workers", str(workers),
            "--solver-seed", str(seed),
            "--ctg-depth", str(args.ctg_depth),
            "--lanes", str(args.lanes),
            "--profile", args.profile,
            "--binary", str(args.binary),
            "--output", str(output),
            "--skip-existing",
        ]
        record = {
            **job,
            "output": str(output),
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        state["jobs"].append(record)
        state["updated_at"] = record["started_at"]
        write_json(state_path, state)
        print(
            f"[job {index}/{len(jobs)}] year={year} seed={seed} "
            f"group={args.group} timeout={args.timeout:g}s "
            f"configs={len(configs)} workers={workers} "
            f"max_processes={workers * processes_per_model}",
            flush=True,
        )
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
