#!/usr/bin/env python3
"""Collect replayable SAT query streams for selected causal models."""

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

from compare_runner import ProcessRegistry, parse_status
from run_representation_simplification import REPRESENTATIONS, decode_config, parse_instrumentation


HEADER = [
    "model_id", "name", "year", "tier", "category", "run", "paired_seed",
    "config", "representation", "origin", "translation_order", "lift_order",
    "status", "wall_seconds", "timeout_seconds", "exit_code", "winner_thread",
    "trace_key", "trace_files", "trace_bytes",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--trace-root", required=True, type=Path)
    parser.add_argument("--configs", default="aig_canonical-cnf,xag_canonical-cnf")
    parser.add_argument("--origins", default="first:first,numeric:numeric")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--lanes", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--max-trace-mb", type=float, default=128.0)
    parser.add_argument("--ctg-depth", type=int, default=1)
    parser.add_argument("--limit-models", type=int, default=0)
    return parser.parse_args()


def paired_seed(run: int) -> int:
    return (110_000 if run <= 3 else 310_000) + 10_000 * run


def trace_key(task: dict[str, Any]) -> str:
    raw = "|".join((
        str(task["model"]["id"]), str(task["run"]), str(task["config"]),
        str(task["translation_order"]), str(task["lift_order"]),
    ))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def prepare_output(path: Path, trace_root: Path) -> set[tuple[str, str, str, str]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    trace_root.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=HEADER, delimiter="\t").writeheader()
        return set()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != HEADER:
            raise SystemExit("existing query-trace output header does not match")
        done = set()
        for row in reader:
            directory = trace_root / row["trace_key"]
            if directory.is_dir() and any(
                trace.stat().st_size > 0 for trace in directory.glob("*.mcpdrq")
            ):
                done.add((row["model_id"], row["run"], row["config"], row["origin"]))
        return done


class Runner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.registry = ProcessRegistry()
        self.cancelled = threading.Event()

    def cancel(self) -> None:
        self.cancelled.set()
        self.registry.terminate_all()

    def run(self, task: dict[str, Any]) -> dict[str, str]:
        if self.cancelled.is_set():
            return {}
        model = task["model"]
        representation, _, controls = decode_config(task["config"])
        translation_order = str(task["translation_order"])
        lift_order = str(task["lift_order"])
        origin = f"{translation_order}__{lift_order}"
        seed = paired_seed(int(task["run"]))
        key = trace_key(task)
        directory = self.args.trace_root / key
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)

        command = [
            str(self.args.binary), REPRESENTATIONS[representation], str(self.args.lanes),
            str(model["path"]),
        ]
        env = os.environ.copy()
        env.update({
            "MC_PDR_STATS": "1", "MC_PDR_PHASE_STATS": "1",
            "MC_PDR_CTG_DEPTH": str(self.args.ctg_depth),
            "MC_PDR_INPUT_ORDER": "original", "MC_PDR_INPUT_ORDER_SEED": "1",
            "MC_PDR_PERTURB": "", "MC_PDR_XAG_POLICY": "all",
            "MC_PDR_XAG_FRACTION": "1.0", "MC_PDR_XAG_STABLE_SLOTS": "0",
            "MC_PDR_MINISAT_ELIMINATE": str(controls["eliminate"]),
            "MC_PDR_CANONICAL_MINISAT": str(controls["canonical_minisat"]),
            "MC_PDR_CANONICAL_CNF": str(controls["canonical_cnf"]),
            "MC_PDR_CADICAL_VAR_ORDER": "first",
            "MC_PDR_CADICAL_ORDER_TRANSLATION": translation_order,
            "MC_PDR_CADICAL_ORDER_LIFT": lift_order,
            "MC_PDR_CADICAL_REVERSE": "0", "MC_PDR_SEED": str(seed),
            "MC_PDR_QUERY_TRACE_DIR": str(directory),
        })
        for key_name in ("MC_PDR_XAG_ALLOWLIST_FILE", "MC_PDR_PERTURB_SEED"):
            env.pop(key_name, None)

        started = time.monotonic()
        output, status, exit_code = "", "ERROR", ""
        proc: subprocess.Popen[str] | None = None
        try:
            proc = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, errors="replace", start_new_session=True, env=env,
            )
            self.registry.add(proc)
            next_size_check = time.monotonic() + 1.0
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
                now = time.monotonic()
                if self.args.max_trace_mb > 0 and now >= next_size_check:
                    trace_bytes = sum(
                        path.stat().st_size for path in directory.glob("*.mcpdrq")
                    )
                    if trace_bytes >= self.args.max_trace_mb * 1024 * 1024:
                        self.registry.terminate(proc)
                        status = "TRACE_LIMIT"
                        break
                    next_size_check = now + 1.0
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

        instrument = parse_instrumentation(output)
        winner_thread = instrument.get("winner_thread", "") or "0"
        winner_prefix = f"thread-{winner_thread}-"
        for path in directory.glob("*.mcpdrq"):
            if not path.name.startswith(winner_prefix):
                path.unlink()
        traces = list(directory.glob("*.mcpdrq"))
        return {
            "model_id": str(model["id"]), "name": str(model["name"]),
            "year": str(model["year"]), "tier": str(model["tier"]),
            "category": str(model["category"]), "run": str(task["run"]),
            "paired_seed": str(seed), "config": str(task["config"]),
            "representation": representation, "origin": origin,
            "translation_order": translation_order, "lift_order": lift_order,
            "status": status, "wall_seconds": f"{time.monotonic() - started:.6f}",
            "timeout_seconds": f"{self.args.timeout:.6f}", "exit_code": exit_code,
            "winner_thread": winner_thread,
            "trace_key": directory.name, "trace_files": str(len(traces)),
            "trace_bytes": str(sum(path.stat().st_size for path in traces)),
        }


def main() -> int:
    args = parse_args()
    configs = [item.strip() for item in args.configs.split(",") if item.strip()]
    origins = []
    for item in args.origins.split(","):
        parts = item.strip().split(":")
        if len(parts) != 2:
            raise SystemExit(f"invalid trace origin: {item}")
        origins.append((parts[0], parts[1]))
    for config in configs:
        decode_config(config)
    models = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    if args.limit_models > 0:
        models = models[:args.limit_models]
    done = prepare_output(args.output, args.trace_root)
    tasks = [
        {
            "model": model, "run": int(run), "config": config,
            "translation_order": translation, "lift_order": lift,
        }
        for model in models for run in model["trace_runs"] for config in configs
        for translation, lift in origins
        if (
            str(model["id"]), str(run), config, f"{translation}__{lift}"
        ) not in done
    ]
    runner = Runner(args)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    print(
        f"models={len(models)} pending={len(tasks)} workers={args.workers} lanes={args.lanes}",
        flush=True,
    )
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
                if completed % 5 == 0 or completed == len(tasks):
                    print(f"completed={completed}/{len(tasks)}", flush=True)
    finally:
        if runner.cancelled.is_set():
            runner.cancel()
    return 130 if runner.cancelled.is_set() else 0


if __name__ == "__main__":
    raise SystemExit(main())
