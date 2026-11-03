#!/usr/bin/env python3
"""
PIC3 差分模糊测试驱动脚本
============================
对 HWMCC 基准做语义保留变异后，用 MC（Oracle）和 PIC3 同时验证，
发现结果不一致即为潜在 bug。

工作流程:
  1. 从 HWMCC 数据集中选取测试用例（可指定金丝雀集或全量）
  2. 对每个 AIG 生成若干变异版本
  3. 对原始 AIG 和每个变异版本分别运行 MC 和 PIC3
  4. 比较结果，报告 mismatch
"""

import argparse, concurrent.futures, os, subprocess, sys, tempfile, time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent  # compare/ → test_tools/ → wudl/
BLIF_DIR = ROOT / "blif"
MODELCHECKER_BIN = ROOT / "Modelchecker-xag" / "modelchecker" / "modelchecker"
MAINBLIF = BLIF_DIR / "mainblif.py"
AIGTOAIG = BLIF_DIR / "aigtoaig"
HWMCC_DATA = ROOT / "test_tools" / "hwmcc2015" / "data"
FUZZ_RESULTS = SCRIPT_DIR / "results" / "fuzz"

# 金丝雀集：已知敏感的 benchmark
CANARY_SET = [
    "oski15a14b01s",   # mismatch: PIC3=SAFE, MC=UNSAFE
    "oski15a14b13s",   # mismatch
    "oski15a14b15s",   # mismatch
    "oski15a14b31s",   # mismatch
    "oski15a14b09s",   # mismatch
    "oski15a14b07s",   # both UNSAFE (OK, was correct)
    "oski15a14b12s",   # both SAFE (OK)
    "bobcohdoptdcd4",  # PIC3 timeout, MC=SAFE=26s
    "power2eq2048",    # PIC3 timeout, MC=SAFE
    "shift1add2048",   # PIC3 faster (3.5s vs 391s)
    "6s317b14",        # PIC3 faster (2.7s vs 321s)
    "pj2015",          # PIC3 faster (255s vs 1390s)
]

sys.path.insert(0, str(BLIF_DIR))


def convert_aig_to_aag(aig_path: str, aag_path: str) -> bool:
    """AIG → AAG"""
    try:
        subprocess.run([str(AIGTOAIG), aig_path, aag_path],
                       check=True, capture_output=True, timeout=120)
        return True
    except Exception:
        return False


def convert_aag_to_blif(aag_path: str, blif_path: str) -> bool:
    """AAG → BLIF"""
    try:
        from extractxor import read_aag, build_netlist, extract_xors, write_blif
        M, inputs, outputs, latches, and_gates, bad_outputs, constraint_outputs = read_aag(aag_path)
        nodes, and_ids = build_netlist(M, inputs, outputs, latches, and_gates, bad_outputs, constraint_outputs)
        extract_xors(nodes, and_ids)
        write_blif(nodes, inputs, outputs, latches, M, and_ids, str(blif_path),
                   bad_outputs, constraint_outputs)
        return True
    except Exception:
        return False


def run_mc(aig_path: str, timeout: int) -> tuple:
    """运行 MC，返回 (status, elapsed)"""
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [str(MODELCHECKER_BIN), "-pdr", "1", aig_path],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(MODELCHECKER_BIN.parent))
        out = proc.stdout.lower() + proc.stderr.lower()
        if "result: unsafe" in out:
            return "UNSAFE", time.perf_counter() - t0
        elif "result: safe" in out or "no output asserted" in out:
            return "SAFE", time.perf_counter() - t0
        else:
            return "UNKNOWN", time.perf_counter() - t0
    except subprocess.TimeoutExpired:
        return "TIMEOUT", time.perf_counter() - t0
    except Exception:
        return "ERROR", time.perf_counter() - t0


def run_pic3(blif_path: str, timeout: int) -> tuple:
    """运行 PIC3，返回 (status, elapsed)"""
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, str(MAINBLIF), "--parallel", "1", blif_path],
            capture_output=True, text=True, timeout=timeout)
        out = proc.stdout.lower() + proc.stderr.lower()
        if "the design is unsafe" in out:
            return "UNSAFE", time.perf_counter() - t0
        elif "the design is safe" in out:
            return "SAFE", time.perf_counter() - t0
        else:
            return "UNKNOWN", time.perf_counter() - t0
    except subprocess.TimeoutExpired:
        return "TIMEOUT", time.perf_counter() - t0
    except Exception:
        return "ERROR", time.perf_counter() - t0


def fuzz_one(aig_path, seed, num_variants, mc_timeout, pic3_timeout, work_dir, mutators):
    """对单个 AIG 进行模糊测试"""
    name = aig_path.stem
    results = []

    # 原始用例测试
    aag_path = work_dir / f"{name}.aag"
    blif_path = work_dir / f"{name}.blif"

    if not convert_aig_to_aag(str(aig_path), str(aag_path)):
        return [{"name": name, "variant": "original", "mc": "SKIP", "pic3": "SKIP", "note": "aig→aag failed"}]

    if not convert_aag_to_blif(str(aag_path), str(blif_path)):
        return [{"name": name, "variant": "original", "mc": "SKIP", "pic3": "SKIP", "note": "aag→blif failed"}]

    mc_s, mc_t = run_mc(str(aig_path), mc_timeout)
    pic3_s, pic3_t = run_pic3(str(blif_path), pic3_timeout)
    match = "OK" if mc_s == pic3_s else "MISMATCH"
    results.append({
        "name": name, "variant": "original",
        "mc": mc_s, "mc_time": f"{mc_t:.2f}",
        "pic3": pic3_s, "pic3_time": f"{pic3_t:.2f}",
        "match": match
    })

    # 变异版本测试
    from fuzz_mutate import mutate_aag, MUTATORS
    avail = [(n, f) for n, f in MUTATORS if n in mutators]
    rng = __import__('random').Random(seed)

    for vi in range(num_variants):
        var_name = f"{name}_m{vi}"
        var_aag = work_dir / f"{var_name}.aag"
        var_blif = work_dir / f"{var_name}.blif"

        try:
            applied = mutate_aag(str(aag_path), str(var_aag), seed + vi, avail)
        except Exception:
            continue

        if not convert_aag_to_blif(str(var_aag), str(var_blif)):
            continue

        # 变异后的 AIG 也用 MC 跑
        mc_s, mc_t = run_mc(str(var_aag), mc_timeout)
        pic3_s, pic3_t = run_pic3(str(var_blif), pic3_timeout)
        match = "OK" if mc_s == pic3_s else "MISMATCH"
        results.append({
            "name": name, "variant": f"mutation_{vi}",
            "mutations": ",".join(applied),
            "mc": mc_s, "mc_time": f"{mc_t:.2f}",
            "pic3": pic3_s, "pic3_time": f"{pic3_t:.2f}",
            "match": match
        })

    return results


def main():
    parser = argparse.ArgumentParser(description="PIC3 差分模糊测试")
    parser.add_argument("--canary", action="store_true", help="仅测试金丝雀集")
    parser.add_argument("--benchmarks", nargs="+", help="指定测试的 benchmark 名称")
    parser.add_argument("--variants", type=int, default=3, help="每个用例的变异数")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--mc-timeout", type=int, default=120, help="MC 超时（秒）")
    parser.add_argument("--pic3-timeout", type=int, default=300, help="PIC3 超时（秒）")
    parser.add_argument("--workers", type=int, default=2, help="并行数")
    parser.add_argument("--mutators", nargs="+",
                        default=["swap_and_inputs", "add_redundant_and", "insert_buf_chain"],
                        help="使用的变异器")
    args = parser.parse_args()

    FUZZ_RESULTS.mkdir(parents=True, exist_ok=True)

    # 选择测试集
    if args.benchmarks:
        names = args.benchmarks
    elif args.canary:
        names = CANARY_SET
    else:
        names = [p.stem for p in sorted(HWMCC_DATA.glob("*.aig"))][:50]  # 默认前50个

    aig_files = []
    for n in names:
        p = HWMCC_DATA / f"{n}.aig"
        if p.exists():
            aig_files.append(p)

    print(f"Testing {len(aig_files)} benchmarks, {args.variants} variants each")
    print(f"MC timeout={args.mc_timeout}s, PIC3 timeout={args.pic3_timeout}s")
    print()

    all_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        work_dir = FUZZ_RESULTS / f"run_{int(time.time())}"
        work_dir.mkdir(parents=True, exist_ok=True)
        futures = {}
        for p in aig_files:
            f = ex.submit(fuzz_one, p, args.seed, args.variants,
                          args.mc_timeout, args.pic3_timeout,
                          work_dir, args.mutators)
            futures[f] = p

        for fut in concurrent.futures.as_completed(futures):
            p = futures[fut]
            try:
                res = fut.result()
                all_results.extend(res)
            except Exception as e:
                print(f"  ERROR {p.stem}: {e}")

    # 统计
    mismatch_count = sum(1 for r in all_results if r["match"] == "MISMATCH")
    ok_count = sum(1 for r in all_results if r["match"] == "OK")

    print()
    print("=" * 60)
    print(f"Results: {len(all_results)} tests, {ok_count} OK, {mismatch_count} MISMATCH")
    if mismatch_count > 0:
        print()
        print("MISMATCHES:")
        for r in all_results:
            if r["match"] == "MISMATCH":
                print(f"  {r['name']} [{r['variant']}]  MC={r['mc']}  PIC3={r['pic3']}")
    print()


if __name__ == "__main__":
    main()
