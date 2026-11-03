#!/usr/bin/env python3
"""Run resumable single-XOR causal interventions with live phase capture."""

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
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from compare_runner import MC_STAT_FIELDS, ProcessRegistry, parse_mc_stats, parse_status


PHASES = (
    "translation_build", "translation_simplify", "translation_inject",
    "bmc0_solve", "first_pre_solve", "lift_build", "lift_simplify",
    "lift_inject", "first_lift_solve",
)
BASE_HEADER = [
    "model_id", "name", "year", "shard", "run", "variant", "kind", "xor_var",
    "selected_xors", "total_xors", "affected_xors", "status", "wall_seconds",
    "timeout_seconds", "exit_code", "winner_thread", "timeout_phase",
]
PHASE_HEADER = [f"phase_{phase}" for phase in PHASES]
CNF_HEADER = [
    "translation_raw_vars", "translation_raw_clauses", "translation_simplified_vars",
    "translation_simplified_clauses", "translation_simplified_literals",
    "lift_raw_vars", "lift_raw_clauses", "lift_simplified_vars",
    "lift_simplified_clauses", "lift_simplified_literals",
]
HEADER = BASE_HEADER + PHASE_HEADER + CNF_HEADER + list(MC_STAT_FIELDS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--shard", required=True, choices=["server-a", "server-b", "all"])
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--runs", default="1,2,3,4")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--lanes", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--ctg-depth", type=int, default=1)
    return parser.parse_args()


def kv(line: str) -> dict[str, str]:
    return dict(re.findall(r"([A-Za-z_]+)=([^ ]+)", line))


def parse_phase_output(output: str) -> dict[str, str]:
    winner = ""
    phase_rows: list[dict[str, str]] = []
    cnf_by_thread: dict[str, dict[str, str]] = {}
    for line in output.splitlines():
        if line.startswith("c PDR_STATS "):
            values = kv(line)
            if values.get("result") in {"safe", "unsafe"} and not winner:
                winner = values.get("thread", "")
        elif line.startswith("c PDR_PHASE "):
            phase_rows.append(kv(line))
        elif line.startswith("c PDR_PHASE_CNF "):
            values = kv(line)
            cnf_by_thread[values.get("thread", "")] = values

    by_thread: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in phase_rows:
        by_thread[row.get("thread", "")].append(row)
    chosen = by_thread.get(winner, [])
    if not chosen and by_thread:
        chosen = max(by_thread.values(), key=len)
    result: dict[str, str] = {"winner_thread": winner}
    phase_values: dict[str, float] = {}
    open_phase: dict[str, str] = {}
    for row in chosen:
        phase = row.get("phase", "")
        event = row.get("event", "")
        if event == "start":
            open_phase[phase] = phase
        elif event == "done":
            open_phase.pop(phase, None)
            value = row.get("total", row.get("elapsed", ""))
            try:
                phase_values[phase] = max(phase_values.get(phase, 0.0), float(value))
            except ValueError:
                pass
    for phase in PHASES:
        result[f"phase_{phase}"] = (
            f"{phase_values[phase]:.6f}" if phase in phase_values else ""
        )
    if open_phase:
        result["timeout_phase"] = sorted(open_phase)[-1]
    elif chosen:
        result["timeout_phase"] = "after_" + chosen[-1].get("phase", "unknown")
    else:
        result["timeout_phase"] = "no_phase_output"
    cnf = dict(cnf_by_thread.get(winner, {}))
    # Timed-out lanes do not print final stats; recover CNF sizes from live phase events.
    for row in chosen:
        if row.get("event") != "done":
            continue
        if row.get("phase") == "translation_build":
            cnf.setdefault("translation_raw_vars", row.get("vars", ""))
            cnf.setdefault("translation_raw_clauses", row.get("clauses", ""))
        elif row.get("phase") == "translation_simplify":
            cnf.setdefault("translation_simplified_vars", row.get("vars", ""))
            cnf.setdefault("translation_simplified_clauses", row.get("clauses", ""))
            cnf.setdefault("translation_simplified_literals", row.get("literals", ""))
        elif row.get("phase") == "lift_build":
            cnf.setdefault("lift_raw_vars", row.get("vars", ""))
            cnf.setdefault("lift_raw_clauses", row.get("clauses", ""))
        elif row.get("phase") == "lift_simplify":
            cnf.setdefault("lift_simplified_vars", row.get("vars", ""))
            cnf.setdefault("lift_simplified_clauses", row.get("clauses", ""))
            cnf.setdefault("lift_simplified_literals", row.get("literals", ""))
    for field in CNF_HEADER:
        result[field] = cnf.get(field, "")
    return result


def prepare_output(path: Path) -> set[tuple[str, str, str]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=HEADER, delimiter="\t").writeheader()
        return set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != HEADER:
            raise SystemExit("existing causal output header does not match")
        return {(row["model_id"], row["run"], row["variant"]) for row in reader}


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
        variant = task["variant"]
        command = [str(self.args.binary), "--forward-xag", str(self.args.lanes), model["path"]]
        env = os.environ.copy()
        env.update({
            "MC_PDR_STATS": "1",
            "MC_PDR_PHASE_STATS": "1",
            "MC_PDR_CTG_DEPTH": str(self.args.ctg_depth),
            "MC_PDR_INPUT_ORDER": "original",
            "MC_PDR_XAG_POLICY": "all",
            "MC_PDR_XAG_FRACTION": "1.0",
            "MC_PDR_XAG_ALLOWLIST_FILE": variant["allowlist"],
            "MC_PDR_PERTURB": "",
        })
        env.pop("MC_PDR_SEED", None)
        started = time.monotonic()
        output = ""
        status = "ERROR"
        exit_code: Any = ""
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
            # communicate() after termination recovers live phase lines from timed-out tasks.
            if not output and proc.stdout is not None:
                try:
                    output, _ = proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            exit_code = proc.returncode if proc.returncode is not None else ""
        except OSError:
            status = "ERROR"
        finally:
            if proc is not None:
                self.registry.discard(proc)

        row = {
            "model_id": model["id"], "name": model["name"], "year": str(model["year"]),
            "shard": model["shard"], "run": str(task["run"]), "variant": variant["id"],
            "kind": variant["kind"], "xor_var": str(variant["xor_var"]),
            "selected_xors": str(variant["selected_xors"]), "total_xors": str(model["total_xors"]),
            "affected_xors": str(model["affected_xors"]), "status": status,
            "wall_seconds": f"{time.monotonic() - started:.6f}",
            "timeout_seconds": f"{self.args.timeout:.6f}", "exit_code": str(exit_code),
        }
        phase = parse_phase_output(output)
        for field in ("winner_thread", "timeout_phase", *PHASE_HEADER, *CNF_HEADER):
            row[field] = phase.get(field, "")
        stats = parse_mc_stats(output)
        for field in MC_STAT_FIELDS:
            row[field] = str(stats.get(field, ""))
        return row


def main() -> int:
    args = parse_args()
    runs = [int(value) for value in args.runs.split(",") if value.strip()]
    design = json.loads(args.manifest.read_text(encoding="utf-8"))
    models = [m for m in design["models"] if args.shard == "all" or m["shard"] == args.shard]
    done = prepare_output(args.output)
    # Interleave variants across repeats so resumed runs do not launch four copies of one variant first.
    tasks = [
        {"model": model, "variant": variant, "run": run}
        for run in runs for model in models for variant in model["variants"]
        if (model["id"], str(run), variant["id"]) not in done
    ]
    runner = Runner(args)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    print(f"shard={args.shard} models={len(models)} pending={len(tasks)} workers={args.workers} lanes={args.lanes}", flush=True)
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
