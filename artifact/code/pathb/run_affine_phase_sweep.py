#!/usr/bin/env python3
"""Run equal-four-core phase-boundary screens on Path B benchmarks."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path


CONFIGS = ("ric3", "mc-aig", "mc-xag", "cmsat", "cmsat-gauss", "minisat")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=730001)
    parser.add_argument("--config", action="append", choices=CONFIGS)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--ric3",
        type=Path,
        default=Path("/home/wudl/rIC3-stock-7149d56/target/release/ric3"),
    )
    parser.add_argument(
        "--mc",
        type=Path,
        default=Path(
            "/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker"
        ),
    )
    parser.add_argument(
        "--blif-main", type=Path, default=Path("/home/wudl/blif/mainblif.py")
    )
    return parser.parse_args()


def terminate_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=1)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def verdict(config: str, text: str) -> str:
    if config == "ric3":
        lines = {line.strip() for line in text.splitlines()}
        if "UNSAT" in lines:
            return "safe"
        if "SAT" in lines:
            return "unsafe"
    elif config.startswith("mc-"):
        matches = re.findall(r"^result:\s*(\w+)", text, flags=re.MULTILINE)
        if matches:
            return matches[-1].lower()
    else:
        if "The design is SAFE" in text:
            return "safe"
        if "The design is UNSAFE" in text:
            return "unsafe"
    return "timeout"


def metrics(config: str, text: str) -> dict[str, object]:
    result: dict[str, object] = {}
    patterns = {
        "depth": r"\bdepth=(-?\d+)",
        "conflicts": r"(?:frame_sat|cmsat)_conflicts=(\d+)",
        "decisions": r"(?:frame_sat|cmsat)_decisions=(\d+)",
        "propagations": r"(?:frame_sat|cmsat)_propagations=(\d+)",
        "recognized_xors": r"recognized_xors=(\d+)",
        "first_pre_seconds": r"first_pre_solve=([0-9.]+)",
    }
    for name, pattern in patterns.items():
        found = re.findall(pattern, text)
        if found:
            convert = float if name == "first_pre_seconds" else int
            values = [convert(value) for value in found]
            result[name] = max(values)
    elapsed = re.findall(r"Elapsed time:\s*([0-9.]+)", text)
    if elapsed:
        result["solver_elapsed"] = float(elapsed[-1])
    return result


def run_single(
    command: list[str], log: Path, timeout: float, env: dict[str, str]
) -> tuple[int, float, str]:
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(
            command,
            stdout=stream,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            start_new_session=True,
        )
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            terminate_group(process)
            returncode = 124
    elapsed = time.monotonic() - started
    return returncode, elapsed, log.read_text(encoding="utf-8", errors="replace")


def run_ric3(
    args: argparse.Namespace, aag: Path, directory: Path
) -> tuple[int, float, str, int]:
    env = os.environ.copy()
    processes: list[tuple[int, subprocess.Popen[str], object, Path]] = []
    started = time.monotonic()
    seeds = [args.seed + 2 * index for index in range(4)]
    for replica, seed in enumerate(seeds):
        log = directory / f"replica-{replica}.log"
        stream = log.open("w", encoding="utf-8")
        command = [
            str(args.ric3),
            "check",
            "--ui",
            "false",
            str(aag),
            "ic3",
            "--rseed",
            str(seed),
        ]
        process = subprocess.Popen(
            command,
            stdout=stream,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            start_new_session=True,
        )
        processes.append((replica, process, stream, log))

    winner = -1
    winner_text = ""
    reached_deadline = False
    while time.monotonic() - started < args.timeout:
        for replica, process, stream, log in processes:
            if process.poll() is None:
                continue
            stream.flush()
            text = log.read_text(encoding="utf-8", errors="replace")
            if verdict("ric3", text) in {"safe", "unsafe"}:
                winner = replica
                winner_text = text
                break
        if winner >= 0:
            break
        if all(process.poll() is not None for _, process, _, _ in processes):
            break
        time.sleep(0.02)
    else:
        reached_deadline = True

    returncodes = []
    for _, process, stream, _ in processes:
        terminate_group(process)
        returncodes.append(process.returncode)
        stream.close()
    elapsed = time.monotonic() - started
    if winner < 0:
        if reached_deadline:
            return 124, elapsed, "", winner
        failed = next((code for code in returncodes if code not in (0, None)), 1)
        return failed, elapsed, "", winner
    return 0, elapsed, winner_text, winner


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    selected = args.config or list(CONFIGS)
    args.output.mkdir(parents=True, exist_ok=True)
    result_path = args.output / "report.json"
    prior: dict[tuple[str, str], dict[str, object]] = {}
    if args.resume and result_path.exists():
        old = json.loads(result_path.read_text(encoding="utf-8"))
        prior = {(row["stem"], row["config"]): row for row in old["results"]}

    jobs = [
        (entry, config)
        for entry in manifest
        for config in selected
        if (entry["stem"], config) not in prior
    ]

    def run(job: tuple[dict[str, object], str]) -> dict[str, object]:
        entry, config = job
        stem = str(entry["stem"])
        directory = args.output / "logs" / stem / config
        directory.mkdir(parents=True, exist_ok=True)
        aag = Path(str(entry["paths"]["aag"])).resolve()
        blif = Path(str(entry["paths"]["blif"])).resolve()
        env = os.environ.copy()
        env.update({"MC_PDR_SEED": str(args.seed), "MC_PDR_STATS": "1"})
        winner = -1
        if config == "ric3":
            returncode, elapsed, text, winner = run_ric3(args, aag, directory)
        else:
            if config == "mc-aig":
                command = [str(args.mc), "--forward-aig", "4", str(aag)]
            elif config == "mc-xag":
                command = [str(args.mc), "--forward-xag", "4", str(aag)]
            else:
                backend = "cmsat" if config == "cmsat-gauss" else config
                command = [
                    "python3",
                    str(args.blif_main),
                    "--solver",
                    backend,
                    "--parallel",
                    "4",
                    "--seed",
                    str(args.seed),
                    str(blif),
                ]
                env["BLIF_SOLVER_BACKEND"] = backend
                env["CMSAT_SEED"] = str(args.seed)
                if config == "cmsat-gauss":
                    env["CMSAT_GAUSS"] = "1"
                env["LD_LIBRARY_PATH"] = (
                    "/home/wudl/blif/cryptominisat/build/lib:"
                    + env.get("LD_LIBRARY_PATH", "")
                )
            returncode, elapsed, text = run_single(
                command, directory / "run.log", args.timeout, env
            )
        status = verdict(config, text)
        if status == "timeout" and returncode != 124:
            status = "error"
        row = {
            "stem": stem,
            "family": entry["family"],
            "params": entry["params"],
            "stats": entry["stats"],
            "config": config,
            "result": status,
            "wall_seconds": elapsed,
            "returncode": returncode,
            "winner_replica": winner,
            **metrics(config, text),
        }
        return row

    rows = list(prior.values())
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        for row in executor.map(run, jobs):
            rows.append(row)
            print(
                f"config={row['config']} stem={row['stem']} "
                f"result={row['result']} wall={row['wall_seconds']:.3f}",
                flush=True,
            )
    rows.sort(key=lambda row: (str(row["stem"]), str(row["config"])))
    report = {
        "schema": "pathb-affine-phase-sweep-v1",
        "manifest": str(args.manifest),
        "timeout": args.timeout,
        "four_core_budget": True,
        "results": rows,
    }
    result_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote={result_path} rows={len(rows)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
