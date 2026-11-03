#!/usr/bin/env python3
"""Compare Modelchecker-xag CTG configurations on HWMCC 2015."""

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


SCRIPT_DIR = Path(__file__).resolve().parent
TOOLS_DIR = SCRIPT_DIR.parent
ROOT = TOOLS_DIR.parent
MODELCHECKER_DIR = ROOT / "Modelchecker-xag" / "modelchecker"
MODELCHECKER_BIN = MODELCHECKER_DIR / "modelchecker"
HWMCC_DATA = TOOLS_DIR / "hwmcc2015" / "data"
RESULTS_DIR = SCRIPT_DIR / "results"
DEFAULT_OUTPUT = RESULTS_DIR / "mc_ctg_hwmcc2015.tsv"
DEFAULT_SUMMARY = RESULTS_DIR / "mc_ctg_hwmcc2015_summary.tsv"
DEFAULT_LOG_DIR = RESULTS_DIR / "mc_ctg_hwmcc2015_logs"
DEFAULT_GROUP_FILE = SCRIPT_DIR / "hwmcc2015_groups_ric3_1800.json"

CONFIGS = [
    {
        "name": "no_ctg",
        "env": {
            "MC_PDR_CTG_DEPTH": "0",
            "MC_PDR_PUSH_CTG_TRIES": "0",
            "MC_PDR_PUSH_CTG_DEPTH": "0",
            "MC_PDR_PUSH_CTG_MAX_CUBE": "3",
            "MC_PDR_PUSH_CTG_LIGHT": "1",
            "MC_PDR_PUSH_CTG_TOP_ONLY": "1",
        },
    },
    {
        "name": "gen_ctg",
        "env": {
            "MC_PDR_CTG_DEPTH": "1",
            "MC_PDR_PUSH_CTG_TRIES": "0",
            "MC_PDR_PUSH_CTG_DEPTH": "0",
            "MC_PDR_PUSH_CTG_MAX_CUBE": "3",
            "MC_PDR_PUSH_CTG_LIGHT": "1",
            "MC_PDR_PUSH_CTG_TOP_ONLY": "1",
        },
    },
    {
        "name": "push_ctg",
        "env": {
            "MC_PDR_CTG_DEPTH": "0",
            "MC_PDR_PUSH_CTG_TRIES": "1",
            "MC_PDR_PUSH_CTG_DEPTH": "1",
            "MC_PDR_PUSH_CTG_MAX_CUBE": "3",
            "MC_PDR_PUSH_CTG_LIGHT": "1",
            "MC_PDR_PUSH_CTG_TOP_ONLY": "1",
        },
    },
    {
        "name": "both_ctg",
        "env": {
            "MC_PDR_CTG_DEPTH": "1",
            "MC_PDR_PUSH_CTG_TRIES": "1",
            "MC_PDR_PUSH_CTG_DEPTH": "1",
            "MC_PDR_PUSH_CTG_MAX_CUBE": "3",
            "MC_PDR_PUSH_CTG_LIGHT": "1",
            "MC_PDR_PUSH_CTG_TOP_ONLY": "1",
        },
    },
]

DETAIL_HEADER = [
    "name",
    "aig_path",
    "size_bytes",
    "mode",
    "group",
    "config",
    "status",
    "exit_code",
    "wall_seconds",
    "reported_seconds",
    "pdr_runtime",
    "pdr_thread",
    "depth",
    "queries",
    "inductive",
    "cti",
    "ctg",
    "push_ctg",
    "push_ctg_success",
    "push_ctg_effective",
    "push_ctg_useless",
    "push_ctg_failed",
    "push_ctg_skipped",
    "mic",
    "block",
    "generalize",
    "extract",
    "pre",
    "propagate",
    "push",
    "unpush",
    "core_reduced",
    "abort_join",
    "abort_mic",
    "timed_out",
    "log_path",
    "command",
]

SUMMARY_HEADER = [
    "name",
    "aig_path",
    "size_bytes",
    "mode",
    "baseline_status",
    "baseline_pdr",
    "gen_status",
    "gen_pdr",
    "gen_speedup",
    "push_status",
    "push_pdr",
    "push_speedup",
    "both_status",
    "both_pdr",
    "both_speedup",
    "group",
    "best_config",
    "best_pdr",
    "best_speedup",
]

TSV_LOCK = threading.Lock()
PROC_LOCK = threading.Lock()
ACTIVE_PROCS: set[subprocess.Popen[str]] = set()
SHUTDOWN = threading.Event()


def register_proc(proc: subprocess.Popen[str]) -> None:
    with PROC_LOCK:
        ACTIVE_PROCS.add(proc)


def unregister_proc(proc: subprocess.Popen[str]) -> None:
    with PROC_LOCK:
        ACTIVE_PROCS.discard(proc)


def terminate_proc_tree(proc: subprocess.Popen[str], sig: signal.Signals = signal.SIGTERM) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        return


def cleanup_active_processes(sig: signal.Signals = signal.SIGTERM) -> None:
    with PROC_LOCK:
        procs = list(ACTIVE_PROCS)
    for proc in procs:
        terminate_proc_tree(proc, sig)


def shutdown_executor(executor: ThreadPoolExecutor) -> None:
    try:
        executor.shutdown(wait=False, cancel_futures=True)
    except TypeError:
        executor.shutdown(wait=False)


def install_signal_handlers() -> None:
    def handle_signal(signum: int, _frame: object) -> None:
        SHUTDOWN.set()
        cleanup_active_processes(signal.SIGTERM)
        time.sleep(0.5)
        cleanup_active_processes(signal.SIGKILL)
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Modelchecker-xag on HWMCC 2015 with four CTG configurations."
    )
    parser.add_argument("--data-dir", type=Path, default=HWMCC_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--log-dir", type=Path, default=None)
    parser.add_argument("--modelchecker", type=Path, default=MODELCHECKER_BIN)
    parser.add_argument("--mode", choices=["aig", "xag"], default="xag")
    parser.add_argument("--pdr", type=int, default=1, help="PDR threads per Modelchecker-xag process")
    parser.add_argument("--workers", type=int, default=40, help="concurrent Modelchecker-xag processes")
    parser.add_argument("--timeout", type=float, default=300.0, help="per job timeout in seconds")
    parser.add_argument("--limit", type=int, default=0, help="run first N benchmarks; 0 means all")
    parser.add_argument("--sort", choices=["name", "size"], default="name")
    parser.add_argument("--group-file", type=Path, default=DEFAULT_GROUP_FILE)
    parser.add_argument("--group", choices=["all", "regular", "hard", "other"], default="all")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.summary_output is None:
        if args.output == DEFAULT_OUTPUT:
            args.summary_output = DEFAULT_SUMMARY
        else:
            args.summary_output = args.output.with_name(args.output.stem + "_summary.tsv")
    if args.log_dir is None:
        if args.output == DEFAULT_OUTPUT:
            args.log_dir = DEFAULT_LOG_DIR
        else:
            args.log_dir = args.output.with_name(args.output.stem + "_logs")
    return args


def load_group_filter(group_file: Path, group: str) -> set[str] | None:
    if group == "all":
        return None
    if not group_file.exists():
        raise SystemExit(f"missing group file: {group_file}")
    with group_file.open("r", encoding="utf-8") as f:
        data = json.load(f)
    groups = data.get("groups", {})
    names = groups.get(group)
    if names is None:
        raise SystemExit(f"group {group!r} not found in {group_file}")
    return {str(name) for name in names}


def discover(data_dir: Path, sort_by: str, limit: int, allowed_names: set[str] | None) -> list[Path]:
    paths = list(data_dir.glob("*.aig"))
    if allowed_names is not None:
        paths = [path for path in paths if path.stem in allowed_names]
    if sort_by == "size":
        paths.sort(key=lambda p: (p.stat().st_size, p.name))
    else:
        paths.sort(key=lambda p: p.name)
    if limit > 0:
        paths = paths[:limit]
    return paths


def read_done(output: Path) -> set[tuple[str, str]]:
    if not output.exists():
        return set()
    with output.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return {(row.get("name", ""), row.get("config", "")) for row in reader}


def ensure_output(output: Path, header: list[str]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists() or output.stat().st_size == 0:
        with output.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f, delimiter="\t").writerow(header)
        return

    with output.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        old_header = reader.fieldnames or []
        if old_header == header:
            return
        rows = list(reader)

    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in header})


def parse_key_values(line: str) -> dict[str, str]:
    out = {}
    for part in line.split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        out[key] = value
    return out


def parse_output(text: str, exit_code: int, timed_out: bool) -> dict[str, str]:
    row = {key: "" for key in DETAIL_HEADER}
    if timed_out:
        row["status"] = "TIMEOUT"
        return row

    lower = text.lower()
    if "result: safe" in lower:
        row["status"] = "SAFE"
    elif "result: unsafe" in lower:
        row["status"] = "UNSAFE"
    elif exit_code == 0:
        row["status"] = "UNKNOWN"
    else:
        row["status"] = "ERROR"

    for line in text.splitlines():
        if line.startswith("time ="):
            row["reported_seconds"] = line.split("=", 1)[1].strip().rstrip("s")
            continue
        if line.startswith("c PDR_STATS "):
            kv = parse_key_values(line)
            row["pdr_runtime"] = kv.get("runtime", "")
            row["pdr_thread"] = kv.get("thread", "")
            row["depth"] = kv.get("depth", "")
            if kv.get("result"):
                row["status"] = kv["result"].upper()
            continue
        if line.startswith("c PDR_COUNTERS "):
            kv = parse_key_values(line)
            for key in [
                "queries",
                "inductive",
                "cti",
                "ctg",
                "push_ctg",
                "push_ctg_success",
                "push_ctg_effective",
                "push_ctg_useless",
                "push_ctg_failed",
                "push_ctg_skipped",
                "mic",
                "block",
                "generalize",
                "extract",
                "pre",
                "propagate",
                "push",
                "unpush",
                "core_reduced",
                "abort_join",
                "abort_mic",
            ]:
                row[key] = kv.get(key, row[key])
    return row


def run_one(args: argparse.Namespace, aig_path: Path, config: dict[str, object]) -> dict[str, str]:
    name = aig_path.stem
    config_name = str(config["name"])
    log_path = args.log_dir / config_name / f"{name}.log"
    command = [
        str(args.modelchecker),
        "-pdr",
        str(args.pdr),
        f"-{args.mode}",
        str(aig_path),
    ]

    env = os.environ.copy()
    env["MC_PDR_STATS"] = "1"
    env.update(config["env"])  # type: ignore[arg-type]

    start = time.monotonic()
    timed_out = False
    exit_code = -1
    output = ""

    log_path.parent.mkdir(parents=True, exist_ok=True)
    if SHUTDOWN.is_set():
        row = {key: "" for key in DETAIL_HEADER}
        row.update({
            "name": name,
            "aig_path": str(aig_path),
            "size_bytes": str(aig_path.stat().st_size),
            "mode": args.mode,
            "group": args.group,
            "config": config_name,
            "status": "INTERRUPTED",
            "exit_code": "",
            "wall_seconds": "0.000",
            "timed_out": "0",
            "log_path": str(log_path),
            "command": " ".join(command),
        })
        return row

    proc = subprocess.Popen(
        command,
        cwd=str(MODELCHECKER_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        env=env,
        start_new_session=True,
    )
    register_proc(proc)
    try:
        output, _ = proc.communicate(timeout=args.timeout)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        terminate_proc_tree(proc, signal.SIGTERM)
        try:
            output, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            terminate_proc_tree(proc, signal.SIGKILL)
            output, _ = proc.communicate()
        exit_code = proc.returncode if proc.returncode is not None else -1
    finally:
        unregister_proc(proc)

    log_path.write_text(
        "cmd: " + " ".join(command) + "\n"
        + "env: " + " ".join(f"{k}={v}" for k, v in sorted(config["env"].items())) + "\n"  # type: ignore[union-attr]
        + output,
        encoding="utf-8",
        errors="replace",
    )

    row = parse_output(output, exit_code, timed_out)
    row.update({
        "name": name,
        "aig_path": str(aig_path),
        "size_bytes": str(aig_path.stat().st_size),
        "mode": args.mode,
        "group": args.group,
        "config": config_name,
        "exit_code": str(exit_code),
        "wall_seconds": f"{time.monotonic() - start:.3f}",
        "timed_out": "1" if timed_out else "0",
        "log_path": str(log_path),
        "command": " ".join(command),
    })
    return row


def append_row(output: Path, row: dict[str, str]) -> None:
    with TSV_LOCK:
        with output.open("a", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, fieldnames=DETAIL_HEADER, delimiter="\t").writerow(row)


def metric(row: dict[str, str]) -> float:
    value = row.get("pdr_runtime") or row.get("wall_seconds") or "inf"
    try:
        return float(value)
    except ValueError:
        return float("inf")


def write_summary(output: Path, summary_output: Path, mode: str) -> None:
    if not output.exists():
        return
    with output.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    by_name: dict[str, dict[str, dict[str, str]]] = {}
    for row in rows:
        if row.get("status") not in {"SAFE", "UNSAFE"}:
            continue
        by_name.setdefault(row["name"], {})[row["config"]] = row

    summary_output.parent.mkdir(parents=True, exist_ok=True)
    with summary_output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_HEADER, delimiter="\t")
        writer.writeheader()
        for name, configs in sorted(by_name.items()):
            baseline = configs.get("no_ctg")
            if not baseline:
                continue
            baseline_metric = metric(baseline)
            candidates = [row for row in configs.values() if metric(row) < float("inf")]
            best = min(candidates, key=metric) if candidates else baseline

            def speedup(config_name: str) -> str:
                row = configs.get(config_name)
                if not row or metric(row) <= 0 or baseline_metric == float("inf"):
                    return ""
                return f"{baseline_metric / metric(row):.6f}"

            writer.writerow({
                "name": name,
                "aig_path": baseline["aig_path"],
                "size_bytes": baseline["size_bytes"],
                "mode": mode,
                "baseline_status": baseline["status"],
                "baseline_pdr": baseline.get("pdr_runtime", ""),
                "gen_status": configs.get("gen_ctg", {}).get("status", ""),
                "gen_pdr": configs.get("gen_ctg", {}).get("pdr_runtime", ""),
                "gen_speedup": speedup("gen_ctg"),
                "push_status": configs.get("push_ctg", {}).get("status", ""),
                "push_pdr": configs.get("push_ctg", {}).get("pdr_runtime", ""),
                "push_speedup": speedup("push_ctg"),
                "both_status": configs.get("both_ctg", {}).get("status", ""),
                "both_pdr": configs.get("both_ctg", {}).get("pdr_runtime", ""),
                "both_speedup": speedup("both_ctg"),
                "group": baseline.get("group", ""),
                "best_config": best["config"],
                "best_pdr": best.get("pdr_runtime", ""),
                "best_speedup": f"{baseline_metric / metric(best):.6f}" if metric(best) > 0 else "",
            })


def main() -> int:
    install_signal_handlers()
    args = parse_args()
    if not args.data_dir.exists():
        raise SystemExit(f"missing data dir: {args.data_dir}")
    if not args.modelchecker.exists():
        raise SystemExit(f"missing modelchecker binary: {args.modelchecker}")

    allowed_names = load_group_filter(args.group_file, args.group)
    paths = discover(args.data_dir, args.sort, args.limit, allowed_names)
    jobs = [(path, config) for path in paths for config in CONFIGS]
    if args.skip_existing:
        done = read_done(args.output)
        jobs = [(path, config) for path, config in jobs if (path.stem, str(config["name"])) not in done]

    print(
        f"benchmarks={len(paths)} jobs={len(jobs)} workers={args.workers} "
        f"pdr={args.pdr} mode={args.mode} group={args.group} timeout={args.timeout:g}s"
    )
    if args.dry_run:
        return 0

    ensure_output(args.output, DETAIL_HEADER)
    completed = 0
    started = time.monotonic()
    executor = ThreadPoolExecutor(max_workers=max(args.workers, 1))
    try:
        futures = {
            executor.submit(run_one, args, path, config): (path, config)
            for path, config in jobs
        }
        for future in as_completed(futures):
            if SHUTDOWN.is_set():
                break
            row = future.result()
            append_row(args.output, row)
            completed += 1
            elapsed = time.monotonic() - started
            print(
                f"[{completed}/{len(jobs)}] {row['name']} {row['config']} "
                f"{row['status']} pdr={row.get('pdr_runtime', '')} "
                f"wall={row['wall_seconds']}s elapsed={elapsed:.1f}s",
                flush=True,
            )
    except KeyboardInterrupt:
        SHUTDOWN.set()
        cleanup_active_processes(signal.SIGTERM)
        time.sleep(0.5)
        cleanup_active_processes(signal.SIGKILL)
        shutdown_executor(executor)
        print("\ninterrupted; terminated active modelchecker processes", flush=True)
        return 130
    finally:
        shutdown_executor(executor)
        cleanup_active_processes(signal.SIGTERM)

    write_summary(args.output, args.summary_output, args.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
