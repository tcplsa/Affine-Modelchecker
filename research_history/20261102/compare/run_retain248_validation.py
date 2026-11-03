#!/usr/bin/env python3
"""Run the frozen retain248 validation as bounded, resumable tasks."""

from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from compare_runner import MC_STAT_FIELDS, ProcessRegistry, parse_mc_stats, parse_status


CONFIGS = {
    "aig": "--forward-aig",
    "compact_aig": "--forward-aig-compact",
    "full_xag": "--forward-xag",
    "retain248": "--forward-xag",
}
BASE_HEADER = [
    "model_id", "name", "year", "group", "family", "shard", "run", "config",
    "status", "wall_seconds", "timeout_seconds", "exit_code", "total_xors",
    "parent_xors", "retained_xors", "removed_xors",
]
HEADER = BASE_HEADER + list(MC_STAT_FIELDS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--shard", required=True, choices=["server-a", "server-b", "all"])
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--runs", default="1,2,3,4")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--workers", type=int, default=28)
    parser.add_argument("--lanes", type=int, default=4)
    parser.add_argument("--ctg-depth", type=int, default=1)
    return parser.parse_args()


def prepare_output(path: Path) -> set[tuple[str, str, str]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    done: set[tuple[str, str, str]] = set()
    if path.exists() and path.stat().st_size:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if reader.fieldnames != HEADER:
                raise SystemExit("existing output header does not match")
            done = {(row["model_id"], row["run"], row["config"]) for row in reader}
    else:
        with path.open("w", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=HEADER, delimiter="\t").writeheader()
    return done


class Runner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.cancelled = threading.Event()
        self.registry = ProcessRegistry()

    def cancel(self) -> None:
        self.cancelled.set()
        self.registry.terminate_all()

    def run(self, task: dict[str, Any]) -> dict[str, str]:
        model = task["model"]
        config = task["config"]
        if self.cancelled.is_set():
            raise KeyboardInterrupt
        command = [str(self.args.binary), CONFIGS[config], str(self.args.lanes), model["path"]]
        env = os.environ.copy()
        env.update({
            "MC_PDR_STATS": "1",
            "MC_PDR_CTG_DEPTH": str(self.args.ctg_depth),
            "MC_PDR_INPUT_ORDER": "original",
            "MC_PDR_INPUT_ORDER_SEED": "1",
            "MC_PDR_XAG_POLICY": "all",
            "MC_PDR_XAG_FRACTION": "1.0",
            "MC_PDR_PERTURB": "",
        })
        # Four lanes are independent randomized portfolios; the run number is a repeat id.
        env.pop("MC_PDR_SEED", None)
        if config == "retain248":
            env["MC_PDR_XAG_ALLOWLIST_FILE"] = model["allowlist"]
        else:
            env.pop("MC_PDR_XAG_ALLOWLIST_FILE", None)

        started = time.monotonic()
        output = ""
        status = "ERROR"
        exit_code: Any = ""
        proc: subprocess.Popen[str] | None = None
        try:
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                start_new_session=True,
                env=env,
            )
            self.registry.add(proc)
            while True:
                if self.cancelled.is_set():
                    self.registry.terminate(proc)
                    status = "CANCELLED"
                    break
                remaining = self.args.timeout - (time.monotonic() - started)
                if remaining <= 0:
                    self.registry.terminate(proc)
                    status = "TIMEOUT"
                    break
                try:
                    output, _ = proc.communicate(timeout=min(0.5, remaining))
                    status = parse_status("mc", output, proc.returncode or 0)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if proc.poll() is None:
                proc.wait()
            exit_code = proc.returncode if proc.returncode is not None else ""
        except OSError:
            status = "ERROR"
        finally:
            if proc is not None:
                self.registry.discard(proc)

        row = {
            "model_id": model["id"],
            "name": model["name"],
            "year": str(model["year"]),
            "group": model["group"],
            "family": model["family"],
            "shard": model["shard"],
            "run": str(task["run"]),
            "config": config,
            "status": status,
            "wall_seconds": f"{time.monotonic() - started:.6f}",
            "timeout_seconds": f"{self.args.timeout:.6f}",
            "exit_code": str(exit_code),
            "total_xors": str(model["total_xors"]),
            "parent_xors": str(model["parent_xors"]),
            "retained_xors": str(model["retained_xors"]),
            "removed_xors": str(model["removed_xors"]),
        }
        stats = parse_mc_stats(output)
        for field in MC_STAT_FIELDS:
            row[field] = str(stats.get(field, ""))
        return row


def main() -> int:
    args = parse_args()
    if not args.binary.is_file() or not os.access(args.binary, os.X_OK):
        raise SystemExit(f"missing executable: {args.binary}")
    runs = [int(value) for value in args.runs.split(",") if value.strip()]
    if not runs or args.workers < 1 or args.lanes < 1 or args.timeout <= 0 or args.ctg_depth < 0:
        raise SystemExit("invalid runs, workers, lanes, timeout, or CTG depth")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    models = [
        model for model in manifest["models"]
        if args.shard == "all" or model["shard"] == args.shard
    ]
    done = prepare_output(args.output)
    tasks = [
        {"model": model, "run": run, "config": config}
        for model in models for run in runs for config in CONFIGS
        if (model["id"], str(run), config) not in done
    ]
    print(f"shard={args.shard} models={len(models)} pending={len(tasks)} "
          f"workers={args.workers} lanes={args.lanes}", flush=True)
    runner = Runner(args)

    def stop(_signum: int, _frame: object) -> None:
        runner.cancel()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    completed = 0
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(runner.run, task) for task in tasks]
            for future in as_completed(futures):
                if runner.cancelled.is_set():
                    break
                row = future.result()
                with args.output.open("a", encoding="utf-8", newline="") as handle:
                    csv.DictWriter(handle, fieldnames=HEADER, delimiter="\t").writerow(row)
                completed += 1
                if completed % 25 == 0 or completed == len(tasks):
                    print(f"completed={completed}/{len(tasks)}", flush=True)
    except KeyboardInterrupt:
        runner.cancel()
    finally:
        if runner.cancelled.is_set():
            runner.cancel()
    print(f"completed={completed} output={args.output}", flush=True)
    return 130 if runner.cancelled.is_set() else 0


if __name__ == "__main__":
    raise SystemExit(main())
