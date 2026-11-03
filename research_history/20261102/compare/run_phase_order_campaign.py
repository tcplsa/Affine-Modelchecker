#!/usr/bin/env python3
"""Run paired transition/lift CaDiCaL presentation experiments."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from compare_runner import MC_STAT_FIELDS, ProcessRegistry, parse_mc_stats, parse_status
from run_representation_simplification import (
    CNF_FIELDS,
    FEATURE_FIELDS,
    PHASES,
    QUERY_FIELDS,
    REPRESENTATIONS,
    decode_config,
    parse_instrumentation,
)
from run_variable_order_campaign import ORDERS


VAR_ORDER_RE = re.compile(
    r"^c PDR_VAR_ORDER thread=(\S+) phase=(\S+) mode=(\S+) present=(\d+)$",
    re.MULTILINE,
)
HEADER = [
    "model_id", "name", "year", "tier", "shard", "run", "paired_seed",
    "config", "representation", "regime", "treatment",
    "translation_order", "lift_order",
    "minisat_eliminate", "canonical_minisat", "canonical_cnf",
    *FEATURE_FIELDS, "status", "wall_seconds", "timeout_seconds", "exit_code",
    "winner_thread", "timeout_phase", "translation_order_vars", "lift_order_vars",
] + [f"phase_{phase}" for phase in PHASES] + list(CNF_FIELDS) + list(QUERY_FIELDS) + list(MC_STAT_FIELDS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--configs", default="xag_canonical-cnf")
    parser.add_argument(
        "--treatments",
        default="first:first,numeric:first,first:numeric,numeric:numeric",
    )
    parser.add_argument("--runs", default="1,2,3")
    parser.add_argument("--workers", type=int, default=30)
    parser.add_argument("--lanes", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--ctg-depth", type=int, default=1)
    parser.add_argument("--seed-base", type=int, default=100_000)
    parser.add_argument("--seed-step", type=int, default=10_000)
    parser.add_argument("--limit-models", type=int, default=0)
    return parser.parse_args()


def parse_treatments(value: str) -> list[tuple[str, str]]:
    treatments: list[tuple[str, str]] = []
    for item in value.split(","):
        parts = item.strip().split(":")
        if len(parts) != 2 or any(part not in ORDERS for part in parts):
            raise SystemExit(f"invalid phase-order treatment: {item}")
        treatments.append((parts[0], parts[1]))
    return treatments


def prepare_output(path: Path) -> set[tuple[str, str, str, str]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=HEADER, delimiter="\t").writeheader()
        return set()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != HEADER:
            raise SystemExit("existing phase-order output header does not match")
        return {
            (row["model_id"], row["run"], row["config"], row["treatment"])
            for row in reader
        }


def order_counts(output: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for match in VAR_ORDER_RE.finditer(output):
        result.setdefault(f"{match.group(2)}_order_vars", match.group(4))
    return result


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
        representation, regime, controls = decode_config(task["config"])
        translation_order = str(task["translation_order"])
        lift_order = str(task["lift_order"])
        treatment = f"{translation_order}__{lift_order}"
        paired_seed = self.args.seed_base + self.args.seed_step * int(task["run"])
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
            "MC_PDR_CADICAL_REVERSE": "0", "MC_PDR_SEED": str(paired_seed),
        })
        for key in (
            "MC_PDR_XAG_ALLOWLIST_FILE", "MC_PDR_PERTURB_SEED",
            "MC_PDR_QUERY_TRACE_DIR",
        ):
            env.pop(key, None)

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

        row = {
            "model_id": str(model["id"]), "name": str(model["name"]),
            "year": str(model["year"]), "tier": str(model["tier"]),
            "shard": str(model.get("shard", "")), "run": str(task["run"]),
            "paired_seed": str(paired_seed), "config": str(task["config"]),
            "representation": representation, "regime": regime,
            "treatment": treatment, "translation_order": translation_order,
            "lift_order": lift_order,
            "minisat_eliminate": str(controls["eliminate"]),
            "canonical_minisat": str(controls["canonical_minisat"]),
            "canonical_cnf": str(controls["canonical_cnf"]),
            "status": status, "wall_seconds": f"{time.monotonic() - started:.6f}",
            "timeout_seconds": f"{self.args.timeout:.6f}", "exit_code": exit_code,
        }
        for field in FEATURE_FIELDS:
            row[field] = str(model.get(field[len("feature_"):], ""))
        instrument = parse_instrumentation(output)
        instrument_fields = (
            "winner_thread", "timeout_phase", *[f"phase_{phase}" for phase in PHASES],
            *CNF_FIELDS, *QUERY_FIELDS,
        )
        for field in instrument_fields:
            row[field] = instrument.get(field, "")
        row.update(order_counts(output))
        stats = parse_mc_stats(output)
        for field in MC_STAT_FIELDS:
            row[field] = str(stats.get(field, ""))
        return row


def main() -> int:
    args = parse_args()
    configs = [item.strip() for item in args.configs.split(",") if item.strip()]
    treatments = parse_treatments(args.treatments)
    runs = [int(item) for item in args.runs.split(",") if item.strip()]
    for config in configs:
        decode_config(config)
    models = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    if args.limit_models > 0:
        models = models[:args.limit_models]
    done = prepare_output(args.output)
    tasks = [
        {
            "model": model, "run": run, "config": config,
            "translation_order": translation, "lift_order": lift,
        }
        for run in runs for model in models for config in configs
        for translation, lift in treatments
        if (
            str(model["id"]), str(run), config, f"{translation}__{lift}"
        ) not in done
    ]
    runner = Runner(args)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    print(
        f"models={len(models)} pending={len(tasks)} workers={args.workers} "
        f"lanes={args.lanes} configs={len(configs)} treatments={len(treatments)}",
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
                if completed % 10 == 0 or completed == len(tasks):
                    print(f"completed={completed}/{len(tasks)}", flush=True)
    finally:
        if runner.cancelled.is_set():
            runner.cancel()
    return 130 if runner.cancelled.is_set() else 0


if __name__ == "__main__":
    raise SystemExit(main())
