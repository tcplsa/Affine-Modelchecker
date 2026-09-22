#!/usr/bin/env python3
"""
PIC3 vs Modelchecker-xag 对拍脚本
以 HWMCC 2015 为基准，对比 PIC3 (PDR on BLIF) 和 Modelchecker-xag (PDR on AIG)。

流程:
  Phase 1: 并行转换 AIG→AAG→BLIF（只做一次，已有则跳过）
  Phase 2: 并行运行 PIC3 和 Modelchecker-xag（同 benchmark 两者同时跑）
"""

import argparse, concurrent.futures, os, subprocess, sys, threading, time
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TOOLS_DIR = SCRIPT_DIR.parent
ROOT = TOOLS_DIR.parent

BLIF_DIR = ROOT / "blif"
AIGTOAIG = BLIF_DIR / "aigtoaig"
MAINBLIF = BLIF_DIR / "mainblif.py"
MODELCHECKER_DIR = ROOT / "Modelchecker-xag" / "modelchecker"
MODELCHECKER_BIN = MODELCHECKER_DIR / "modelchecker"
HWMCC_DATA = TOOLS_DIR / "hwmcc2015" / "data"
HWMCC_SAMPLES = TOOLS_DIR / "hwmcc2015" / "samples" / "all.txt"

RESULTS_DIR = SCRIPT_DIR / "results"
CONV_AAG_DIR = RESULTS_DIR / "conversion" / "aag"
CONV_BLIF_DIR = RESULTS_DIR / "conversion" / "blif"
PIC3_LOG_DIR = RESULTS_DIR / "pic3_logs"
MC_LOG_DIR = RESULTS_DIR / "modelchecker_logs"
TSV_OUTPUT = RESULTS_DIR / "compare.tsv"

sys.path.insert(0, str(BLIF_DIR))
TSV_LOCK = threading.Lock()

def parse_args():
    p = argparse.ArgumentParser(description="PIC3 vs Modelchecker-xag 对拍")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--pic3-parallel", type=int, default=4)
    p.add_argument("--mc-pdr", type=int, default=1)
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--keep-converted", action="store_true")
    p.add_argument("--reconvert", action="store_true")
    p.add_argument("--max-size", type=int, default=5*1024*1024)
    p.add_argument("--skip-tested", action="store_true", help="跳过 TSV 中已有完整结果的 benchmark")
    return p.parse_args()

def find_aig_files():
    slp = HWMCC_SAMPLES
    files = []
    if slp.exists():
        with slp.open("r", encoding="utf-8", errors="ignore") as f:
            names = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        for n in names:
            p = HWMCC_DATA / n
            if p.exists():
                files.append(p)
    else:
        files = sorted(HWMCC_DATA.glob("*.aig"))
    files.sort(key=lambda p: p.stat().st_size)
    return files

def convert_one(aig_path, force):
    name = aig_path.stem
    aag = CONV_AAG_DIR / f"{name}.aag"
    blif = CONV_BLIF_DIR / f"{name}.blif"
    info = {"aag_ok":"","aag_time":"","blif_ok":"","blif_time":""}
    # AIG->AAG
    if aag.exists() and aag.stat().st_size > 0 and not force:
        info["aag_ok"], info["aag_time"] = "skip", "0"
    else:
        aag.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        try:
            subprocess.run([str(AIGTOAIG), str(aig_path), str(aag)],
                           check=True, capture_output=True, text=True, timeout=600)
            info["aag_ok"], info["aag_time"] = "ok", f"{time.perf_counter()-t0:.3f}"
        except Exception:
            info["aag_ok"], info["aag_time"] = "err", f"{time.perf_counter()-t0:.3f}"
            return False, info
    # AAG->BLIF
    from extractxor import read_aag, build_netlist, extract_xors, write_blif
    if blif.exists() and blif.stat().st_size > 0 and not force:
        info["blif_ok"], info["blif_time"] = "skip", "0"
    else:
        blif.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        try:
            M, inputs, outputs, latches, and_gates, bad, cstr = read_aag(str(aag))
            nodes, and_ids = build_netlist(M, inputs, outputs, latches, and_gates, bad, cstr)
            extract_xors(nodes, and_ids)
            write_blif(nodes, inputs, outputs, latches, M, and_ids, str(blif), bad, cstr)
            info["blif_ok"], info["blif_time"] = "ok", f"{time.perf_counter()-t0:.3f}"
        except Exception:
            info["blif_ok"], info["blif_time"] = "err", f"{time.perf_counter()-t0:.3f}"
            return False, info
    return True, info

# PIC3: stdout→file 避免 multiprocessing 管道死锁
def run_pic3(blif_path, parallel, timeout, log_path):
    cmd = [sys.executable, str(MAINBLIF), "--parallel", str(parallel), str(blif_path)]
    t0 = time.perf_counter()
    try:
        with open(log_path, 'w') as lf:
            lf.write(f"cmd: {' '.join(cmd)}\n")
            lf.flush()
            proc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, timeout=timeout)
        with open(log_path, 'r') as lf:
            out = lf.read()
        return _parse_pic3(out, proc.returncode), time.perf_counter()-t0
    except subprocess.TimeoutExpired:
        return "TIMEOUT", time.perf_counter()-t0

def run_mc(aig_path, pdr, timeout, log_path):
    cmd = [str(MODELCHECKER_BIN), "-pdr", str(pdr), str(aig_path)]
    t0 = time.perf_counter()
    try:
        with open(log_path, 'w') as lf:
            lf.write(f"cmd: {' '.join(cmd)}\n")
            lf.flush()
            proc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT,
                                  timeout=timeout, cwd=str(MODELCHECKER_DIR))
        with open(log_path, 'r') as lf:
            out = lf.read()
        return _parse_mc(out, proc.returncode), time.perf_counter()-t0
    except subprocess.TimeoutExpired:
        return "TIMEOUT", time.perf_counter()-t0

def _parse_pic3(out, rc):
    t = out.lower()
    if "the design is safe" in t: return "SAFE"
    if "the design is unsafe" in t: return "UNSAFE"
    if rc != 0:
        if "unsafe" in t: return "UNSAFE"
        if "safe" in t: return "SAFE"
        return "ERROR"
    if "safe" in t: return "SAFE"
    if "unsafe" in t: return "UNSAFE"
    return "UNKNOWN"

def _parse_mc(out, rc):
    t = out.lower()
    if "result: safe" in t: return "SAFE"
    if "result: unsafe" in t: return "UNSAFE"
    if "no output asserted" in t: return "SAFE"
    if rc != 0: return "ERROR"
    return "UNKNOWN"

def run_tool(tool, run_fn, path, threads, timeout, name):
    log_dir = PIC3_LOG_DIR if tool == "pic3" else MC_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{name}.log"
    t0 = time.perf_counter()
    print(f"  [{tool.upper():>2}] {name:<30s} 开始...", flush=True)
    status, elapsed = run_fn(path, threads, timeout, log_path)
    print(f"  [{tool.upper():>2}] {name:<30s} 完成  {status:<8s}  {elapsed:.1f}s", flush=True)
    key_s = "pic3_status" if tool == "pic3" else "mc_status"
    key_t = "pic3_time" if tool == "pic3" else "mc_time"
    return {"name": name, key_s: status, key_t: f"{elapsed:.3f}"}

def load_tested_names():
    """从已有 TSV 中读取已完成的 benchmark 名称（match 列为 OK/MISMATCH/TIMEOUT）"""
    if not TSV_OUTPUT.exists():
        return set()
    tested = set()
    with TSV_OUTPUT.open("r") as f:
        for line in f:
            if line.startswith("name\t"):
                continue
            parts = line.strip().split("\t")
            if len(parts) >= 11:
                name, match = parts[0], parts[10]
                if match in ("OK", "MISMATCH", "TIMEOUT"):
                    tested.add(name)
    return tested

def main():
    args = parse_args()
    for d in [RESULTS_DIR, CONV_AAG_DIR, CONV_BLIF_DIR, PIC3_LOG_DIR, MC_LOG_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    aig_files = find_aig_files()
    valid = [p for p in aig_files if p.stat().st_size <= args.max_size]
    print(f"共 {len(valid)} 个 benchmark（按文件大小升序）\n")

    for label, p in [("aigtoaig",AIGTOAIG),("mainblif.py",MAINBLIF),("modelchecker",MODELCHECKER_BIN)]:
        if not p.exists():
            raise SystemExit(f"错误: 找不到 {label}: {p}")

    # ---- Phase 1: 转换 ----
    convert_map = {}
    failed = set()
    need_convert = []
    for p in valid:
        name = p.stem
        aag = CONV_AAG_DIR / f"{name}.aag"
        blif = CONV_BLIF_DIR / f"{name}.blif"
        if (aag.exists() and aag.stat().st_size > 0 and
            blif.exists() and blif.stat().st_size > 0 and not args.reconvert):
            convert_map[name] = {"aag": aag, "blif": blif,
                                 "info": {"aag_ok":"skip","aag_time":"0","blif_ok":"skip","blif_time":"0"}}
        else:
            need_convert.append(p)

    if need_convert:
        print(f"[Phase 1] 转换 {len(need_convert)} 个 ({args.workers} 并行)...")
        t0 = time.perf_counter(); done = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
            fm = {ex.submit(convert_one, p, args.reconvert): p for p in need_convert}
            for fut in concurrent.futures.as_completed(fm):
                p = fm[fut]; ok, info = fut.result(); done += 1; name = p.stem
                if ok:
                    convert_map[name] = {"aag": CONV_AAG_DIR/f"{name}.aag",
                                         "blif": CONV_BLIF_DIR/f"{name}.blif", "info": info}
                else:
                    failed.add(name)
                if done % 100 == 0: print(f"  转换: {done}/{len(need_convert)}")
        print(f"[Phase 1] 完成: {len(convert_map)} 可用, {len(failed)} 失败 ({time.perf_counter()-t0:.1f}s)\n")
    else:
        print(f"[Phase 1] 跳过: {len(convert_map)} 个已转换\n")

    # TSV header
    hdr = "\t".join(["name","aig_path","pic3_status","pic3_time","mc_status","mc_time",
                     "aag_conv","aag_time","blif_conv","blif_time","match","note"])
    TSV_OUTPUT.write_text(hdr + "\n")
    for name in failed:
        with TSV_OUTPUT.open("a") as f:
            f.write(f"{name}\t\tSKIPPED\t\tSKIPPED\t\t\t\t\tSKIPPED\tconvert_failed\n")

    # ---- Phase 2: 并行 PIC3 & MC ----
    ready = list(convert_map.items())

    # 跳过已测试的
    skipped_tested = set()
    if args.skip_tested:
        tested = load_tested_names()
        ready = [(n, m) for n, m in ready if n not in tested]
        skipped_tested = {n for n in convert_map if n in tested}
        if skipped_tested:
            print(f"[Phase 2] 跳过 {len(skipped_tested)} 个已测试")

    if not ready:
        print("无可运行 benchmark"); return

    print(f"[Phase 2] PIC3 & MC (workers={args.workers}, pic3={args.pic3_parallel}th, mc-pdr={args.mc_pdr}th, timeout={args.timeout}s)\n")

    partials = {}; t0 = time.perf_counter(); done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        fm = {}
        for name, m in ready:
            aig_path = HWMCC_DATA / f"{name}.aig"
            fm[ex.submit(run_tool, "pic3", run_pic3, m["blif"], args.pic3_parallel, args.timeout, name)] = (name, aig_path)
            fm[ex.submit(run_tool, "mc", run_mc, aig_path, args.mc_pdr, args.timeout, name)] = (name, aig_path)

        for fut in concurrent.futures.as_completed(fm):
            name, aig_path = fm[fut]
            r = fut.result()
            partials.setdefault(name, []).append(r)
            if len(partials[name]) == 2:
                done += 1
                p1, p2 = partials.pop(name)
                m = {"name": name, "aig": str(aig_path),
                     "pic3_status":"SKIPPED","pic3_time":"","mc_status":"SKIPPED","mc_time":"",
                     "aag_ok":"","aag_time":"","blif_ok":"","blif_time":"","match":"","note":""}
                info = convert_map[name]["info"]
                m.update(info)
                m.update(p1); m.update(p2)

                ps, ms = m["pic3_status"], m["mc_status"]
                if ps == ms: m["match"] = "OK"
                elif "TIMEOUT" in (ps,ms): m["match"] = "TIMEOUT"
                else: m["match"] = "MISMATCH"; m["note"] = f"PIC3={ps} MC={ms}"

                row = "\t".join(str(m.get(k,"")) for k in hdr.split("\t"))
                with TSV_LOCK:
                    with TSV_OUTPUT.open("a") as f:
                        f.write(row + "\n")

                flag = {"OK":"✓","MISMATCH":"✗","TIMEOUT":"⏱"}.get(m["match"],"?")
                print(f"  >>> {flag} {name:<30s} PIC3={ps:<8s} MC={ms:<8s} {m['match']}", flush=True)

                if not args.keep_converted:
                    for pp in [convert_map[name]["aag"], convert_map[name]["blif"]]:
                        try:
                            if pp.exists(): pp.unlink()
                        except Exception: pass

    # 统计
    ok = mismatch = timeout = err = 0
    if TSV_OUTPUT.exists():
        with TSV_OUTPUT.open("r") as f:
            for line in f:
                if line.startswith("name\t"):
                    continue
                parts = line.strip().split("\t")
                if len(parts) >= 11:
                    m = parts[10]
                    if m == "OK":
                        ok += 1
                    elif m == "MISMATCH":
                        mismatch += 1
                    elif m == "TIMEOUT":
                        timeout += 1
                    elif m not in ("SKIPPED", ""):
                        err += 1

    elapsed = time.perf_counter() - t0
    print(f"\n{'='*60}")
    print(f"完成: {datetime.now().isoformat()}")
    print(f"  总耗时: {elapsed:.1f}s ({elapsed/3600:.1f}h)")
    if skipped_tested:
        print(f"  跳过(已测): {len(skipped_tested)}")
    print(f"  一致: {ok}  |  不一致: {mismatch}  |  超时: {timeout}  |  错误: {err}")
    print(f"结果: {TSV_OUTPUT}")

if __name__ == "__main__":
    main()
