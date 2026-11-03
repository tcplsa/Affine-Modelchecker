#!/usr/bin/env python3
"""
oski15a14b 系列差异分析工具
============================
对比 correct (PIC3 判对) 和 mismatch (PIC3 判错) 之间的 AAG 差异，
定位哪些 AND 门导致 PDR bug 被触发。

用法:
  python3 analyze_oski.py --diff        # 对比所有案例的 AAG 差异
  python3 analyze_oski.py --bisect      # 二分法定位触发 bug 的门
  python3 analyze_oski.py --summary     # 打印汇总
"""

import argparse, subprocess, sys, tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
BLIF_DIR = ROOT / "blif"
AIGTOAIG = str(BLIF_DIR / "aigtoaig")
HWMCC = ROOT / "test_tools" / "hwmcc2015" / "data"

sys.path.insert(0, str(BLIF_DIR))

# ---- 数据定义 ----

# oski15a14b 系列全部案例及已知结果
OSKI_CASES = {
    # mismatch: PIC3 错误地判 SAFE (MC 判 UNSAFE)
    "b01s": {"mc": "UNSAFE", "pic3": "SAFE",   "group": "mismatch"},
    "b09s": {"mc": "UNSAFE", "pic3": "SAFE",   "group": "mismatch"},
    "b13s": {"mc": "UNSAFE", "pic3": "SAFE",   "group": "mismatch"},
    "b15s": {"mc": "UNSAFE", "pic3": "SAFE",   "group": "mismatch"},
    "b31s": {"mc": "UNSAFE", "pic3": "SAFE",   "group": "mismatch"},
    # correct: 两边一致
    "b07s": {"mc": "UNSAFE", "pic3": "UNSAFE", "group": "correct_unsafe"},
    "b11s": {"mc": "UNSAFE", "pic3": "UNSAFE", "group": "correct_unsafe"},
    "b12s": {"mc": "SAFE",   "pic3": "SAFE",   "group": "correct_safe"},
    "b14s": {"mc": "SAFE",   "pic3": "SAFE",   "group": "correct_safe"},
    "b16s": {"mc": "SAFE",   "pic3": "SAFE",   "group": "correct_safe"},
    "b18s": {"mc": "SAFE",   "pic3": "SAFE",   "group": "correct_safe"},
    # timeout: PIC3 超时
    "b02s": {"mc": "UNSAFE", "pic3": "TIMEOUT", "group": "timeout"},
    "b03s": {"mc": "UNSAFE", "pic3": "TIMEOUT", "group": "timeout"},
    "b04s": {"mc": "UNSAFE", "pic3": "TIMEOUT", "group": "timeout"},
    "b05s": {"mc": "UNSAFE", "pic3": "TIMEOUT", "group": "timeout"},
    "b06s": {"mc": "UNSAFE", "pic3": "TIMEOUT", "group": "timeout"},
    "b08s": {"mc": "SAFE",   "pic3": "TIMEOUT", "group": "timeout"},
    "b10s": {"mc": "UNSAFE", "pic3": "TIMEOUT", "group": "timeout"},
}


def aig_to_aag(name):
    """转换单个 AIG → AAG，返回路径"""
    aig = HWMCC / f"oski15a14{name}.aig"
    aag = Path(f"/tmp/oski_analysis/oski15a14{name}.aag")
    aag.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([AIGTOAIG, str(aig), str(aag)],
                   check=True, capture_output=True)
    return aag


def read_aag_structured(path):
    """读取 AAG 并返回结构化数据"""
    from extractxor import read_aag
    M, inputs, outputs, latches, and_gates, bad, constr = read_aag(str(path))
    # and_gates: list of (out_var, lhs, rhs) where out_var = node id
    return {
        "M": M, "I": len(inputs), "L": len(latches),
        "O": len(outputs), "A": len(and_gates), "B": len(bad), "C": len(constr),
        "inputs": inputs, "outputs": outputs,
        "latches": latches, "and_gates": and_gates,
        "bad": bad, "constraints": constr,
    }


def and_gate_signature(gate):
    """返回 AND 门的签名: (lhs, rhs) 排序后的 tuple（忽略输出节点编号）"""
    out, lhs, rhs = gate
    return tuple(sorted([lhs, rhs]))


def diff_cases(name_a, name_b):
    """对比两个案例的 AND 门差异"""
    aag_a = aig_to_aag(name_a)
    aag_b = aig_to_aag(name_b)
    data_a = read_aag_structured(aag_a)
    data_b = read_aag_structured(aag_b)

    print(f"\n{'='*60}")
    print(f"Diff: oski15a14{name_a} (M={data_a['M']}, A={data_a['A']})")
    print(f"  vs  oski15a14{name_b} (M={data_b['M']}, A={data_b['A']})")

    sigs_a = {and_gate_signature(g) for g in data_a["and_gates"]}
    sigs_b = {and_gate_signature(g) for g in data_b["and_gates"]}

    only_a = sigs_a - sigs_b
    only_b = sigs_b - sigs_a

    print(f"  Only in {name_a}: {len(only_a)} gates")
    for sig in sorted(only_a)[:10]:
        print(f"    {sig}")

    print(f"  Only in {name_b}: {len(only_b)} gates")
    for sig in sorted(only_b)[:10]:
        print(f"    {sig}")

    return {"only_a": only_a, "only_b": only_b, "common": sigs_a & sigs_b}


def compare_groups():
    """对比 mismatch 组和 correct_unsafe 组"""
    print("=" * 60)
    print("GROUP COMPARISON: mismatch vs correct_unsafe")
    print("=" * 60)

    mismatch_cases = [k for k, v in OSKI_CASES.items() if v["group"] == "mismatch"]
    correct_cases = [k for k, v in OSKI_CASES.items() if v["group"] == "correct_unsafe"]

    for mc_case in mismatch_cases:
        for cc_case in correct_cases:
            diff_cases(mc_case, cc_case)


def summary():
    """打印所有 oski15a14b 案例的汇总"""
    print(f"{'Case':<8} {'Group':<16} {'M':>6} {'I':>5} {'L':>5} {'O':>3} {'A':>6} {'B':>3} {'MC':>8} {'PIC3':>8}")
    print("-" * 80)
    for name in sorted(OSKI_CASES.keys()):
        info = OSKI_CASES[name]
        try:
            aag = aig_to_aag(name)
            d = read_aag_structured(aag)
            print(f"b{name:<7} {info['group']:<16} {d['M']:>6} {d['I']:>5} {d['L']:>5} "
                  f"{d['O']:>3} {d['A']:>6} {d['B']:>3} {info['mc']:>8} {info['pic3']:>8}")
        except Exception as e:
            print(f"b{name:<7} {info['group']:<16} {'ERR':>6}  {e}")


def main():
    parser = argparse.ArgumentParser(description="oski15a14b 系列差异分析")
    parser.add_argument("--summary", action="store_true", help="打印汇总表")
    parser.add_argument("--diff", nargs=2, metavar=("CASE_A", "CASE_B"),
                        help="对比两个案例，如 b01s b07s")
    parser.add_argument("--groups", action="store_true", help="对比 mismatch 组 vs correct 组")
    args = parser.parse_args()

    if args.summary or (not args.diff and not args.groups):
        summary()

    if args.groups:
        compare_groups()

    if args.diff:
        diff_cases(args.diff[0], args.diff[1])


if __name__ == "__main__":
    main()
