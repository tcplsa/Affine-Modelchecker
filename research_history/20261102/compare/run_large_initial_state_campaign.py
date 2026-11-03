#!/usr/bin/env python3
"""Run a recoverable, multi-year initial-state search campaign."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
DEFAULT_TIMEOUTS = {
    "fast_unique": 10.0,
    "medium_unique": 30.0,
    "slow_unique": 60.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Search broad initial-state designs across training years and "
            "runtime tiers. Existing TSV rows are reused."
        )
    )
    parser.add_argument(
        "--years", nargs="+", default=["2015", "2017", "2019", "2020"],
    )
    parser.add_argument(
        "--tiers",
        nargs="+",
        default=["fast_unique", "medium_unique", "slow_unique"],
    )
    parser.add_argument("--design-seeds", nargs="+", type=int, default=[1, 2, 3])
    parser.add_argument("--solver-seeds", nargs="+", type=int, default=[1, 2])
    parser.add_argument("--candidates", type=int, default=64)
    parser.add_argument(
        "--candidate-ids",
        default="",
        help="comma-separated broad-profile state IDs to execute",
    )
    parser.add_argument(
        "--lanes-per-state",
        type=int,
        default=1,
        help="same-representation PDR lanes inside each selected state",
    )
    parser.add_argument(
        "--core-budget",
        type=int,
        default=128,
        help="approximate maximum concurrent modelchecker processes",
    )
    parser.add_argument("--ctg-depth", type=int, default=1)
    parser.add_argument("--baseline-timeout", type=int, default=60)
    parser.add_argument(
        "--timeout",
        action="append",
        default=[],
        metavar="TIER=SECONDS",
        help="override a tier timeout; may be repeated",
    )
    parser.add_argument(
        "--group-pattern",
        default="hwmcc{year}_groups_mc_{baseline_timeout}.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=SCRIPT_DIR / "results" / "initial_state_large",
    )
    parser.add_argument(
        "--binary",
        type=Path,
        default=ROOT / "Modelchecker-bidirectional"
        / "modelchecker" / "modelchecker",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=0,
        help="run at most this many matrix jobs; zero runs the full matrix",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def timeout_map(overrides: list[str]) -> dict[str, float]:
    result = dict(DEFAULT_TIMEOUTS)
    for spec in overrides:
        try:
            tier, raw_seconds = spec.split("=", 1)
            seconds = float(raw_seconds)
        except ValueError as error:
            raise SystemExit(f"invalid --timeout {spec!r}; use TIER=SECONDS") from error
        if seconds <= 0.0:
            raise SystemExit(f"timeout must be positive: {spec}")
        result[tier] = seconds
    return result


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    if args.candidates < 16:
        raise SystemExit("--candidates must be at least 16 for the broad profile")
    if args.core_budget < 1:
        raise SystemExit("--core-budget must be positive")
    if args.lanes_per_state < 1:
        raise SystemExit("--lanes-per-state must be positive")
    candidate_ids = [
        item.strip() for item in args.candidate_ids.split(",") if item.strip()
    ]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise SystemExit("--candidate-ids contains duplicates")
    selected_candidates = len(candidate_ids) if candidate_ids else args.candidates
    processes_per_model = selected_candidates * args.lanes_per_state
    if processes_per_model > args.core_budget:
        raise SystemExit(
            "one benchmark requires "
            f"{processes_per_model} processes, exceeding --core-budget "
            f"{args.core_budget}"
        )
    timeouts = timeout_map(args.timeout)
    missing_timeouts = set(args.tiers) - set(timeouts)
    if missing_timeouts:
        raise SystemExit(
            "missing timeouts for tiers: " + ", ".join(sorted(missing_timeouts))
        )
    workers = max(1, args.core_budget // processes_per_model)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    state_path = args.output_dir / "campaign_state.json"
    jobs = []
    for tier in args.tiers:
        for year in args.years:
            for design_seed in args.design_seeds:
                for solver_seed in args.solver_seeds:
                    jobs.append({
                        "year": year,
                        "tier": tier,
                        "design_seed": design_seed,
                        "solver_seed": solver_seed,
                        "timeout": timeouts[tier],
                    })
    if args.max_jobs:
        jobs = jobs[: args.max_jobs]

    state = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "settings": {
            "years": args.years,
            "tiers": args.tiers,
            "design_seeds": args.design_seeds,
            "solver_seeds": args.solver_seeds,
            "candidates": args.candidates,
            "candidate_ids": candidate_ids,
            "selected_candidates": selected_candidates,
            "lanes_per_state": args.lanes_per_state,
            "processes_per_model": processes_per_model,
            "core_budget": args.core_budget,
            "workers": workers,
            "ctg_depth": args.ctg_depth,
            "timeouts": timeouts,
            "binary": str(args.binary),
        },
        "jobs": [],
    }
    write_json(state_path, state)
    active: subprocess.Popen[bytes] | None = None
    stop_requested = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal active, stop_requested
        stop_requested = True
        if active is not None and active.poll() is None:
            os.killpg(active.pid, signal.SIGTERM)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    failures = 0
    for index, job in enumerate(jobs, 1):
        year = job["year"]
        tier = job["tier"]
        design_seed = job["design_seed"]
        solver_seed = job["solver_seed"]
        group_file = SCRIPT_DIR / args.group_pattern.format(
            year=year, baseline_timeout=args.baseline_timeout,
        )
        output = args.output_dir / (
            f"hwmcc{year}_{tier}_broad{args.candidates}"
            f"_d{design_seed}_s{solver_seed}.tsv"
        )
        command = [
            sys.executable,
            str(SCRIPT_DIR / "collect_initial_state_search.py"),
            "--year", year,
            "--group", tier,
            "--groups-file", str(group_file),
            "--timeout", str(job["timeout"]),
            "--workers", str(workers),
            "--candidates", str(args.candidates),
            "--design-profile", "broad",
            "--lanes-per-state", str(args.lanes_per_state),
            "--solver-seed", str(solver_seed),
            "--design-seed", str(design_seed),
            "--ctg-depth", str(args.ctg_depth),
            "--binary", str(args.binary),
            "--output", str(output),
            "--skip-existing",
        ]
        if candidate_ids:
            command.extend(["--candidate-ids", ",".join(candidate_ids)])
        record = {
            **job,
            "output": str(output),
            "status": "dry-run" if args.dry_run else "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        state["jobs"].append(record)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        write_json(state_path, state)
        print(
            f"[job {index}/{len(jobs)}] year={year} tier={tier} "
            f"design={design_seed} solver={solver_seed} timeout={job['timeout']:g}s "
            f"workers={workers} selected={selected_candidates} "
            f"lanes={args.lanes_per_state} "
            f"max_processes={workers * processes_per_model}",
            flush=True,
        )
        if args.dry_run:
            print(" ".join(command), flush=True)
            continue
        try:
            active = subprocess.Popen(command, start_new_session=True)
            return_code = active.wait()
        except KeyboardInterrupt:
            if active is not None and active.poll() is None:
                os.killpg(active.pid, signal.SIGTERM)
                active.wait()
            record["status"] = "cancelled"
            record["finished_at"] = datetime.now(timezone.utc).isoformat()
            state["updated_at"] = record["finished_at"]
            write_json(state_path, state)
            return 130
        finally:
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
            print(f"job failed with exit code {return_code}: {output}", flush=True)

    print(
        f"campaign jobs={len(jobs)} failures={failures} state={state_path}",
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
