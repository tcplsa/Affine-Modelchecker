#!/usr/bin/env python3
"""Run matched XOR numbering modes and capture first-query SAT statistics."""

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


MODES = {
    "compact": (0, 0, 1, 0),
    "stable": (1, 0, 1, 0),
    "canonical_compact": (0, 1, 1, 0),
    "canonical_stable": (1, 1, 1, 0),
    "raw_canonical_compact": (0, 1, 0, 0),
    "raw_canonical_stable": (1, 1, 0, 0),
    "precanonical_compact": (0, 1, 1, 1),
    "precanonical_stable": (1, 1, 1, 1),
}
PHASES = (
    "translation_build", "translation_simplify", "translation_inject",
    "bmc0_solve", "first_pre_solve", "lift_build", "lift_simplify",
    "lift_inject", "first_lift_solve",
)
CNF_FIELDS = (
    "translation_raw_vars", "translation_raw_clauses",
    "translation_simplified_vars", "translation_simplified_clauses",
    "translation_simplified_literals",
)
QUERY_FIELDS = (
    "query_result", "query_elapsed", "query_conflicts", "query_decisions",
    "query_propagations", "query_restarts",
)
HEADER = [
    "model_id", "name", "year", "run", "variant", "kind", "xor_var",
    "selection_role", "mode", "stable_slots", "canonical_cnf",
    "canonical_minisat", "status",
    "wall_seconds", "timeout_seconds", "exit_code", "winner_thread",
    "timeout_phase",
] + [f"phase_{phase}" for phase in PHASES] + list(CNF_FIELDS) + list(QUERY_FIELDS) + list(MC_STAT_FIELDS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--modes", default=",".join(MODES))
    parser.add_argument("--runs", default="1,2,3,4")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--lanes", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--ctg-depth", type=int, default=1)
    return parser.parse_args()


def key_values(line: str) -> dict[str, str]:
    return dict(re.findall(r"([A-Za-z_]+)=([^ ]+)", line))


def parse_instrumentation(output: str) -> dict[str, str]:
    winner = ""
    phase_by_thread: dict[str, list[dict[str, str]]] = {}
    query_by_thread: dict[str, dict[str, str]] = {}
    cnf_by_thread: dict[str, dict[str, str]] = {}
    for line in output.splitlines():
        if line.startswith("c PDR_STATS "):
            values = key_values(line)
            if values.get("result") in {"safe", "unsafe"} and not winner:
                winner = values.get("thread", "")
        elif line.startswith("c PDR_PHASE "):
            values = key_values(line)
            phase_by_thread.setdefault(values.get("thread", ""), []).append(values)
        elif line.startswith("c PDR_SOLVER_QUERY "):
            values = key_values(line)
            if values.get("phase") == "first_pre_solve":
                query_by_thread[values.get("thread", "")] = values
        elif line.startswith("c PDR_PHASE_CNF "):
            values = key_values(line)
            cnf_by_thread[values.get("thread", "")] = values

    if not winner:
        candidates = set(phase_by_thread) | set(query_by_thread) | set(cnf_by_thread)
        winner = sorted(candidates)[0] if candidates else ""
    phases = phase_by_thread.get(winner, [])
    result: dict[str, str] = {"winner_thread": winner}
    values_by_phase: dict[str, float] = {}
    open_phases: set[str] = set()
    for values in phases:
        phase = values.get("phase", "")
        if values.get("event") == "start":
            open_phases.add(phase)
        elif values.get("event") == "done":
            open_phases.discard(phase)
            raw = values.get("total", values.get("elapsed", ""))
            try:
                values_by_phase[phase] = max(values_by_phase.get(phase, 0.0), float(raw))
            except ValueError:
                pass
    for phase in PHASES:
        result[f"phase_{phase}"] = f"{values_by_phase[phase]:.6f}" if phase in values_by_phase else ""
    if open_phases:
        result["timeout_phase"] = sorted(open_phases)[-1]
    elif phases:
        result["timeout_phase"] = "after_" + phases[-1].get("phase", "unknown")
    else:
        result["timeout_phase"] = "no_phase_output"

    cnf = dict(cnf_by_thread.get(winner, {}))
    for values in phases:
        if values.get("event") != "done":
            continue
        phase = values.get("phase")
        if phase == "translation_build":
            cnf.setdefault("translation_raw_vars", values.get("vars", ""))
            cnf.setdefault("translation_raw_clauses", values.get("clauses", ""))
        elif phase == "translation_simplify":
            cnf.setdefault("translation_simplified_vars", values.get("vars", ""))
            cnf.setdefault("translation_simplified_clauses", values.get("clauses", ""))
            cnf.setdefault("translation_simplified_literals", values.get("literals", ""))
    for field in CNF_FIELDS:
        result[field] = cnf.get(field, "")

    query = query_by_thread.get(winner, {})
    result.update({
        "query_result": query.get("result", ""),
        "query_elapsed": query.get("elapsed", ""),
        "query_conflicts": query.get("conflicts", ""),
        "query_decisions": query.get("decisions", ""),
        "query_propagations": query.get("propagations", ""),
        "query_restarts": query.get("restarts", ""),
    })
    return result


def prepare_output(path: Path) -> set[tuple[str, str, str, str]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=HEADER, delimiter="\t").writeheader()
        return set()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != HEADER:
            raise SystemExit("existing canonical-mechanism output header does not match")
        return {(row["model_id"], row["run"], row["variant"], row["mode"]) for row in reader}


class Runner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.registry = ProcessRegistry()
        self.cancelled = threading.Event()

    def cancel(self) -> None:
        self.cancelled.set()
        self.registry.terminate_all()

    def run(self, task: dict[str, Any]) -> dict[str, str]:
        model, variant, mode = task["model"], task["variant"], task["mode"]
        stable, canonical, eliminate, canonical_minisat = MODES[mode]
        command = [str(self.args.binary), "--forward-xag", str(self.args.lanes), model["path"]]
        env = os.environ.copy()
        env.update({
            "MC_PDR_STATS": "1", "MC_PDR_PHASE_STATS": "1",
            "MC_PDR_CTG_DEPTH": str(self.args.ctg_depth),
            "MC_PDR_INPUT_ORDER": "original", "MC_PDR_XAG_POLICY": "all",
            "MC_PDR_XAG_FRACTION": "1.0",
            "MC_PDR_XAG_ALLOWLIST_FILE": variant["allowlist"],
            "MC_PDR_XAG_STABLE_SLOTS": str(stable),
            "MC_PDR_CANONICAL_CNF": str(canonical), "MC_PDR_PERTURB": "",
            "MC_PDR_MINISAT_ELIMINATE": str(eliminate),
            "MC_PDR_CANONICAL_MINISAT": str(canonical_minisat),
        })
        env.pop("MC_PDR_SEED", None)
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
                try:
                    output, _ = proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            exit_code = str(proc.returncode if proc.returncode is not None else "")
        except OSError:
            status = "ERROR"
        finally:
            if proc is not None:
                self.registry.discard(proc)

        row = {
            "model_id": model["id"], "name": model["name"], "year": str(model["year"]),
            "run": str(task["run"]), "variant": variant["id"], "kind": variant["kind"],
            "xor_var": str(variant["xor_var"]),
            "selection_role": str(variant.get("selection_role", "")), "mode": mode,
            "stable_slots": str(stable), "canonical_cnf": str(canonical), "status": status,
            "canonical_minisat": str(canonical_minisat),
            "wall_seconds": f"{time.monotonic() - started:.6f}",
            "timeout_seconds": f"{self.args.timeout:.6f}", "exit_code": exit_code,
        }
        instrument = parse_instrumentation(output)
        for field in ("winner_thread", "timeout_phase", *[f"phase_{p}" for p in PHASES], *CNF_FIELDS, *QUERY_FIELDS):
            row[field] = instrument.get(field, "")
        stats = parse_mc_stats(output)
        for field in MC_STAT_FIELDS:
            row[field] = str(stats.get(field, ""))
        return row


def main() -> int:
    args = parse_args()
    modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()]
    invalid = set(modes) - set(MODES)
    if invalid:
        raise SystemExit(f"invalid modes: {sorted(invalid)}")
    runs = [int(value) for value in args.runs.split(",") if value.strip()]
    design = json.loads(args.manifest.read_text(encoding="utf-8"))
    done = prepare_output(args.output)
    tasks = [
        {"model": model, "variant": variant, "run": run, "mode": mode}
        for run in runs for model in design["models"] for variant in model["variants"] for mode in modes
        if (model["id"], str(run), variant["id"], mode) not in done
    ]
    runner = Runner(args)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    print(f"models={len(design['models'])} pending={len(tasks)} workers={args.workers} lanes={args.lanes} modes={','.join(modes)}", flush=True)
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
