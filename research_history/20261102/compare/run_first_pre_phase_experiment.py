#!/usr/bin/env python3
"""Measure causal effects of phase-selecting only the first get-pre model."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from compare_runner import MC_STAT_FIELDS, ProcessRegistry, parse_mc_stats, parse_status


REPRESENTATIONS = {"aig": "--forward-aig", "xag": "--forward-xag"}
HEADER = [
    "model_id", "name", "year", "tier", "representation", "strategy",
    "phase_mode", "phase_seed", "status", "wall_seconds", "timeout_seconds",
    "exit_code", "first_target_hash", "semantic_events",
] + list(MC_STAT_FIELDS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--trace-root", required=True, type=Path)
    parser.add_argument("--representations", default="aig,xag")
    parser.add_argument("--random-seeds", default="1,2,3,4,5,6,7,8")
    parser.add_argument("--workers", type=int, default=64)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--solver-seed", type=int, default=350000)
    parser.add_argument("--ctg-depth", type=int, default=1)
    parser.add_argument("--limit-models", type=int, default=0)
    return parser.parse_args()


def strategies(seed_text: str) -> list[tuple[str, str, int]]:
    result = [(mode, mode, 0) for mode in ("default", "zero", "one", "init")]
    for value in seed_text.split(","):
        seed = int(value.strip())
        result.append((f"random-{seed}", "random", seed))
    return result


def prepare_output(path: Path) -> set[tuple[str, str, str]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=HEADER, delimiter="\t").writeheader()
        return set()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != HEADER:
            raise SystemExit("existing first-pre output header does not match")
        return {(row["model_id"], row["representation"], row["strategy"]) for row in reader}


def trace_identity(task: dict[str, Any]) -> str:
    value = f"{task['model']['id']}|{task['representation']}|{task['strategy']}"
    return hashlib.sha256(value.encode()).hexdigest()[:20]


def read_first_target(directory: Path) -> tuple[str, int]:
    events = 0
    target_hash = ""
    for path in directory.glob("*.semantic.tsv"):
        with path.open(encoding="utf-8", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                events += 1
                if not target_hash and row.get("event") == "state-target":
                    target_hash = row.get("literal_hash", "")
    return target_hash, events


class Runner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.registry = ProcessRegistry()
        self.cancelled = threading.Event()

    def cancel(self) -> None:
        self.cancelled.set()
        self.registry.terminate_all()

    def run(self, task: dict[str, Any]) -> dict[str, str]:
        model = task["model"]
        directory = self.args.trace_root / trace_identity(task)
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)
        command = [
            str(self.args.binary), REPRESENTATIONS[task["representation"]], "1",
            str(model["path"]),
        ]
        env = os.environ.copy()
        env.update({
            "MC_PDR_STATS": "1", "MC_PDR_PHASE_STATS": "0",
            "MC_PDR_CTG_DEPTH": str(self.args.ctg_depth), "MC_PDR_CTG_TRIES": "3",
            "MC_PDR_INPUT_ORDER": "original", "MC_PDR_INPUT_ORDER_SEED": "1",
            "MC_PDR_PERTURB": "", "MC_PDR_XAG_POLICY": "all",
            "MC_PDR_XAG_FRACTION": "1.0", "MC_PDR_XAG_STABLE_SLOTS": "0",
            "MC_PDR_MINISAT_ELIMINATE": "1", "MC_PDR_CANONICAL_MINISAT": "1",
            "MC_PDR_CANONICAL_CNF": "1", "MC_PDR_CADICAL_VAR_ORDER": "first",
            "MC_PDR_CADICAL_ORDER_TRANSLATION": "first",
            "MC_PDR_CADICAL_ORDER_LIFT": "first", "MC_PDR_CADICAL_REVERSE": "0",
            "MC_PDR_SEED": str(self.args.solver_seed),
            "MC_PDR_FIRST_PRE_PHASE": task["phase_mode"],
            "MC_PDR_FIRST_PRE_PHASE_SEED": str(task["phase_seed"]),
            "MC_PDR_SEMANTIC_TRACE_DIR": str(directory),
            "MC_PDR_SEMANTIC_TRACE_MAX_EVENTS": "4",
        })
        env.pop("MC_PDR_QUERY_TRACE_DIR", None)

        started = time.monotonic()
        output, status, exit_code = "", "ERROR", ""
        proc: subprocess.Popen[str] | None = None
        try:
            proc = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, errors="replace", start_new_session=True, env=env,
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
            if not output and proc.stdout is not None:
                output, _ = proc.communicate(timeout=5)
            exit_code = str(proc.returncode if proc.returncode is not None else "")
        except (OSError, subprocess.TimeoutExpired):
            status = "ERROR"
        finally:
            if proc is not None:
                self.registry.discard(proc)

        target_hash, events = read_first_target(directory)
        shutil.rmtree(directory, ignore_errors=True)
        row = {
            "model_id": str(model["id"]), "name": str(model["name"]),
            "year": str(model["year"]), "tier": str(model["tier"]),
            "representation": task["representation"], "strategy": task["strategy"],
            "phase_mode": task["phase_mode"], "phase_seed": str(task["phase_seed"]),
            "status": status, "wall_seconds": f"{time.monotonic() - started:.6f}",
            "timeout_seconds": f"{self.args.timeout:.6f}", "exit_code": exit_code,
            "first_target_hash": target_hash, "semantic_events": str(events),
        }
        stats = parse_mc_stats(output)
        for field in MC_STAT_FIELDS:
            row[field] = str(stats.get(field, ""))
        return row


def main() -> int:
    args = parse_args()
    reps = [item.strip() for item in args.representations.split(",") if item.strip()]
    if any(rep not in REPRESENTATIONS for rep in reps):
        raise SystemExit("invalid representation")
    design = json.loads(args.manifest.read_text(encoding="utf-8"))
    models = design["models"][:args.limit_models or None]
    treatments = strategies(args.random_seeds)
    done = prepare_output(args.output)
    args.trace_root.mkdir(parents=True, exist_ok=True)
    tasks = [
        {"model": model, "representation": rep, "strategy": strategy,
         "phase_mode": mode, "phase_seed": seed}
        for model in models for rep in reps for strategy, mode, seed in treatments
        if (str(model["id"]), rep, strategy) not in done
    ]
    runner = Runner(args)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    print(f"models={len(models)} strategies={len(treatments)} pending={len(tasks)} workers={args.workers}", flush=True)
    completed = 0
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(runner.run, task) for task in tasks]
            for future in as_completed(futures):
                row = future.result()
                with args.output.open("a", encoding="utf-8", newline="") as handle:
                    csv.DictWriter(handle, fieldnames=HEADER, delimiter="\t").writerow(row)
                completed += 1
                if completed % 40 == 0 or completed == len(tasks):
                    print(f"completed={completed}/{len(tasks)}", flush=True)
    finally:
        if runner.cancelled.is_set():
            runner.cancel()
    return 130 if runner.cancelled.is_set() else 0


if __name__ == "__main__":
    raise SystemExit(main())
