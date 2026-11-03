#!/usr/bin/env python3
"""Replay winner-lane SAT traces under alternative variable mappings."""

from __future__ import annotations

import argparse
import csv
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


REPLAY_FIELDS = [
    "complete", "malformed", "queries", "mismatches",
    "recorded_seconds", "replay_seconds",
    "recorded_conflicts", "replay_conflicts",
    "recorded_decisions", "replay_decisions",
    "recorded_propagations", "replay_propagations",
    "recorded_restarts", "replay_restarts",
    "observations", "observation_mismatches",
]
HEADER = [
    "model_id", "year", "tier", "category", "run", "config", "representation",
    "origin", "winner_thread", "trace_key", "trace", "solver_role", "mode",
    "replay_status", *REPLAY_FIELDS,
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-summary", required=True, type=Path)
    parser.add_argument("--trace-root", required=True, type=Path)
    parser.add_argument("--replay-binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--modes", default="recorded,numeric,reverse,first")
    parser.add_argument("--roles", default="all")
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=300.0)
    return parser.parse_args()


def solver_role(name: str) -> str:
    stem = name[:-len(".mcpdrq")] if name.endswith(".mcpdrq") else name
    marker = stem.find("-frame-")
    if marker >= 0:
        return "frame"
    for role in ("lift", "source", "checker", "inductive"):
        if stem.endswith(f"-{role}"):
            return role
    return "other"


def prepare_output(path: Path) -> set[tuple[str, str, str]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=HEADER, delimiter="\t").writeheader()
        return set()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != HEADER:
            raise SystemExit("existing query-replay output header does not match")
        return {(row["trace_key"], row["trace"], row["mode"]) for row in reader}


def replay(args: argparse.Namespace, task: dict[str, Any]) -> dict[str, str]:
    command = [
        str(args.replay_binary), "--header", "--mode", task["mode"], str(task["path"]),
    ]
    row = {
        "model_id": task["model_id"], "year": task["year"], "tier": task["tier"],
        "category": task["category"], "run": task["run"], "config": task["config"],
        "representation": task["representation"], "origin": task["origin"],
        "winner_thread": task["winner_thread"], "trace_key": task["trace_key"],
        "trace": task["path"].name, "solver_role": solver_role(task["path"].name),
        "mode": task["mode"], "replay_status": "ERROR",
    }
    try:
        completed = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace", timeout=args.timeout, check=False,
        )
        parsed = list(csv.DictReader(completed.stdout.splitlines(), delimiter="\t"))
        if parsed:
            for field in REPLAY_FIELDS:
                row[field] = parsed[-1].get(field, "")
            row["replay_status"] = "OK" if completed.returncode == 0 else "MISMATCH"
    except (OSError, subprocess.TimeoutExpired):
        row["replay_status"] = "TIMEOUT"
    return row


def main() -> int:
    args = parse_args()
    modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()]
    roles = {role.strip() for role in args.roles.split(",") if role.strip()}
    done = prepare_output(args.output)
    tasks = []
    with args.trace_summary.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            directory = args.trace_root / row["trace_key"]
            winner = row["winner_thread"] if row["winner_thread"] else "0"
            prefix = f"thread-{winner}-"
            traces = sorted(
                path for path in directory.glob("*.mcpdrq")
                if path.name.startswith(prefix) and path.stat().st_size > 0
                and ("all" in roles or solver_role(path.name) in roles)
            )
            for path in traces:
                for mode in modes:
                    if (row["trace_key"], path.name, mode) in done:
                        continue
                    tasks.append({**row, "path": path, "mode": mode})
    print(f"pending={len(tasks)} workers={args.workers} modes={len(modes)}", flush=True)
    completed_count = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(replay, args, task) for task in tasks]
        for future in as_completed(futures):
            row = future.result()
            with args.output.open("a", encoding="utf-8", newline="") as handle:
                csv.DictWriter(handle, fieldnames=HEADER, delimiter="\t").writerow(row)
            completed_count += 1
            if completed_count % 20 == 0 or completed_count == len(tasks):
                print(f"completed={completed_count}/{len(tasks)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
