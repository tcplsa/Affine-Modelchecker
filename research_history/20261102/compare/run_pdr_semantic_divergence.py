#!/usr/bin/env python3
"""Run paired single-lane PDR jobs with compact semantic trajectory traces."""

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
from run_representation_simplification import REPRESENTATIONS, decode_config


HEADER = [
    "model_id", "name", "year", "tier", "run", "seed", "config",
    "representation", "origin", "translation_order", "lift_order",
    "status", "wall_seconds", "timeout_seconds", "exit_code",
    "trace_key", "semantic_events", "semantic_bytes", "semantic_capped",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--trace-root", required=True, type=Path)
    parser.add_argument("--configs", default="aig_canonical-cnf,xag_canonical-cnf")
    parser.add_argument("--origins", default="first:first,numeric:first")
    parser.add_argument("--run", type=int, default=4)
    parser.add_argument("--seed", type=int, default=350000)
    parser.add_argument("--workers", type=int, default=48)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--max-events", type=int, default=20000)
    parser.add_argument("--ctg-depth", type=int, default=1)
    parser.add_argument("--limit-models", type=int, default=0)
    return parser.parse_args()


def parse_origins(value: str) -> list[tuple[str, str]]:
    origins = []
    for item in value.split(","):
        parts = item.strip().split(":")
        if len(parts) != 2 or parts[0] not in {"first", "numeric"} or parts[1] not in {"first", "numeric"}:
            raise SystemExit(f"invalid semantic origin: {item}")
        origins.append((parts[0], parts[1]))
    return origins


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
            raise SystemExit("existing semantic output header does not match")
        done = set()
        for row in reader:
            directory = trace_root / row["trace_key"]
            if directory.is_dir() and any(
                item.stat().st_size > 0 for item in directory.glob("*.semantic.tsv")
            ):
                done.add((row["model_id"], row["config"], row["origin"], row["run"]))
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
        key = trace_key(task)
        directory = self.args.trace_root / key
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)

        command = [
            str(self.args.binary), REPRESENTATIONS[representation], "1", str(model["path"]),
        ]
        env = os.environ.copy()
        env.update({
            "MC_PDR_STATS": "0", "MC_PDR_PHASE_STATS": "0",
            "MC_PDR_CTG_DEPTH": str(self.args.ctg_depth),
            "MC_PDR_CTG_TRIES": "3", "MC_PDR_INPUT_ORDER": "original",
            "MC_PDR_INPUT_ORDER_SEED": "1", "MC_PDR_PERTURB": "",
            "MC_PDR_XAG_POLICY": "all", "MC_PDR_XAG_FRACTION": "1.0",
            "MC_PDR_XAG_STABLE_SLOTS": "0",
            "MC_PDR_MINISAT_ELIMINATE": str(controls["eliminate"]),
            "MC_PDR_CANONICAL_MINISAT": str(controls["canonical_minisat"]),
            "MC_PDR_CANONICAL_CNF": str(controls["canonical_cnf"]),
            "MC_PDR_CADICAL_VAR_ORDER": "first",
            "MC_PDR_CADICAL_ORDER_TRANSLATION": str(task["translation_order"]),
            "MC_PDR_CADICAL_ORDER_LIFT": str(task["lift_order"]),
            "MC_PDR_CADICAL_REVERSE": "0", "MC_PDR_SEED": str(task["seed"]),
            "MC_PDR_SEMANTIC_TRACE_DIR": str(directory),
            "MC_PDR_SEMANTIC_TRACE_MAX_EVENTS": str(self.args.max_events),
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

        traces = list(directory.glob("*.semantic.tsv"))
        semantic_bytes = sum(path.stat().st_size for path in traces)
        semantic_events = 0
        for path in traces:
            with path.open(encoding="utf-8", errors="replace") as handle:
                semantic_events += max(0, sum(1 for _ in handle) - 1)
        return {
            "model_id": str(model["id"]), "name": str(model["name"]),
            "year": str(model["year"]), "tier": str(model["tier"]),
            "run": str(task["run"]), "seed": str(task["seed"]),
            "config": str(task["config"]), "representation": representation,
            "origin": f"{task['translation_order']}__{task['lift_order']}",
            "translation_order": str(task["translation_order"]),
            "lift_order": str(task["lift_order"]), "status": status,
            "wall_seconds": f"{time.monotonic() - started:.6f}",
            "timeout_seconds": f"{self.args.timeout:.6f}",
            "exit_code": exit_code, "trace_key": key,
            "semantic_events": str(semantic_events),
            "semantic_bytes": str(semantic_bytes),
            "semantic_capped": "1" if semantic_events >= self.args.max_events else "0",
        }


def main() -> int:
    args = parse_args()
    configs = [item.strip() for item in args.configs.split(",") if item.strip()]
    origins = parse_origins(args.origins)
    for config in configs:
        decode_config(config)
    models = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    if args.limit_models > 0:
        models = models[:args.limit_models]
    done = prepare_output(args.output, args.trace_root)
    tasks = [
        {
            "model": model, "run": args.run, "seed": args.seed,
            "config": config, "translation_order": translation,
            "lift_order": lift,
        }
        for model in models for config in configs for translation, lift in origins
        if (str(model["id"]), config, f"{translation}__{lift}", str(args.run)) not in done
    ]
    runner = Runner(args)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    print(f"models={len(models)} pending={len(tasks)} workers={args.workers}", flush=True)
    completed = 0
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(runner.run, task) for task in tasks]
            for future in as_completed(futures):
                row = future.result()
                if row:
                    with args.output.open("a", encoding="utf-8", newline="") as handle:
                        csv.DictWriter(handle, fieldnames=HEADER, delimiter="\t").writerow(row)
                completed += 1
                if completed % 20 == 0 or completed == len(tasks):
                    print(f"completed={completed}/{len(tasks)}", flush=True)
    finally:
        runner.cancel()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
