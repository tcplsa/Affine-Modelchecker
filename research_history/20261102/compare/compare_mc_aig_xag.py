#!/usr/bin/env python3
"""
Modelchecker-xag AIG vs XAG 对比脚本。

对 HWMCC 2015 的 AIG benchmark 同时运行:
  1. Modelchecker-xag PDR -aig
  2. Modelchecker-xag PDR -xag

结果写入 results/compare_mc_aig_xag.tsv，并分别保存日志到:
  results/modelchecker_aig_logs/
  results/modelchecker_xag_logs/
"""

import argparse
import concurrent.futures
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
TOOLS_DIR = SCRIPT_DIR.parent
ROOT = TOOLS_DIR.parent

MODELCHECKER_DIR = ROOT / "Modelchecker-xag" / "modelchecker"
MODELCHECKER_BIN = MODELCHECKER_DIR / "modelchecker"

HWMCC_DATA = TOOLS_DIR / "hwmcc2015" / "data"
HWMCC_SAMPLES = TOOLS_DIR / "hwmcc2015" / "samples" / "all.txt"

RESULTS_DIR = SCRIPT_DIR / "results"
MC_AIG_LOG_DIR = RESULTS_DIR / "modelchecker_aig_logs"
MC_XAG_LOG_DIR = RESULTS_DIR / "modelchecker_xag_logs"
TSV_OUTPUT = RESULTS_DIR / "compare_mc_aig_xag.tsv"

TSV_LOCK = threading.Lock()


HEADER = [
    "name",
    "aig_path",
    "aig_status",
    "aig_wall",
    "aig_reported",
    "aig_depth",
    "aig_queries",
    "aig_inductive",
    "aig_ands",
    "aig_xors",
    "xag_status",
    "xag_wall",
    "xag_reported",
    "xag_depth",
    "xag_queries",
    "xag_inductive",
    "xag_ands",
    "xag_xors",
    "speedup_wall",
    "same_result",
    "note",
]


def parse_args():
    p = argparse.ArgumentParser(description="Modelchecker-xag AIG vs XAG on HWMCC2015")
    p.add_argument("--data-dir", type=Path, default=HWMCC_DATA, help="AIG benchmark 目录")
    p.add_argument("--workers", type=int, default=4, help="benchmark 并发数")
    p.add_argument("--mc-pdr", type=int, default=1, help="Modelchecker-xag -pdr 线程数，建议先用 1 降低噪声")
    p.add_argument("--timeout", type=int, default=1800, help="每个模式超时秒数")
    p.add_argument("--max-size", type=int, default=5 * 1024 * 1024, help="最大 AIG 文件大小 bytes")
    p.add_argument("--limit", type=int, default=0, help="只跑前 N 个按大小排序的 benchmark，0 表示不限")
    p.add_argument("--sample-file", type=Path, default=HWMCC_SAMPLES, help="benchmark 名单文件")
    p.add_argument("--output", type=Path, default=TSV_OUTPUT, help="TSV 输出路径")
    p.add_argument("--skip-tested", action="store_true", help="跳过输出 TSV 中已有完整结果的 benchmark")
    p.add_argument("--no-stats", action="store_true", help="不设置 MC_PDR_STATS=1")
    p.add_argument("--solver", choices=["cadical", "minisat"], default="", help="可选设置 MC_PDR_SOLVER")
    return p.parse_args()


def find_aig_files(data_dir, sample_file, max_size, limit):
    files = []
    if sample_file and sample_file.exists():
        with sample_file.open("r", encoding="utf-8", errors="ignore") as f:
            names = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        for name in names:
            p = data_dir / name
            if not p.exists() and not name.endswith(".aig"):
                p = data_dir / f"{name}.aig"
            if p.exists():
                files.append(p)
    else:
        files = sorted(data_dir.glob("*.aig"))

    files = [p for p in files if p.stat().st_size <= max_size]
    files.sort(key=lambda p: p.stat().st_size)
    if limit > 0:
        files = files[:limit]
    return files


def parse_key_values(line):
    result = {}
    for part in line.split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        result[key] = value
    return result


def parse_mc_output(out, rc):
    lower = out.lower()
    if "result: safe" in lower:
        status = "SAFE"
    elif "result: unsafe" in lower:
        status = "UNSAFE"
    elif "no output asserted" in lower:
        status = "SAFE"
    elif rc != 0:
        status = "ERROR"
    else:
        status = "UNKNOWN"

    info = {
        "status": status,
        "reported": "",
        "depth": "",
        "queries": "",
        "inductive": "",
        "ands": "",
        "xors": "",
    }

    m = re.search(r"^time\s*=\s*([0-9.]+)s", out, re.MULTILINE)
    if m:
        info["reported"] = m.group(1)

    for line in out.splitlines():
        if "PDR_STATS" in line:
            kv = parse_key_values(line)
            info["depth"] = kv.get("depth", info["depth"])
        elif "PDR_COUNTERS" in line:
            kv = parse_key_values(line)
            info["queries"] = kv.get("queries", info["queries"])
            info["inductive"] = kv.get("inductive", info["inductive"])
        elif "XAG_STATS" in line:
            kv = parse_key_values(line)
            info["ands"] = kv.get("ands", info["ands"])
            info["xors"] = kv.get("xors", info["xors"])

    return info


def run_mc_mode(aig_path, mode, pdr_threads, timeout, log_path, stats, solver):
    cmd = [str(MODELCHECKER_BIN), "-pdr", str(pdr_threads), mode, str(aig_path)]
    env = os.environ.copy()
    if stats:
        env["MC_PDR_STATS"] = "1"
    if solver:
        env["MC_PDR_SOLVER"] = solver

    t0 = time.perf_counter()
    try:
        with open(log_path, "w") as lf:
            lf.write("cmd: " + " ".join(cmd) + "\n")
            if stats:
                lf.write("env: MC_PDR_STATS=1\n")
            if solver:
                lf.write(f"env: MC_PDR_SOLVER={solver}\n")
            lf.flush()
            proc = subprocess.run(
                cmd,
                stdout=lf,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                cwd=str(MODELCHECKER_DIR),
                env=env,
            )
        with open(log_path, "r", errors="ignore") as lf:
            out = lf.read()
        info = parse_mc_output(out, proc.returncode)
    except subprocess.TimeoutExpired:
        info = {
            "status": "TIMEOUT",
            "reported": "",
            "depth": "",
            "queries": "",
            "inductive": "",
            "ands": "",
            "xors": "",
        }

    info["wall"] = f"{time.perf_counter() - t0:.3f}"
    return info


def run_one(aig_path, args):
    name = aig_path.stem
    aig_log_dir = args.log_dir / "aig"
    xag_log_dir = args.log_dir / "xag"
    aig_log_dir.mkdir(parents=True, exist_ok=True)
    xag_log_dir.mkdir(parents=True, exist_ok=True)

    print(f"  [MC] {name:<30s} start AIG/XAG", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        fa = ex.submit(
            run_mc_mode,
            aig_path,
            "-aig",
            args.mc_pdr,
            args.timeout,
            aig_log_dir / f"{name}.log",
            not args.no_stats,
            args.solver,
        )
        fx = ex.submit(
            run_mc_mode,
            aig_path,
            "-xag",
            args.mc_pdr,
            args.timeout,
            xag_log_dir / f"{name}.log",
            not args.no_stats,
            args.solver,
        )
        aig = fa.result()
        xag = fx.result()

    try:
        speedup = float(aig["wall"]) / float(xag["wall"]) if float(xag["wall"]) > 0 else 0.0
        speedup_s = f"{speedup:.3f}"
    except Exception:
        speedup_s = ""

    same = "YES" if aig["status"] == xag["status"] else "NO"
    note = ""
    if "ERROR" in (aig["status"], xag["status"]):
        note = f"AIG={aig['status']} XAG={xag['status']}"
    elif "TIMEOUT" in (aig["status"], xag["status"]):
        note = f"AIG={aig['status']} XAG={xag['status']}"
    elif same == "NO":
        note = f"AIG={aig['status']} XAG={xag['status']}"

    print(
        f"  [MC] {name:<30s} AIG={aig['status']:<8s} {aig['wall']:>8s}s  "
        f"XAG={xag['status']:<8s} {xag['wall']:>8s}s  speedup={speedup_s}",
        flush=True,
    )

    return {
        "name": name,
        "aig_path": str(aig_path),
        "aig_status": aig["status"],
        "aig_wall": aig["wall"],
        "aig_reported": aig["reported"],
        "aig_depth": aig["depth"],
        "aig_queries": aig["queries"],
        "aig_inductive": aig["inductive"],
        "aig_ands": aig["ands"],
        "aig_xors": aig["xors"],
        "xag_status": xag["status"],
        "xag_wall": xag["wall"],
        "xag_reported": xag["reported"],
        "xag_depth": xag["depth"],
        "xag_queries": xag["queries"],
        "xag_inductive": xag["inductive"],
        "xag_ands": xag["ands"],
        "xag_xors": xag["xors"],
        "speedup_wall": speedup_s,
        "same_result": same,
        "note": note,
    }


def load_tested_names(output):
    if not output.exists():
        return set()
    tested = set()
    with output.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("name\t"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= len(HEADER):
                name = parts[0]
                same = parts[19]
                note = parts[20]
                if same in ("YES", "NO") or "TIMEOUT" in note or "ERROR" in note:
                    tested.add(name)
    return tested


def append_row(output, row):
    line = "\t".join(str(row.get(key, "")) for key in HEADER)
    with TSV_LOCK:
        with output.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def main():
    args = parse_args()
    args.log_dir = args.output.with_name(args.output.stem + "_logs")
    for d in [RESULTS_DIR, args.log_dir]:
        d.mkdir(parents=True, exist_ok=True)

    if not MODELCHECKER_BIN.exists():
        raise SystemExit(f"错误: 找不到 modelchecker: {MODELCHECKER_BIN}")

    aig_files = find_aig_files(args.data_dir, args.sample_file, args.max_size, args.limit)
    if args.skip_tested:
        tested = load_tested_names(args.output)
        before = len(aig_files)
        aig_files = [p for p in aig_files if p.stem not in tested]
        print(f"跳过已测 {before - len(aig_files)} 个")

    if not aig_files:
        print("无可运行 benchmark")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not args.output.exists() or not args.skip_tested:
        args.output.write_text("\t".join(HEADER) + "\n", encoding="utf-8")

    print(
        f"共 {len(aig_files)} 个 benchmark，workers={args.workers}, "
        f"mc-pdr={args.mc_pdr}, timeout={args.timeout}s, output={args.output}"
    )
    print(f"开始: {datetime.now().isoformat()}\n")

    t0 = time.perf_counter()
    done = 0
    same = diff = timeout = error = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        future_map = {ex.submit(run_one, p, args): p for p in aig_files}
        for fut in concurrent.futures.as_completed(future_map):
            row = fut.result()
            append_row(args.output, row)
            done += 1

            if row["same_result"] == "YES":
                same += 1
            else:
                diff += 1
            if "TIMEOUT" in (row["aig_status"], row["xag_status"]):
                timeout += 1
            if "ERROR" in (row["aig_status"], row["xag_status"]):
                error += 1

            if done % 20 == 0 or done == len(aig_files):
                print(
                    f"进度 {done}/{len(aig_files)} same={same} diff={diff} "
                    f"timeout={timeout} error={error}",
                    flush=True,
                )

    elapsed = time.perf_counter() - t0
    print("\n" + "=" * 60)
    print(f"完成: {datetime.now().isoformat()}")
    print(f"总耗时: {elapsed:.1f}s ({elapsed / 3600:.2f}h)")
    print(f"一致: {same}  不一致: {diff}  超时: {timeout}  错误: {error}")
    print(f"结果: {args.output}")


if __name__ == "__main__":
    main()
