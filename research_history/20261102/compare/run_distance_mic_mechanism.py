#!/usr/bin/env python3
"""Record paired legacy/winning MIC traces on promoted hard models."""

from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from compare_runner import MC_STAT_FIELDS, parse_mc_stats, parse_status


WINNING_POLICY = {
    "2015__6s45": "distance-far",
    "2017__oc8051gmd7acc": "distance-near",
    "2019__ponylink-slaveTXlen-sat": "feedback",
    "2020__vgasim_imgfifo-p088": "distance-feedback",
    "2025__rast-p16": "feedback",
}


def run_one(
    binary: Path,
    result_dir: Path,
    model: dict[str, object],
    policy: str,
    timeout: float,
    seed: int,
) -> dict[str, str]:
    model_id = str(model["id"])
    trace_dir = result_dir / "traces" / model_id / policy
    trace_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        MC_PDR_STATS="1",
        MC_PDR_SEED=str(seed),
        MC_PDR_MIC_ORDER=policy,
        MC_PDR_DECISION_TRACE_DIR=str(trace_dir),
        MC_PDR_DECISION_TRACE_MAX_EVENTS="500000",
        MC_PDR_DECISION_TRACE_LEMMAS="0",
        MC_PDR_DISTANCE_MAX_DEPTH="32",
        MC_PDR_PROGRESS_SECONDS="30",
    )
    started = time.monotonic()
    process = subprocess.Popen(
        [str(binary), "-aig", str(model["path"])],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    status = "UNKNOWN"
    output = ""
    try:
        output, _ = process.communicate(timeout=timeout)
        status = parse_status("mc", output, process.returncode)
    except subprocess.TimeoutExpired:
        process.send_signal(signal.SIGTERM)
        try:
            output, _ = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate()
        status = "TIMEOUT"
    stats = parse_mc_stats(output)
    row = {
        "model_id": model_id,
        "family": str(model.get("family", "")),
        "policy": policy,
        "status": status,
        "wall_seconds": f"{time.monotonic() - started:.6f}",
        "trace_dir": str(trace_dir),
    }
    for field in MC_STAT_FIELDS:
        row[field] = stats.get(field, "")
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--seed", type=int, default=730001)
    args = parser.parse_args()

    models = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    models = [model for model in models if model["id"] in WINNING_POLICY]
    jobs = []
    for model in models:
        jobs.append((model, "legacy"))
        jobs.append((model, WINNING_POLICY[str(model["id"])]))

    args.results.mkdir(parents=True, exist_ok=True)
    output_path = args.results / "summary.tsv"
    fields = [
        "model_id", "family", "policy", "status", "wall_seconds", "trace_dir",
        *MC_STAT_FIELDS,
    ]
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                run_one, args.binary, args.results, model, policy,
                args.timeout, args.seed,
            ): (model["id"], policy)
            for model, policy in jobs
        }
        for completed, future in enumerate(as_completed(futures), 1):
            row = future.result()
            rows.append(row)
            print(
                f"completed={completed}/{len(jobs)} model={row['model_id']} "
                f"policy={row['policy']} status={row['status']}",
                flush=True,
            )
    with output_path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: (row["model_id"], row["policy"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
