#!/usr/bin/env python3
"""
PDR 执行轨迹对比工具
=====================
注入调试钩子到 PDRblif.py，捕获关键函数的调用序列和内部状态，
然后对比 b07s（正确）和 b13s（错误）的执行轨迹差异。

用法:
  python3 trace_pdr.py --correct b07s --wrong b13s --timeout 600
"""

import argparse, os, re, subprocess, sys, tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
BLIF_DIR = ROOT / "blif"
AIGTOAIG = str(BLIF_DIR / "aigtoaig")
HWMCC = ROOT / "test_tools" / "hwmcc2015" / "data"
MAINBLIF = BLIF_DIR / "mainblif.py"
PDRBLIF = BLIF_DIR / "PDRblif.py"

sys.path.insert(0, str(BLIF_DIR))

# PDRblif.py 的副本路径（注入调试钩子用）
PDR_INSTRUMENTED = Path("/tmp/PDRblif_debug.py")


def instrument_pdr():
    """复制 PDRblif.py 并在关键函数中注入调试打印"""
    src = PDRBLIF.read_text()

    # 1. 在 get_pre_of_bad 中注入
    src = src.replace(
        'res = frames[Fk].solver.solve(False)',
        'res = frames[Fk].solver.solve(False)\n'
        '    print(f"[TRACE] get_pre_of_bad: depth={depth()}, SAT={res==1}")'
    )

    # 2. 在 rec_block_cube 每轮迭代中注入
    src = src.replace(
        'if show_block_info:\n'
        '            print("obligation_queue size:", len(obligation_queue))',
        'if True:\n'
        '            print(f"[TRACE] rec_block_cube iter={cnt}: queue={len(obligation_queue)}, '
        'obl.frame_k={obl.frame_k}, obl.depth={obl.depth}, obl.failed={obl.state.failed}")'
    )

    # 3. 在 obligation 被丢弃时注入
    src = src.replace(
        'obl.state.failed_depth = obl.depth + obl.frame_k\n'
        '                # 传递失败深度给下一个状态\n'
        '                if obl.state.next is not None:\n'
        '                    obl.state.next.failed_depth = obl.state.failed_depth\n'
        '                continue  # 继续处理下一个义务',
        'obl.state.failed_depth = obl.depth + obl.frame_k\n'
        '                print(f"[TRACE] DROP obl due to failed>=5: frame_k={obl.frame_k}, depth={obl.depth}, '
        'depth()={depth()}, failed_depth={obl.state.failed_depth}")\n'
        '                if obl.state.next is not None:\n'
        '                    obl.state.next.failed_depth = obl.state.failed_depth\n'
        '                continue'
    )

    # 4. 在 propagate 中注入（帧清空检测）
    src = src.replace(
        'if len(frames[i].cubes) == 0:\n'
        '            if len(frames[i].cubes) == 0:',
        'print(f"[TRACE] propagate: frame {i} emptied (cubes=0), depth={depth()}")\n'
        '            if len(frames[i].cubes) == 0:\n'
        '            if len(frames[i].cubes) == 0:'
    )

    # 5. 在 add_cube 中注入（记录每次 cube 添加）
    src = src.replace(
        'cube_tuple = tuple(cube)\n'
        '    if cube_tuple in frames[k].cubes:\n'
        '        return',
        'cube_tuple = tuple(cube)\n'
        '    print(f"[TRACE] add_cube: k={k}, sz={len(cube)}, to_all={to_all}, isprop={ispropagate}")\n'
        '    if cube_tuple in frames[k].cubes:\n'
        '        print(f"[TRACE] add_cube: DUPLICATE, skipped")\n'
        '        return'
    )

    # 6. 在 generalize 中注入
    src = src.replace(
        'def generalize(cube, k, depth):',
        'def generalize(cube, k, depth):\n'
        '    print(f"[TRACE] generalize: k={k}, depth={depth}, sz={len(cube)}")'
    )

    # 7. 在 CTG_down 中注入
    src = src.replace(
        'def CTG_down(cube, k, rec_depth, required):',
        'def CTG_down(cube, k, rec_depth, required):\n'
        '    print(f"[TRACE] CTG_down: k={k}, rec_depth={rec_depth}, sz={len(cube)}")'
    )

    PDR_INSTRUMENTED.write_text(src)
    print(f"Instrumented PDR written to {PDR_INSTRUMENTED}")


def run_instrumented_pic3(name, timeout):
    """运行注入了调试钩子的 PIC3"""
    aig = HWMCC / f"oski15a14{name}.aig"
    aag = Path(f"/tmp/pdr_trace/{name}.aag")
    blif = Path(f"/tmp/pdr_trace/{name}.blif")
    log = Path(f"/tmp/pdr_trace/{name}_trace.log")
    aag.parent.mkdir(parents=True, exist_ok=True)

    # AIG → AAG → BLIF
    subprocess.run([AIGTOAIG, str(aig), str(aag)], check=True, capture_output=True)

    from extractxor import read_aag, build_netlist, extract_xors, write_blif
    M, inputs, outputs, latches, gates, bad, constr = read_aag(str(aag))
    nodes, and_ids = build_netlist(M, inputs, outputs, latches, gates, bad, constr)
    extract_xors(nodes, and_ids)
    write_blif(nodes, inputs, outputs, latches, M, and_ids, str(blif), bad, constr)

    # 复制 mainblif.py 临时版本，让它 import 注入版 PDR
    mainblif_src = MAINBLIF.read_text()

    # 用注入版替换原始 import
    tmp_main = Path(f"/tmp/pdr_trace/mainblif_{name}.py")
    # 在 mainblif.py 中，PDRblif 是通过 from PDRblif import * 或类似方式导入的
    # 我们需要修改 sys.path 让注入版被先找到
    wrapper = f'''
import sys, os
sys.path.insert(0, "/tmp")
os.chdir("{BLIF_DIR}")

# 把注入版 PDRblif 作为模块加载
import importlib.util
spec = importlib.util.spec_from_file_location("PDRblif", "{PDR_INSTRUMENTED}")
pdr_module = importlib.util.module_from_spec(spec)
sys.modules["PDRblif"] = pdr_module
spec.loader.exec_module(pdr_module)

# 把所有 PDRblif 的符号注入到 mainblif 的全局命名空间
# mainblif.py 使用 from PDRblif import * 或类似
{mainblif_src.replace("from PDRblif import", "# patched: from PDRblif import")}
'''
    tmp_main.write_text(wrapper)

    print(f"Running PIC3 on {name} with instrumented PDR (timeout={timeout}s)...")
    try:
        with open(log, 'w') as lf:
            proc = subprocess.run(
                [sys.executable, str(tmp_main), "--parallel", "1", str(blif)],
                stdout=lf, stderr=subprocess.STDOUT, timeout=timeout)
        print(f"  {name}: done, log={log}")
    except subprocess.TimeoutExpired:
        print(f"  {name}: TIMEOUT")
    return log


def parse_trace(log_path):
    """从日志中提取 [TRACE] 行"""
    if not log_path.exists():
        return []
    traces = []
    with open(log_path) as f:
        for line in f:
            if "[TRACE]" in line:
                traces.append(line.strip())
    return traces


def diff_traces(trace_a, trace_b, name_a, name_b):
    """对比两条执行轨迹"""
    print(f"\n{'='*70}")
    print(f"Trace comparison: {name_a} vs {name_b}")
    print(f"  {name_a}: {len(trace_a)} trace events")
    print(f"  {name_b}: {len(trace_b)} trace events")
    print(f"{'='*70}")

    max_len = max(len(trace_a), len(trace_b))
    divergence = None

    for i in range(max_len):
        la = trace_a[i] if i < len(trace_a) else "<END>"
        lb = trace_b[i] if i < len(trace_b) else "<END>"

        if la != lb and divergence is None:
            divergence = i
            print(f"\n>>> DIVERGENCE at event {i}:")
            print(f"  {name_a}: {la}")
            print(f"  {name_b}: {lb}")
        elif la != lb:
            print(f"  diff[{i}]:")
            print(f"    {name_a}: {la[:120]}")
            print(f"    {name_b}: {lb[:120]}")

    if divergence is None:
        print("\nTraces are identical up to min length.")

    return divergence


def main():
    parser = argparse.ArgumentParser(description="PDR 执行轨迹对比")
    parser.add_argument("--correct", default="b07s", help="正确的案例")
    parser.add_argument("--wrong", default="b13s", help="错误的案例")
    parser.add_argument("--timeout", type=int, default=900, help="每个案例超时秒数")
    parser.add_argument("--instrument-only", action="store_true",
                        help="只生成注入版 PDRblif.py，不运行")
    args = parser.parse_args()

    instrument_pdr()

    if args.instrument_only:
        print(f"\n注入版 PDR: {PDR_INSTRUMENTED}")
        print(f"手动运行: python3 mainblif.py --parallel 1 <blif_file>")
        return

    # 运行两个案例
    print(f"\nRunning correct case: oski15a14{args.correct}")
    log_correct = run_instrumented_pic3(args.correct, args.timeout)

    print(f"\nRunning wrong case: oski15a14{args.wrong}")
    log_wrong = run_instrumented_pic3(args.wrong, args.timeout)

    # 解析并对比
    trace_correct = parse_trace(log_correct)
    trace_wrong = parse_trace(log_wrong)

    div = diff_traces(trace_correct, trace_wrong, args.correct, args.wrong)

    if div is not None:
        print(f"\n{'='*70}")
        print("ACTION: 在 PDRblif.py 中找到分歧点对应的函数。")
        print(f"分歧事件: {trace_correct[div] if div < len(trace_correct) else trace_wrong[div]}")
        print(f"从此处开始，{args.wrong} 的执行路径偏离了 {args.correct}。")
    else:
        print("\n轨迹完全一致——说明 bug 不在追踪的步骤中，")
        print("尝试增加更多 [TRACE] 钩子到其他关键函数。")


if __name__ == "__main__":
    main()
