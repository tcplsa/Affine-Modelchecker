#!/usr/bin/env python3
"""Run exact XOR-subset interventions as resumable long-form tasks."""

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
from typing import Any, Dict

from compare_runner import MC_STAT_FIELDS, ProcessRegistry, parse_mc_stats, parse_status


BASE_HEADER = [
    "name", "year", "arm", "seed", "task", "mask", "full_mask",
    "bucket_count", "active_buckets", "selected_xors", "total_xors",
    "status", "wall_seconds", "timeout_seconds", "exit_code",
]
HEADER = BASE_HEADER + list(MC_STAT_FIELDS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--arm", required=True, choices=["benefit", "harm"])
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--workers", type=int, default=80)
    parser.add_argument("--ctg-depth", type=int, default=1)
    parser.add_argument(
        "--lanes", type=int, default=1,
        help="forward AIG/XAG lanes inside each model-checker process",
    )
    parser.add_argument(
        "--models", default="",
        help="optional comma-separated model-name filter",
    )
    return parser.parse_args()


class TaskRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.registry = ProcessRegistry()
        self.cancelled = threading.Event()
        self.write_lock = threading.Lock()

    def cancel(self) -> None:
        self.cancelled.set()
        self.registry.terminate_all()

    def run_task(self, task: Dict[str, Any]) -> Dict[str, str]:
        if self.cancelled.is_set():
            raise KeyboardInterrupt
        model = task["model"]
        is_aig = task["task"] == "baseline_aig"
        command = [
            str(self.args.binary),
            "--forward-aig" if is_aig else "--forward-xag",
            str(self.args.lanes),
            model["path"],
        ]
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
        if self.args.lanes == 1:
            env["MC_PDR_SEED"] = str(self.args.seed)
        else:
            # Multi-lane MC intentionally assigns independent random seeds.
            env.pop("MC_PDR_SEED", None)
        if is_aig:
            env.pop("MC_PDR_XAG_ALLOWLIST_FILE", None)
        else:
            env["MC_PDR_XAG_ALLOWLIST_FILE"] = task["allowlist"]

        started = time.monotonic()
        output = ""
        status = "ERROR"
        exit_code: Any = ""
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
        except OSError:
            proc = None
        if proc is not None:
            self.registry.add(proc)
            try:
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
                        status = parse_status("mc", output, proc.returncode)
                        break
                    except subprocess.TimeoutExpired:
                        continue
                if proc.poll() is None:
                    proc.wait()
                exit_code = proc.returncode if proc.returncode is not None else ""
            finally:
                self.registry.discard(proc)

        row = {
            "name": model["name"],
            "year": str(model["year"]),
            "arm": model["arm"],
            "seed": str(self.args.seed),
            "task": task["task"],
            "mask": str(task["mask"]),
            "full_mask": str(model["full_mask"]),
            "bucket_count": str(len(model["active_buckets"])),
            "active_buckets": ",".join(model["active_buckets"]),
            "selected_xors": str(task["selected_xors"]),
            "total_xors": str(model["total_xors"]),
            "status": status,
            "wall_seconds": "%.6f" % (time.monotonic() - started),
            "timeout_seconds": "%.6f" % self.args.timeout,
            "exit_code": str(exit_code),
        }
        stats = parse_mc_stats(output)
        for field in MC_STAT_FIELDS:
            row[field] = str(stats.get(field, ""))
        return row


def prepare_output(path: Path) -> set[tuple[str, str, str]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    done: set[tuple[str, str, str]] = set()
    if path.exists() and path.stat().st_size:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if reader.fieldnames != HEADER:
                raise SystemExit("existing output header does not match this experiment")
            done = {(row["name"], row["seed"], row["task"]) for row in reader}
    else:
        with path.open("w", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=HEADER, delimiter="\t").writeheader()
    return done


def main() -> int:
    args = parse_args()
    if not args.binary.is_file() or not os.access(args.binary, os.X_OK):
        raise SystemExit("binary is missing or not executable: %s" % args.binary)
    if args.seed < 0 or args.workers < 1 or args.workers > 256:
        raise SystemExit("seed/run id must be non-negative and workers must be 1..256")
    if args.lanes < 1 or args.lanes > 128:
        raise SystemExit("lanes must be 1..128")
    if args.timeout <= 0 or args.ctg_depth < 0:
        raise SystemExit("timeout must be positive and ctg depth non-negative")

    design = json.loads(args.manifest.read_text(encoding="utf-8"))
    models = [model for model in design["models"] if model["arm"] == args.arm]
    if args.models:
        requested = {item.strip() for item in args.models.split(",") if item.strip()}
        available = {model["name"] for model in models}
        missing = sorted(requested - available)
        if missing:
            raise SystemExit("requested models are absent from this arm: %s" % ", ".join(missing))
        models = [model for model in models if model["name"] in requested]
    if not models:
        raise SystemExit("no models selected")
    tasks = []
    for model in models:
        tasks.append({
            "model": model,
            "task": "baseline_aig",
            "mask": -1,
            "allowlist": "",
            "selected_xors": 0,
        })
        for mask in model["masks"]:
            tasks.append({
                "model": model,
                "task": "mask_%03d" % mask["mask"],
                **mask,
            })

    done = prepare_output(args.output)
    tasks = [
        task for task in tasks
        if (task["model"]["name"], str(args.seed), task["task"]) not in done
    ]
    runner = TaskRunner(args)

    def stop(_signum: int, _frame: object) -> None:
        runner.cancel()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    print("arm=%s run=%d lanes=%d pending=%d workers=%d output=%s" % (
        args.arm, args.seed, args.lanes, len(tasks), args.workers, args.output,
    ), flush=True)
    completed = 0
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(runner.run_task, task) for task in tasks]
            for future in as_completed(futures):
                if runner.cancelled.is_set():
                    break
                row = future.result()
                with runner.write_lock:
                    with args.output.open("a", encoding="utf-8", newline="") as handle:
                        csv.DictWriter(handle, fieldnames=HEADER, delimiter="\t").writerow(row)
                completed += 1
                progress_step = 1 if len(tasks) <= 25 else 25
                if completed % progress_step == 0 or completed == len(tasks):
                    print("completed=%d/%d" % (completed, len(tasks)), flush=True)
    except KeyboardInterrupt:
        runner.cancel()
        return 130
    finally:
        if runner.cancelled.is_set():
            runner.cancel()
    print("completed=%d output=%s" % (completed, args.output), flush=True)
    return 130 if runner.cancelled.is_set() else 0


if __name__ == "__main__":
    raise SystemExit(main())
