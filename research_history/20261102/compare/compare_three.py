#!/usr/bin/env python3
"""
三路对比: Modelchecker-xag vs PIC3(MiniSat) vs PIC3(CryptoMiniSat)

以 HWMCC 2015 为基准，对每个 benchmark 同时运行:
  1. Modelchecker-xag (PDR on AIG)       - 参照基准
  2. PIC3 + MiniSat  (BLIF)          - PIC3 的 MiniSat 后端
  3. PIC3 + CMS      (BLIF)          - PIC3 的 CryptoMiniSat 后端

结果输出为 CSV:
  name, mc_status, mc_time,
  pic3_minisat_status, pic3_minisat_time,
  pic3_cms_status, pic3_cms_time,
  match, note
"""

import argparse, concurrent.futures, os, subprocess, sys, threading, time
from datetime import datetime
from pathlib import Path

# ---- 路径配置 ----
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

MC_LOG_DIR = RESULTS_DIR / "modelchecker_logs"
PIC3_MINI_LOG_DIR = RESULTS_DIR / "pic3_minisat_logs"
PIC3_CMS_LOG_DIR = RESULTS_DIR / "pic3_cms_logs"

CSV_OUTPUT = RESULTS_DIR / "compare_three.tsv"

sys.path.insert(0, str(BLIF_DIR))
TSV_LOCK = threading.Lock()

# ---- 参数 ----
def parse_args():
    p = argparse.ArgumentParser(description="三路对比")
    p.add_argument("--workers", type=int, default=3, help="并发 worker 数 (建议 3~6)")
    p.add_argument("--pic3-parallel", type=int, default=4, help="PIC3 内部并行线程数")
    p.add_argument("--mc-pdr", type=int, default=1, help="Modelchecker-xag PDR 线程数")
    p.add_argument("--timeout", type=int, default=1800, help="每个工具超时 (秒)")
    p.add_argument("--max-size", type=int, default=5 * 1024 * 1024, help="最大 AIG 大小 (bytes)")
    p.add_argument("--skip-tested", action="store_true", help="跳过已有完整结果的 benchmark")
    p.add_argument("--keep-converted", action="store_true", help="保留转换后的 AAG/BLIF 文件")
    return p.parse_args()


# ---- 查找 AIG 文件 ----
def find_aig_files():
    files = []
    if HWMCC_SAMPLES.exists():
        with HWMCC_SAMPLES.open("r", encoding="utf-8", errors="ignore") as f:
            names = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        for n in names:
            p = HWMCC_DATA / n
            if p.exists():
                files.append(p)
    else:
        files = sorted(HWMCC_DATA.glob("*.aig"))
    files.sort(key=lambda p: p.stat().st_size)
    return files


# ---- 转换 AIG→AAG→BLIF ----
def convert_one(aig_path, force):
    name = aig_path.stem
    aag = CONV_AAG_DIR / f"{name}.aag"
    blif = CONV_BLIF_DIR / f"{name}.blif"

    # AIG → AAG
    if aag.exists() and aag.stat().st_size > 0 and not force:
        pass
    else:
        aag.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run([str(AIGTOAIG), str(aig_path), str(aag)],
                           check=True, capture_output=True, text=True, timeout=600)
        except Exception:
            return False
    if not aag.exists() or aag.stat().st_size == 0:
        return False

    # AAG → BLIF
    from extractxor import read_aag, build_netlist, extract_xors, write_blif
    if blif.exists() and blif.stat().st_size > 0 and not force:
        pass
    else:
        blif.parent.mkdir(parents=True, exist_ok=True)
        try:
            M, inputs, outputs, latches, and_gates, bad, cstr = read_aag(str(aag))
            nodes, and_ids = build_netlist(M, inputs, outputs, latches, and_gates, bad, cstr)
            extract_xors(nodes, and_ids)
            write_blif(nodes, inputs, outputs, latches, M, and_ids, str(blif), bad, cstr)
        except Exception:
            return False
    if not blif.exists() or blif.stat().st_size == 0:
        return False
    return True


# ---- 运行函数 ----
def _build_pic3_cmd(blif_path, parallel, solver):
    return [sys.executable, str(MAINBLIF),
            "--parallel", str(parallel),
            "--solver", solver,
            str(blif_path)]


def run_mc(aig_path, pdr_threads, timeout, log_path):
    cmd = [str(MODELCHECKER_BIN), "-pdr", str(pdr_threads), str(aig_path)]
    t0 = time.perf_counter()
    try:
        with open(log_path, 'w') as lf:
            lf.write(f"cmd: {' '.join(cmd)}\n")
            lf.flush()
            proc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT,
                                  timeout=timeout, cwd=str(MODELCHECKER_DIR))
        with open(log_path, 'r') as lf:
            out = lf.read()
        return _parse_mc(out, proc.returncode), time.perf_counter() - t0
    except subprocess.TimeoutExpired:
        return "TIMEOUT", time.perf_counter() - t0


def run_pic3_minisat(blif_path, parallel, timeout, log_path):
    cmd = _build_pic3_cmd(blif_path, parallel, "minisat")
    t0 = time.perf_counter()
    try:
        with open(log_path, 'w') as lf:
            lf.write(f"cmd: {' '.join(cmd)}\n")
            lf.flush()
            proc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT,
                                  timeout=timeout)
        with open(log_path, 'r') as lf:
            out = lf.read()
        return _parse_pic3(out, proc.returncode), time.perf_counter() - t0
    except subprocess.TimeoutExpired:
        return "TIMEOUT", time.perf_counter() - t0


def run_pic3_cms(blif_path, parallel, timeout, log_path):
    cmd = _build_pic3_cmd(blif_path, parallel, "cmsat")
    t0 = time.perf_counter()
    try:
        with open(log_path, 'w') as lf:
            lf.write(f"cmd: {' '.join(cmd)}\n")
            lf.flush()
            proc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT,
                                  timeout=timeout)
        with open(log_path, 'r') as lf:
            out = lf.read()
        return _parse_pic3(out, proc.returncode), time.perf_counter() - t0
    except subprocess.TimeoutExpired:
        return "TIMEOUT", time.perf_counter() - t0


# ---- 结果解析 ----
def _parse_pic3(out, rc):
    t = out.lower()
    if "the design is safe" in t:
        return "SAFE"
    if "the design is unsafe" in t:
        return "UNSAFE"
    if rc != 0:
        if "unsafe" in t:
            return "UNSAFE"
        if "safe" in t:
            return "SAFE"
        return "ERROR"
    if "safe" in t:
        return "SAFE"
    if "unsafe" in t:
        return "UNSAFE"
    return "UNKNOWN"


def _parse_mc(out, rc):
    t = out.lower()
    if "result: safe" in t:
        return "SAFE"
    if "result: unsafe" in t:
        return "UNSAFE"
    if "no output asserted" in t:
        return "SAFE"
    if rc != 0:
        return "ERROR"
    return "UNKNOWN"


# ---- 判断匹配 ----
def judge_match(mc_s, mini_s, cms_s):
    """判断三路结果匹配情况"""
    # 任何一方 ERROR → ERROR
    if "ERROR" in (mc_s, mini_s, cms_s):
        return "ERROR", f"MC={mc_s} MINISAT={mini_s} CMS={cms_s}"

    # 三方 TIMEOUT
    if mc_s == mini_s == cms_s == "TIMEOUT":
        return "OK", "ALL_TIMEOUT"

    # 部分 TIMEOUT
    timeouts = sum(1 for s in (mc_s, mini_s, cms_s) if s == "TIMEOUT")
    if timeouts > 0:
        return "TIMEOUT", f"MC={mc_s} MINISAT={mini_s} CMS={cms_s}"

    # 三方一致
    if mc_s == mini_s == cms_s:
        return "OK", ""

    # MC vs MiniSat 一致但 CMS 不同
    if mc_s == mini_s and mini_s != cms_s:
        return "MISMATCH", f"CMS={cms_s} vs MC/MINISAT={mc_s}"

    # MC vs CMS 一致但 MiniSat 不同
    if mc_s == cms_s and cms_s != mini_s:
        return "MISMATCH", f"MINISAT={mini_s} vs MC/CMS={mc_s}"

    # MiniSat vs CMS 一致但 MC 不同
    if mini_s == cms_s and cms_s != mc_s:
        return "MISMATCH", f"MC={mc_s} vs PIC3={mini_s}"

    # 三方互不相同
    return "MISMATCH", f"MC={mc_s} MINISAT={mini_s} CMS={cms_s}"


# ---- 加载已测试 ----
def load_tested_names():
    if not CSV_OUTPUT.exists():
        return set()
    tested = set()
    with CSV_OUTPUT.open("r") as f:
        for line in f:
            if line.startswith("name\t"):
                continue
            parts = line.strip().split("\t")
            if len(parts) >= 9:
                name, match = parts[0], parts[7]
                if match in ("OK", "MISMATCH", "TIMEOUT", "ERROR"):
                    tested.add(name)
    return tested


# ---- 主流程 ----
def main():
    args = parse_args()
    for d in [RESULTS_DIR, CONV_AAG_DIR, CONV_BLIF_DIR,
              MC_LOG_DIR, PIC3_MINI_LOG_DIR, PIC3_CMS_LOG_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # 检查工具
    for label, p in [("aigtoaig", AIGTOAIG), ("mainblif.py", MAINBLIF),
                     ("modelchecker", MODELCHECKER_BIN)]:
        if not p.exists():
            raise SystemExit(f"错误: 找不到 {label}: {p}")

    # ---- Phase 1: 转换 ----
    aig_files = find_aig_files()
    valid = [p for p in aig_files if p.stat().st_size <= args.max_size]
    print(f"共 {len(valid)} 个 benchmark (≤{args.max_size//1024//1024}MB)\n")

    convert_map = {}
    failed_conv = set()
    need_convert = []
    for p in valid:
        name = p.stem
        aag = CONV_AAG_DIR / f"{name}.aag"
        blif = CONV_BLIF_DIR / f"{name}.blif"
        if (aag.exists() and aag.stat().st_size > 0 and
            blif.exists() and blif.stat().st_size > 0):
            convert_map[name] = {"aag": aag, "blif": blif}
        else:
            need_convert.append(p)

    if need_convert:
        print(f"[Phase 1] 转换 {len(need_convert)} 个 ({args.workers} 并行)...")
        t0 = time.perf_counter()
        done = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
            fm = {ex.submit(convert_one, p, False): p for p in need_convert}
            for fut in concurrent.futures.as_completed(fm):
                p = fm[fut]; done += 1; name = p.stem
                if fut.result():
                    convert_map[name] = {
                        "aag": CONV_AAG_DIR / f"{name}.aag",
                        "blif": CONV_BLIF_DIR / f"{name}.blif",
                    }
                else:
                    failed_conv.add(name)
        print(f"[Phase 1] 完成: {len(convert_map)} 可用, {len(failed_conv)} 失败 "
              f"({time.perf_counter()-t0:.1f}s)\n")
    else:
        print(f"[Phase 1] 跳过: {len(convert_map)} 个已转换\n")

    # ---- Phase 2: 三路对比 ----
    # 写入 CSV header
    hdr = ["name",
           "mc_status", "mc_time",
           "pic3_minisat_status", "pic3_minisat_time",
           "pic3_cms_status", "pic3_cms_time",
           "match", "note"]
    CSV_OUTPUT.write_text("\t".join(hdr) + "\n")

    # 记录转换失败的
    for name in sorted(failed_conv):
        with CSV_OUTPUT.open("a") as f:
            f.write(f"{name}\tSKIPPED\t\tSKIPPED\t\tSKIPPED\t\tSKIPPED\tconvert_failed\n")

    # 跳过已测试
    ready = list(convert_map.items())
    skipped_tested = set()
    if args.skip_tested:
        tested = load_tested_names()
        ready = [(n, m) for n, m in ready if n not in tested]
        skipped_tested = {n for n in convert_map if n in tested}
        if skipped_tested:
            print(f"[Phase 2] 跳过 {len(skipped_tested)} 个已测试")

    if not ready:
        print("无可运行 benchmark")
        return

    print(f"[Phase 2] 三路对比: MC + PIC3(MiniSat) + PIC3(CMS)")
    print(f"  workers={args.workers}, pic3_parallel={args.pic3_parallel}, "
          f"mc_pdr={args.mc_pdr}, timeout={args.timeout}s\n")

    partials = {}
    t0 = time.perf_counter()
    done = 0
    total = len(ready)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        fm = {}
        for name, m in ready:
            aig_path = HWMCC_DATA / f"{name}.aig"
            blif_path = m["blif"]

            # 提交三个任务
            mc_log = MC_LOG_DIR / f"{name}.log"
            fm[ex.submit(run_mc, aig_path, args.mc_pdr, args.timeout, mc_log)] = \
                ("mc", name)

            mini_log = PIC3_MINI_LOG_DIR / f"{name}.log"
            fm[ex.submit(run_pic3_minisat, blif_path, args.pic3_parallel,
                         args.timeout, mini_log)] = ("minisat", name)

            cms_log = PIC3_CMS_LOG_DIR / f"{name}.log"
            fm[ex.submit(run_pic3_cms, blif_path, args.pic3_parallel,
                         args.timeout, cms_log)] = ("cms", name)

        for fut in concurrent.futures.as_completed(fm):
            tag, name = fm[fut]
            status, elapsed = fut.result()
            partials.setdefault(name, {})[tag] = (status, elapsed)

            # 三条结果都拿到后写 CSV
            if len(partials[name]) == 3:
                done += 1
                r = partials.pop(name)
                mc_s, mc_t = r.get("mc", ("UNKNOWN", 0))
                mini_s, mini_t = r.get("minisat", ("UNKNOWN", 0))
                cms_s, cms_t = r.get("cms", ("UNKNOWN", 0))

                match, note = judge_match(mc_s, mini_s, cms_s)

                row = [name,
                       mc_s, f"{mc_t:.3f}",
                       mini_s, f"{mini_t:.3f}",
                       cms_s, f"{cms_t:.3f}",
                       match, note]

                with TSV_LOCK:
                    with CSV_OUTPUT.open("a") as f:
                        f.write("\t".join(str(x) for x in row) + "\n")

                flag = {"OK": "✓", "MISMATCH": "✗", "TIMEOUT": "⏱",
                        "ERROR": "⚠"}.get(match, "?")
                print(f"  {flag} [{done:>4}/{total}] {name:<30s} "
                      f"MC={mc_s:<8s}({mc_t:.1f}s)  "
                      f"MINI={mini_s:<8s}({mini_t:.1f}s)  "
                      f"CMS={cms_s:<8s}({cms_t:.1f}s)  {match}",
                      flush=True)

    # ---- 统计 ----
    stats = {"OK": 0, "MISMATCH": 0, "TIMEOUT": 0, "ERROR": 0, "other": 0}
    if CSV_OUTPUT.exists():
        with CSV_OUTPUT.open("r") as f:
            next(f)  # skip header
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 8:
                    m = parts[7]
                    if m in stats:
                        stats[m] += 1
                    else:
                        stats["other"] += 1

    elapsed = time.perf_counter() - t0
    print(f"\n{'='*60}")
    print(f"三路对比完成: {datetime.now().isoformat()}")
    print(f"  总耗时: {elapsed:.1f}s ({elapsed/3600:.1f}h)")
    if skipped_tested:
        print(f"  跳过(已测): {len(skipped_tested)}")
    print(f"  一致: {stats['OK']}  |  不一致: {stats['MISMATCH']}  |  "
          f"超时: {stats['TIMEOUT']}  |  错误: {stats['ERROR']}")
    print(f"  结果: {CSV_OUTPUT}")


if __name__ == "__main__":
    main()
