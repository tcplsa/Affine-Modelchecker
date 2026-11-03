#!/usr/bin/env python3
"""Compare AIG/XAG and gen-CTG configurations on HWMCC 2015."""

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
DEFAULT_OUTPUT = RESULTS_DIR / "mc_aig_xag_genctg_hwmcc2015.tsv"
DEFAULT_SUMMARY = RESULTS_DIR / "mc_aig_xag_genctg_hwmcc2015_summary.tsv"
DEFAULT_LOG_DIR = RESULTS_DIR / "mc_aig_xag_genctg_hwmcc2015_logs"
DEFAULT_GROUP_FILE = SCRIPT_DIR / "hwmcc2015_groups_ric3_1800.json"


CONFIGS = [
    {"name": "aig", "mode": "aig", "env": {"MC_PDR_CTG_DEPTH": "0"}},
    {"name": "xag", "mode": "xag", "env": {"MC_PDR_CTG_DEPTH": "0"}},
    {"name": "aig_genctg", "mode": "aig", "env": {"MC_PDR_CTG_DEPTH": "1"}},
    {"name": "xag_genctg", "mode": "xag", "env": {"MC_PDR_CTG_DEPTH": "1"}},
]

DETAIL_HEADER = [
    "name",
    "aig_path",
    "size_bytes",
    "group",
    "config",
    "mode",
    "ctg_depth",
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
    "ands",
    "xors",
    "ors",
    "timed_out",
    "log_path",
    "command",
]

SUMMARY_HEADER = [
    "name",
    "aig_path",
    "size_bytes",
    "group",
    "aig_status",
    "aig_pdr",
    "xag_status",
    "xag_pdr",
    "xag_speedup_vs_aig",
    "aig_genctg_status",
    "aig_genctg_pdr",
    "aig_genctg_speedup_vs_aig",
    "xag_genctg_status",
    "xag_genctg_pdr",
    "xag_genctg_speedup_vs_aig",
    "best_config",
    "best_pdr",
    "best_speedup_vs_aig",
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


def install_signal_handlers() -> None:
    def handle_signal(_signum: int, _frame: object) -> None:
        SHUTDOWN.set()
        cleanup_active_processes(signal.SIGTERM)
        time.sleep(0.5)
        cleanup_active_processes(signal.SIGKILL)
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Modelchecker-xag with AIG/XAG and gen-CTG configurations."
    )
    parser.add_argument("--data-dir", type=Path, default=HWMCC_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--log-dir", type=Path, default=None)
    parser.add_argument("--modelchecker", type=Path, default=MODELCHECKER_BIN)
    parser.add_argument("--pdr", type=int, default=1)
    parser.add_argument("--workers", type=int, default=80)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sort", choices=["name", "size"], default="name")
    parser.add_argument("--group-file", type=Path, default=DEFAULT_GROUP_FILE)
    parser.add_argument("--group", choices=["all", "regular", "hard", "other"], default="all")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.summary_output is None:
        args.summary_output = (
            DEFAULT_SUMMARY
            if args.output == DEFAULT_OUTPUT
            else args.output.with_name(args.output.stem + "_summary.tsv")
        )
    if args.log_dir is None:
        args.log_dir = (
            DEFAULT_LOG_DIR
            if args.output == DEFAULT_OUTPUT
            else args.output.with_name(args.output.stem + "_logs")
        )
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


def read_done(output: Path) -> set[tuple[str, str]]:
    if not output.exists():
        return set()
    with output.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return {(row.get("name", ""), row.get("config", "")) for row in reader}


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
        elif line.startswith("c PDR_STATS "):
            kv = parse_key_values(line)
            row["pdr_runtime"] = kv.get("runtime", "")
            row["pdr_thread"] = kv.get("thread", "")
            row["depth"] = kv.get("depth", "")
            if kv.get("result"):
                row["status"] = kv["result"].upper()
        elif line.startswith("c PDR_COUNTERS "):
            kv = parse_key_values(line)
            for key in [
                "queries",
                "inductive",
                "cti",
                "ctg",
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
        elif line.startswith("c XAG_STATS "):
            kv = parse_key_values(line)
            row["ands"] = kv.get("ands", "")
            row["xors"] = kv.get("xors", "")
            row["ors"] = kv.get("ors", "")
    return row


def run_one(args: argparse.Namespace, aig_path: Path, config: dict[str, object]) -> dict[str, str]:
    name = aig_path.stem
    config_name = str(config["name"])
    mode = str(config["mode"])
    log_path = args.log_dir / config_name / f"{name}.log"
    command = [
        str(args.modelchecker),
        "-pdr",
        str(args.pdr),
        f"-{mode}",
        str(aig_path),
    ]

    env = os.environ.copy()
    env["MC_PDR_STATS"] = "1"
    env.update(config["env"])  # type: ignore[arg-type]

    row_base = {
        "name": name,
        "aig_path": str(aig_path),
        "size_bytes": str(aig_path.stat().st_size),
        "group": args.group,
        "config": config_name,
        "mode": mode,
        "ctg_depth": str(config["env"].get("MC_PDR_CTG_DEPTH", "")),  # type: ignore[index]
        "log_path": str(log_path),
        "command": " ".join(command),
    }

    if SHUTDOWN.is_set():
        row = {key: "" for key in DETAIL_HEADER}
        row.update(row_base)
        row.update({"status": "INTERRUPTED", "wall_seconds": "0.000", "timed_out": "0"})
        return row

    start = time.monotonic()
    timed_out = False
    exit_code = -1
    output = ""
    log_path.parent.mkdir(parents=True, exist_ok=True)
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
    row.update(row_base)
    row.update({
        "exit_code": str(exit_code),
        "wall_seconds": f"{time.monotonic() - start:.3f}",
        "timed_out": "1" if timed_out else "0",
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


def write_summary(output: Path, summary_output: Path) -> None:
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
            baseline = configs.get("aig")
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
                "group": baseline.get("group", ""),
                "aig_status": baseline["status"],
                "aig_pdr": baseline.get("pdr_runtime", ""),
                "xag_status": configs.get("xag", {}).get("status", ""),
                "xag_pdr": configs.get("xag", {}).get("pdr_runtime", ""),
                "xag_speedup_vs_aig": speedup("xag"),
                "aig_genctg_status": configs.get("aig_genctg", {}).get("status", ""),
                "aig_genctg_pdr": configs.get("aig_genctg", {}).get("pdr_runtime", ""),
                "aig_genctg_speedup_vs_aig": speedup("aig_genctg"),
                "xag_genctg_status": configs.get("xag_genctg", {}).get("status", ""),
                "xag_genctg_pdr": configs.get("xag_genctg", {}).get("pdr_runtime", ""),
                "xag_genctg_speedup_vs_aig": speedup("xag_genctg"),
                "best_config": best["config"],
                "best_pdr": best.get("pdr_runtime", ""),
                "best_speedup_vs_aig": f"{baseline_metric / metric(best):.6f}" if metric(best) > 0 else "",
            })


def shutdown_executor(executor: ThreadPoolExecutor) -> None:
    try:
        executor.shutdown(wait=False, cancel_futures=True)
    except TypeError:
        executor.shutdown(wait=False)


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
        f"pdr={args.pdr} group={args.group} timeout={args.timeout:g}s"
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

    write_summary(args.output, args.summary_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
