#!/usr/bin/env python3
"""Run rIC3 over the HWMCC 2015 AIG set and record per-instance timing."""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from compare_runner import model_name as benchmark_name


SCRIPT_DIR = Path(__file__).resolve().parent
TOOLS_DIR = SCRIPT_DIR.parent
RESULTS_DIR = SCRIPT_DIR / "results"

HEADER = [
    "name",
    "aig_path",
    "size_bytes",
    "engine",
    "status",
    "exit_code",
    "wall_seconds",
    "timed_out",
    "log_path",
    "command",
]

TSV_LOCK = threading.Lock()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ric3 check on all HWMCC AIG benchmarks and time each run."
    )
    parser.add_argument(
        "--year",
        type=str,
        default=os.environ.get("HWMCC_YEAR", "2017"),
        choices=["2015", "2017", "2019", "2020", "2024", "2025"],
        help="HWMCC year; default from env HWMCC_YEAR or 2017",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="directory containing HWMCC .aig files; auto-derived from --year if not set",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="TSV result path; auto-derived from --year if not set",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=None,
        help="directory for per-benchmark ric3 logs; auto-derived from --year if not set",
    )
    parser.add_argument(
        "--ric3",
        default=shutil.which("ric3") or "ric3",
        help="ric3 executable",
    )
    parser.add_argument(
        "--engine",
        default=os.environ.get("RIC3_ENGINE", "ic3"),
        choices=[
            "ic3",
            "kind",
            "bmc",
            "portfolio",
            "multi-prop",
            "polynexus",
            "rlive",
        ],
        help="ric3 check engine; default is ic3. Use --engine portfolio for rIC3 portfolio mode.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("RIC3_TIMEOUT", "300")),
        help="per-benchmark timeout in seconds",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=int(os.environ.get("RIC3_WORKERS", "1")),
        help="number of concurrent ric3 processes",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="run only the first N selected benchmarks; 0 means all",
    )
    parser.add_argument(
        "--sort",
        choices=["name", "size"],
        default="name",
        help="benchmark order",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="skip benchmark names already present in --output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print selected benchmark count without running ric3",
    )
    return parser.parse_args()


def resolve_dirs(args: argparse.Namespace) -> None:
    """Fill in defaults for data-dir, output, log-dir based on --year."""
    if args.data_dir is None:
        args.data_dir = TOOLS_DIR / f"hwmcc{args.year}" / "data"
    if args.output is None:
        args.output = RESULTS_DIR / f"ric3_hwmcc{args.year}.tsv"
    if args.log_dir is None:
        args.log_dir = RESULTS_DIR / f"ric3_hwmcc{args.year}_logs"


def discover(data_dir: Path, sort_by: str, limit: int) -> list[Path]:
    paths = list(data_dir.rglob("*.aig")) + list(data_dir.rglob("*.aag"))
    if sort_by == "size":
        paths.sort(key=lambda p: (p.stat().st_size, p.name))
    else:
        paths.sort(key=lambda p: p.name)
    if limit > 0:
        paths = paths[:limit]
    return paths


def read_done_names(output: Path) -> set[str]:
    if not output.exists():
        return set()
    with output.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return {row["name"] for row in reader if row.get("name")}


def ensure_output(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists() or output.stat().st_size == 0:
        with output.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f, delimiter="\t").writerow(HEADER)


def parse_status(text: str, exit_code: int, timed_out: bool) -> str:
    if timed_out:
        return "TIMEOUT"
    lower = text.lower()
    if "panicked at" in lower or "thread 'main'" in lower:
        return "PANIC"
    if "unsat" in lower or "safe" in lower:
        return "SAFE"
    if "sat" in lower or "unsafe" in lower:
        return "UNSAFE"
    if exit_code == 0:
        return "UNKNOWN"
    return "ERROR"


def run_one(args: argparse.Namespace, aig_path: Path) -> dict[str, str]:
    name = benchmark_name(
        aig_path, {"year": args.year, "data_dir": str(args.data_dir)}
    )
    log_path = args.log_dir / f"{name}.log"
    command = [args.ric3, "check", "--ui", "false", str(aig_path), args.engine]

    start = time.monotonic()
    timed_out = False
    exit_code = -1
    output = ""

    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    try:
        output, _ = proc.communicate(timeout=args.timeout)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            output, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            output, _ = proc.communicate()
        exit_code = proc.returncode if proc.returncode is not None else -1

    wall = time.monotonic() - start
    status = parse_status(output, exit_code, timed_out)

    log_path.write_text(output, encoding="utf-8", errors="replace")
    return {
        "name": name,
        "aig_path": str(aig_path),
        "size_bytes": str(aig_path.stat().st_size),
        "engine": args.engine,
        "status": status,
        "exit_code": str(exit_code),
        "wall_seconds": f"{wall:.3f}",
        "timed_out": "1" if timed_out else "0",
        "log_path": str(log_path),
        "command": " ".join(command),
    }


def append_row(output: Path, row: dict[str, str]) -> None:
    with TSV_LOCK:
        with output.open("a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=HEADER, delimiter="\t")
            writer.writerow(row)


def main() -> int:
    args = parse_args()
    resolve_dirs(args)
    if not args.data_dir.exists():
        raise SystemExit(f"missing data dir: {args.data_dir}")

    paths = discover(args.data_dir, args.sort, args.limit)
    if args.skip_existing:
        done = read_done_names(args.output)
        settings = {"year": args.year, "data_dir": str(args.data_dir)}
        paths = [p for p in paths if benchmark_name(p, settings) not in done]

    print(
        f"selected={len(paths)} data_dir={args.data_dir} engine={args.engine} "
        f"timeout={args.timeout:g}s workers={args.workers}"
    )
    if args.dry_run:
        return 0

    args.log_dir.mkdir(parents=True, exist_ok=True)
    ensure_output(args.output)

    completed = 0
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as executor:
        futures = {executor.submit(run_one, args, path): path for path in paths}
        for future in as_completed(futures):
            row = future.result()
            append_row(args.output, row)
            completed += 1
            elapsed = time.monotonic() - started
            print(
                f"[{completed}/{len(paths)}] {row['name']} {row['status']} "
                f"{row['wall_seconds']}s elapsed={elapsed:.1f}s",
                flush=True,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
