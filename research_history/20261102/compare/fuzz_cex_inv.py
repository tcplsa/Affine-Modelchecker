#!/usr/bin/env python3
"""
反例（CEX）与不变式（Invariant）交叉验证器
==========================================
对 PIC3 的输出做独立验证，不依赖 PIC3 自身的 SAT solver。

功能:
  1. 反例链验证：确认 PIC3 输出的 UNSAFE 反例确实从 init 可达 bad
  2. 不变式验证：用独立 SAT solver 验证 PIC3 的归纳不变式

用法:
  # 验证 PIC3 日志中的反例
  python3 fuzz_cex_inv.py --verify-cex --log pic3_logs/case.log --blif conversion/blif/case.blif

  # 验证 PIC3 的不变式（需 PIC3 输出 cubes）
  python3 fuzz_cex_inv.py --verify-inv --blif conversion/blif/case.blif
"""

import argparse, re, subprocess, sys, time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
BLIF_DIR = ROOT / "blif"
sys.path.insert(0, str(BLIF_DIR))


# ====== 反例链验证 ======

def parse_pic3_cex_from_log(log_path: str):
    """从 PIC3 日志中解析反例链。
    反例格式（PDRblif.py 输出的 show_state）:
      [01101010|0011...]
    其中 '[' 前为输入，'|' 后为 latch 值。
    """
    states = []
    with open(log_path) as f:
        content = f.read()

    # 匹配 show_state 输出的状态行
    pattern = r'\[([01x]+)\|([01x]+)\]'
    matches = re.findall(pattern, content)
    for inp, lat in matches:
        states.append({"inputs": inp, "latches": lat})
    return states


def load_blif_structure(blif_path: str):
    """加载 BLIF 结构信息"""
    from blif_input import parse_blif_core
    from blif_output import BLIFParserResult, resolve_blif_relations
    core = parse_blif_core(blif_path)
    result = BLIFParserResult()
    result.inputs = core[0]
    result.outputs = core[1]
    result.names_blocks = [(ni, no, rows) for ni, no, rows in core[2]]
    result.latches = core[3]
    result.neg_pairs = core[4]
    result.eq_pairs = core[5]
    resolve_blif_relations(result)
    return result


def verify_cex_chain(blif, states):
    """验证反例链: init → t → s1 → t → s2 → ... → bad

    用独立的 SAT solver 对每一步做 SAT check:
      第0步: init(s0) is SAT?
      第i步: trans(si, si+1) is SAT?
      最后步: bad(sn) is SAT?
    """
    from Class import SATSolver

    errors = []
    if len(states) < 1:
        return ["Empty CEX: no states found in log"]

    # 第0步: 初始状态检查
    s0 = states[0]
    solver = SATSolver(backend="minisat")
    init_lits = []
    for li, lo, init_val in blif.latches:
        init_lits.append(lo if init_val == 1 else -lo)
    for lit in init_lits:
        solver.add(lit)
        solver.add(0)
    solver.solve()
    if solver.solve_result != solver.SAT:
        errors.append("Step 0: init condition is UNSAT")

    # Transition steps
    for i in range(len(states) - 1):
        si = states[i]
        sj = states[i + 1]
        # Build transition constraints
        # Simple check: at least the latch values are consistent with some transition
        solver = SATSolver(backend="minisat")
        # This is a simplified check - full check needs transition relation encoding
        errors.append(f"Step {i}→{i+1}: full transition check not yet implemented (need T-relation encoding)")

    # Last step: bad check
    sn = states[-1]
    # Check if bad output is asserted
    solver = SATSolver(backend="minisat")
    if blif.outputs:
        bad_var = blif.outputs[0]
        solver.add(bad_var)
        solver.add(0)
        solver.solve()
        if solver.solve_result != solver.SAT:
            errors.append(f"Final state: bad output not asserted")

    return errors


# ====== 不变式验证 ======

def verify_inductive_invariant(blif, cubes_txt: str):
    """验证归纳不变式的三个条件:
      1. Init → Inv (init_implies_inv)
      2. Inv ∧ T → Inv' (inductive_step)
      3. Inv → ¬Bad (inv_excludes_bad)

    cubes_txt: 每个 cube 一行，用空格分隔的 literal 列表
    """
    from Class import SATSolver

    errors = []
    cubes = []
    for line in cubes_txt.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            cube = [int(x) for x in line.split()]
            cubes.append(cube)
        except ValueError:
            pass

    if not cubes:
        return ["No cubes to verify"]

    solver = SATSolver(backend="minisat")

    # 1. Init → Inv
    solver.clear_act()
    for li, lo, init_val in blif.latches:
        solver.add(lo if init_val == 1 else -lo)
        solver.add(0)
    # ¬Inv: at least one cube is violated
    for cube in cubes:
        for lit in cube:
            solver.add(-lit)  # negate the cube
        solver.add(0)
    res = solver.solve(False)
    if res == 1:  # SAT → exists init that violates Inv
        errors.append("Init → Inv FAILS: found init state not in invariant")

    # 2. Inv → ¬Bad
    solver.clear_act()
    if blif.outputs:
        bad_var = blif.outputs[0]
        for cube in cubes:
            for lit in cube:
                solver.add(-lit)
            solver.add(0)
        solver.add(bad_var)
        solver.add(0)
        res = solver.solve(False)
        if res == 1:  # SAT → bad state in invariant
            errors.append("Inv → ¬Bad FAILS: invariant includes bad state")

    # 3. Inv ∧ T → Inv'
    # Full check needs transition relation - simplified check here
    errors.append("Inv ∧ T → Inv': full check needs transition relation encoding")

    return errors


# ====== 主入口 ======

def main():
    parser = argparse.ArgumentParser(description="CEX/Invariant 交叉验证器")
    parser.add_argument("--verify-cex", action="store_true", help="验证反例链")
    parser.add_argument("--verify-inv", action="store_true", help="验证归纳不变式")
    parser.add_argument("--log", help="PIC3 日志文件路径")
    parser.add_argument("--blif", help="BLIF 文件路径")
    parser.add_argument("--cubes-file", help="Cubes 文件路径（每个 cube 一行）")
    args = parser.parse_args()

    if not args.blif:
        print("Error: --blif is required")
        sys.exit(1)

    if not Path(args.blif).exists():
        print(f"Error: BLIF file not found: {args.blif}")
        sys.exit(1)

    blif = load_blif_structure(args.blif)
    print(f"Loaded BLIF: {len(blif.inputs)} inputs, {len(blif.latches)} latches, "
          f"{len(blif.outputs)} outputs, {len(blif.ands)} ANDs")

    if args.verify_cex:
        if not args.log:
            print("Error: --log required for CEX verification")
            sys.exit(1)
        states = parse_pic3_cex_from_log(args.log)
        print(f"Parsed {len(states)} states from CEX log")
        if not states:
            print("WARNING: No state patterns found in log. "
                  "Ensure PDRblif.py has show_pre_of_bad = True")
        errors = verify_cex_chain(blif, states)
        if errors:
            print(f"CEX VERIFICATION FAILED ({len(errors)} errors):")
            for e in errors:
                print(f"  - {e}")
        else:
            print("CEX VERIFICATION PASSED")

    if args.verify_inv:
        if args.cubes_file:
            cubes_txt = Path(args.cubes_file).read_text()
        else:
            print("Error: --cubes-file required for invariant verification")
            sys.exit(1)
        errors = verify_inductive_invariant(blif, cubes_txt)
        if errors:
            print(f"INVARIANT VERIFICATION FAILED ({len(errors)} errors):")
            for e in errors:
                print(f"  - {e}")
        else:
            print("INVARIANT VERIFICATION PASSED")


if __name__ == "__main__":
    main()
