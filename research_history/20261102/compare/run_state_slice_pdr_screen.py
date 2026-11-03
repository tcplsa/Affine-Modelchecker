#!/usr/bin/env python3
"""Compare four full PDR lanes with a 3-full + 1 exact-slice portfolio.

Both processes in the mixed portfolio always run to completion.  This records
the independent full and slice outcomes as well as the earliest valid result;
it does not manufacture a win by terminating the other lane.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def load_module(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_module("compare_runner", "compare_runner.py")
SLICE = HERE / "slice_aig_property_state_cone.py"
DEFAULT_MC = ROOT / "Modelchecker-bidirectional" / "modelchecker" / "modelchecker"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--include", action="append", default=[],
                        help="substring matched against model id, name, and family")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=1200.0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--seed", type=int, default=760001)
    parser.add_argument("--mc", type=Path, default=DEFAULT_MC)
    parser.add_argument("--closure-steps", type=int, default=256)
    return parser.parse_args()


def models_from_manifest(path: Path, includes: list[str]) -> list[dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    models = document["models"] if isinstance(document, dict) else document
    if includes:
        lowered = [item.lower() for item in includes]
        models = [model for model in models if any(
            item in " ".join(str(model.get(key, "")) for key in ("id", "name", "family")).lower()
            for item in lowered)]
    if not models:
        raise ValueError("selection contains no models")
    return sorted(models, key=lambda model: model["id"])


def run(command: list[str], env: dict[str, str], timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors="replace", start_new_session=True, env=env)
    status = "TIMEOUT"
    output = ""
    try:
        output, _ = proc.communicate(timeout=timeout)
        status = RUNNER.parse_status("mc", output, proc.returncode)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            output, _ = proc.communicate(timeout=2.0)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            output, _ = proc.communicate()
    result: dict[str, Any] = {
        "status": status,
        "wall_seconds": time.monotonic() - started,
        "exit_code": proc.returncode if proc.returncode is not None else "",
    }
    result.update(RUNNER.parse_mc_stats(output))
    return result


def slice_model(model: dict[str, Any], output_dir: Path, closure_steps: int) -> tuple[Path, dict[str, str]]:
    sliced = output_dir / "slices" / f"{model['id']}.aag"
    command = [sys.executable, str(SLICE), model["path"], str(sliced),
               "--closure-steps", str(closure_steps)]
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, errors="replace")
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    fields = sliced.open(encoding="ascii").readline().split()
    return sliced, {
        "slice_inputs": fields[2], "slice_latches": fields[3],
        "slice_ands": fields[5], "slice_bads": fields[6],
        "slice_constraints": fields[7] if len(fields) > 7 else "0",
    }


STAT_FIELDS = (
    "pdr_runtime", "pdr_depth", "queries", "cti", "mic", "push",
    "lemma_added", "lemma_literals", "frame_core_literals",
    "frame_sat_conflicts", "frame_sat_decisions", "frame_sat_propagations",
    "translation_raw_vars", "translation_raw_clauses",
    "translation_simplified_vars", "translation_simplified_clauses",
    "translation_simplified_literals", "translation_build", "translation_simplify",
)


def decorate(prefix: str, result: dict[str, Any]) -> dict[str, str]:
    values = {
        f"{prefix}_status": str(result.get("status", "")),
        f"{prefix}_wall_seconds": f"{float(result.get('wall_seconds', 0.0)):.6f}",
        f"{prefix}_exit_code": str(result.get("exit_code", "")),
    }
    for field in STAT_FIELDS:
        values[f"{prefix}_{field}"] = str(result.get(field, ""))
    return values


def execute_model(model: dict[str, Any], args: argparse.Namespace) -> dict[str, str]:
    sliced, slice_info = slice_model(model, args.output_dir, args.closure_steps)
    env = os.environ.copy()
    env["MC_PDR_SEED"] = str(args.seed)
    env["MC_PDR_STATS"] = "1"
    # Timeout runs need a terminal-like snapshot; otherwise the experiment can
    # tell us only that both variants timed out, not whether slicing changed
    # the PDR trajectory.
    env["MC_PDR_PROGRESS_SECONDS"] = "30"
    full4 = run([str(args.mc), "--forward-aig", "4", model["path"]], env, args.timeout)

    # Separate processes are necessary because their circuit instances differ.
    # They are deliberately awaited together rather than cancelling the loser.
    with ThreadPoolExecutor(max_workers=2) as pool:
        full3_future = pool.submit(
            run, [str(args.mc), "--forward-aig", "3", model["path"]], env, args.timeout)
        slice_future = pool.submit(
            run, [str(args.mc), "--forward-aig", "1", str(sliced)], env, args.timeout)
        full3 = full3_future.result()
        sliced_result = slice_future.result()
    valid = [result for result in (full3, sliced_result)
             if result["status"] in {"SAFE", "UNSAFE"}]
    statuses = {result["status"] for result in valid}
    mixed_status = ("CONFLICT" if len(statuses) > 1 else
                    next(iter(statuses)) if statuses else "TIMEOUT")
    mixed_first = min((float(result["wall_seconds"]) for result in valid), default=args.timeout)
    row: dict[str, str] = {
        "model_id": model["id"], "name": model["name"], "year": str(model["year"]),
        "family": model["family"], "timeout_seconds": str(args.timeout),
        "seed": str(args.seed), **slice_info,
        "mixed_status": mixed_status, "mixed_first_valid_seconds": f"{mixed_first:.6f}",
    }
    row.update(decorate("full4", full4))
    row.update(decorate("full3", full3))
    row.update(decorate("slice1", sliced_result))
    return row


def main() -> int:
    args = parse_args()
    if args.workers < 1:
        raise ValueError("--workers must be positive")
    models = models_from_manifest(args.manifest, args.include)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "state_slice_pdr.tsv"
    rows: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(execute_model, model, args): model for model in models}
        for index, future in enumerate(as_completed(futures), 1):
            model = futures[future]
            try:
                row = future.result()
            except Exception as error:
                row = {"model_id": model["id"], "name": model["name"],
                       "year": str(model["year"]), "family": model["family"],
                       "mixed_status": "ERROR", "error": str(error)}
            rows.append(row)
            print(f"[{index}/{len(models)}] {row['model_id']} {row['mixed_status']}", flush=True)
            fields = sorted({key for saved in rows for key in saved})
            with output.open("w", encoding="utf-8", newline="") as target:
                writer = csv.DictWriter(target, fieldnames=fields, delimiter="\t", extrasaction="ignore")
                writer.writeheader()
                writer.writerows(sorted(rows, key=lambda saved: saved["model_id"]))
    print(f"wrote {len(rows)} rows to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
