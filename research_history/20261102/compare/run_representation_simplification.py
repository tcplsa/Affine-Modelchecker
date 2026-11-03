#!/usr/bin/env python3
"""Compare AIG/XAG/lowered-XAG across MiniSat preprocessing regimes."""

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
from run_xor_canonical_mechanism import CNF_FIELDS, PHASES, QUERY_FIELDS, parse_instrumentation


REPRESENTATIONS = {
    "aig": "--forward-aig",
    "xag": "--forward-xag",
    "lowered": "--forward-xag-lowered",
}
REGIMES = {
    "native": {"eliminate": 1, "canonical_minisat": 0, "canonical_cnf": 0},
    "raw": {"eliminate": 0, "canonical_minisat": 0, "canonical_cnf": 1},
    "precanonical": {"eliminate": 1, "canonical_minisat": 1, "canonical_cnf": 1},
    "canonical-minisat": {"eliminate": 1, "canonical_minisat": 1, "canonical_cnf": 0},
    "canonical-cnf": {"eliminate": 1, "canonical_minisat": 0, "canonical_cnf": 1},
}
DEFAULT_REGIMES = ("native", "raw", "precanonical")
DEFAULT_CONFIGS = [
    f"{representation}_{regime}"
    for regime in DEFAULT_REGIMES for representation in REPRESENTATIONS
]
FEATURE_FIELDS = (
    "feature_aig_ands", "feature_recognized_xors", "feature_and_reduction",
    "feature_next_cone_xors", "feature_bad_cone_xors",
    "feature_shared_cone_xors", "feature_next_xor_density",
    "feature_bad_xor_density",
)
HEADER = [
    "model_id", "name", "year", "tier", "shard", "run", "config",
    "representation", "regime", "minisat_eliminate", "canonical_minisat",
    "canonical_cnf", *FEATURE_FIELDS, "status", "wall_seconds", "timeout_seconds",
    "exit_code", "winner_thread", "timeout_phase",
] + [f"phase_{phase}" for phase in PHASES] + list(CNF_FIELDS) + list(QUERY_FIELDS) + list(MC_STAT_FIELDS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--shard", choices=("all", "server-a", "server-b"), default="all")
    parser.add_argument("--configs", default=",".join(DEFAULT_CONFIGS))
    parser.add_argument("--runs", default="1,2")
    parser.add_argument("--workers", type=int, default=28)
    parser.add_argument("--lanes", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--ctg-depth", type=int, default=1)
    parser.add_argument("--limit-models", type=int, default=0)
    parser.add_argument(
        "--input-order",
        choices=(
            "original", "fanout-desc", "fanout-asc", "bad-first", "bad-last",
            "next-first", "next-last", "shared-first", "shared-last",
        ),
        default="original",
    )
    return parser.parse_args()


def decode_config(name: str) -> tuple[str, str, dict[str, int]]:
    for representation in REPRESENTATIONS:
        prefix = representation + "_"
        if name.startswith(prefix):
            regime = name[len(prefix):]
            if regime in REGIMES:
                return representation, regime, REGIMES[regime]
    raise SystemExit(f"invalid config: {name}")


def prepare_output(path: Path) -> set[tuple[str, str, str]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=HEADER, delimiter="\t").writeheader()
        return set()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != HEADER:
            raise SystemExit("existing representation output header does not match")
        return {(row["model_id"], row["run"], row["config"]) for row in reader}


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
        representation, regime, controls = decode_config(task["config"])
        command = [
            str(self.args.binary), REPRESENTATIONS[representation], str(self.args.lanes),
            str(model["path"]),
        ]
        env = os.environ.copy()
        env.update({
            "MC_PDR_STATS": "1", "MC_PDR_PHASE_STATS": "1",
            "MC_PDR_CTG_DEPTH": str(self.args.ctg_depth),
            "MC_PDR_INPUT_ORDER": self.args.input_order,
            "MC_PDR_INPUT_ORDER_SEED": "1", "MC_PDR_PERTURB": "",
            "MC_PDR_XAG_POLICY": "all", "MC_PDR_XAG_FRACTION": "1.0",
            "MC_PDR_XAG_STABLE_SLOTS": "0",
            "MC_PDR_MINISAT_ELIMINATE": str(controls["eliminate"]),
            "MC_PDR_CANONICAL_MINISAT": str(controls["canonical_minisat"]),
            "MC_PDR_CANONICAL_CNF": str(controls["canonical_cnf"]),
        })
        for key in ("MC_PDR_XAG_ALLOWLIST_FILE", "MC_PDR_SEED", "MC_PDR_PERTURB_SEED"):
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
            "shard": str(model["shard"]), "run": str(task["run"]),
            "config": str(task["config"]), "representation": representation,
            "regime": regime, "minisat_eliminate": str(controls["eliminate"]),
            "canonical_minisat": str(controls["canonical_minisat"]),
            "canonical_cnf": str(controls["canonical_cnf"]),
            "status": status, "wall_seconds": f"{time.monotonic() - started:.6f}",
            "timeout_seconds": f"{self.args.timeout:.6f}", "exit_code": exit_code,
        }
        for field in FEATURE_FIELDS:
            row[field] = str(model[field[len("feature_"):]])
        instrument = parse_instrumentation(output)
        for field in ("winner_thread", "timeout_phase", *[f"phase_{p}" for p in PHASES], *CNF_FIELDS, *QUERY_FIELDS):
            row[field] = instrument.get(field, "")
        stats = parse_mc_stats(output)
        for field in MC_STAT_FIELDS:
            row[field] = str(stats.get(field, ""))
        return row


def main() -> int:
    args = parse_args()
    configs = [value.strip() for value in args.configs.split(",") if value.strip()]
    for config in configs:
        decode_config(config)
    runs = [int(value) for value in args.runs.split(",") if value.strip()]
    design = json.loads(args.manifest.read_text(encoding="utf-8"))
    models = [
        model for model in design["models"]
        if args.shard == "all" or model["shard"] == args.shard
    ]
    if args.limit_models > 0:
        models = models[:args.limit_models]
    done = prepare_output(args.output)
    tasks = [
        {"model": model, "run": run, "config": config}
        for run in runs for model in models for config in configs
        if (str(model["id"]), str(run), config) not in done
    ]
    runner = Runner(args)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    print(
        f"models={len(models)} pending={len(tasks)} workers={args.workers} "
        f"lanes={args.lanes} shard={args.shard} input_order={args.input_order}",
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
