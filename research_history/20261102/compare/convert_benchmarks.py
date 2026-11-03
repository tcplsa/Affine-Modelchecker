#!/usr/bin/env python3
"""
HWMCC 2015 基准转换脚本: AIG → AAG → BLIF
一次转换，所有 benchmark 的 AAG/BLIF 缓存到 results/conversion/ 下。
"""

import argparse, concurrent.futures, os, subprocess, sys, time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TOOLS_DIR = SCRIPT_DIR.parent
ROOT = TOOLS_DIR.parent

BLIF_DIR = ROOT / "blif"
AIGTOAIG = BLIF_DIR / "aigtoaig"
HWMCC_DATA = TOOLS_DIR / "hwmcc2015" / "data"
HWMCC_SAMPLES = TOOLS_DIR / "hwmcc2015" / "samples" / "all.txt"

RESULTS_DIR = SCRIPT_DIR / "results"
CONV_AAG_DIR = RESULTS_DIR / "conversion" / "aag"
CONV_BLIF_DIR = RESULTS_DIR / "conversion" / "blif"

sys.path.insert(0, str(BLIF_DIR))


def parse_args():
    p = argparse.ArgumentParser(description="HWMCC 2015 基准转换")
    p.add_argument("--workers", type=int, default=4, help="并行 worker 数")
    p.add_argument("--force", action="store_true", help="强制重新转换")
    p.add_argument("--max-size", type=int, default=5 * 1024 * 1024,
                   help="最大文件大小 (bytes)，默认 5MB")
    return p.parse_args()


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


def convert_one(aig_path, force):
    name = aig_path.stem
    aag = CONV_AAG_DIR / f"{name}.aag"
    blif = CONV_BLIF_DIR / f"{name}.blif"

    # --- AIG → AAG ---
    if aag.exists() and aag.stat().st_size > 0 and not force:
        aag_time = 0.0
    else:
        aag.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        try:
            subprocess.run([str(AIGTOAIG), str(aig_path), str(aag)],
                           check=True, capture_output=True, text=True, timeout=600)
            aag_time = time.perf_counter() - t0
        except Exception as e:
            print(f"  [ERR] {name} AIG→AAG: {e}", flush=True)
            return False
    # 验证
    if not aag.exists() or aag.stat().st_size == 0:
        print(f"  [ERR] {name} AAG 文件为空", flush=True)
        return False

    # --- AAG → BLIF ---
    from extractxor import read_aag, build_netlist, extract_xors, write_blif

    if blif.exists() and blif.stat().st_size > 0 and not force:
        blif_time = 0.0
    else:
        blif.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        try:
            M, inputs, outputs, latches, and_gates, bad, cstr = read_aag(str(aag))
            nodes, and_ids = build_netlist(M, inputs, outputs, latches, and_gates, bad, cstr)
            extract_xors(nodes, and_ids)
            write_blif(nodes, inputs, outputs, latches, M, and_ids, str(blif), bad, cstr)
            blif_time = time.perf_counter() - t0
        except Exception as e:
            print(f"  [ERR] {name} AAG→BLIF: {e}", flush=True)
            return False
    # 验证
    if not blif.exists() or blif.stat().st_size == 0:
        print(f"  [ERR] {name} BLIF 文件为空", flush=True)
        return False

    return True


def main():
    args = parse_args()
    for d in [RESULTS_DIR, CONV_AAG_DIR, CONV_BLIF_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    if not AIGTOAIG.exists():
        raise SystemExit(f"错误: 找不到 aigtoaig: {AIGTOAIG}")

    aig_files = find_aig_files()
    valid = [p for p in aig_files if p.stat().st_size <= args.max_size]
    print(f"共 {len(valid)} 个 benchmark (≤{args.max_size//1024//1024}MB)")
    print(f"转换目标: AAG → {CONV_AAG_DIR}")
    print(f"          BLIF → {CONV_BLIF_DIR}\n")

    # 跳过已转换的
    need_convert = []
    skip_count = 0
    for p in valid:
        name = p.stem
        aag = CONV_AAG_DIR / f"{name}.aag"
        blif = CONV_BLIF_DIR / f"{name}.blif"
        if (aag.exists() and aag.stat().st_size > 0 and
            blif.exists() and blif.stat().st_size > 0 and not args.force):
            skip_count += 1
        else:
            need_convert.append(p)

    if skip_count:
        print(f"跳过 {skip_count} 个已转换\n")

    if not need_convert:
        print("全部已转换，无需操作")
        return

    print(f"转换 {len(need_convert)} 个 ({args.workers} 并行)...\n")
    t0 = time.perf_counter()
    done = ok = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        fm = {ex.submit(convert_one, p, args.force): p for p in need_convert}
        for fut in concurrent.futures.as_completed(fm):
            p = fm[fut]
            name = p.stem
            success = fut.result()
            done += 1
            if success:
                ok += 1
            if done % 50 == 0:
                print(f"  进度: {done}/{len(need_convert)}  (成功 {ok})")

    elapsed = time.perf_counter() - t0
    print(f"\n{'='*50}")
    print(f"完成: {ok}/{len(need_convert)} 成功, {len(need_convert)-ok} 失败")
    print(f"耗时: {elapsed:.1f}s")
    print(f"AAG:  {CONV_AAG_DIR}")
    print(f"BLIF: {CONV_BLIF_DIR}")


if __name__ == "__main__":
    main()
