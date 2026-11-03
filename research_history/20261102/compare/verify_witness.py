#!/usr/bin/env python3
"""
验证 modelchecker 产出的 witness (反例路径) 是否正确。

读取 AAG 文件 + modelchecker 的 witness 输出，逐步仿真电路，
检查从初态出发，按 witness 给出的输入序列，是否真的能到达 bad 状态。

用法：
  python verify_witness.py <aag_file> [witness_file]
  - 若不指定 witness_file，直接从 stdin 读取模型检查器的输出
"""

import sys
import os

def parse_aag(filepath):
    """解析 AAG 文件，返回电路结构"""
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    # 去掉注释和空行
    lines = [l.strip() for l in lines if l.strip() and not l.strip().startswith('c')]
    
    # 解析头部: aag M I L O A
    header = lines[0].split()
    assert header[0] == 'aag', f"不是 AAG 格式: {header[0]}"
    M = int(header[1])
    I = int(header[2])
    L = int(header[3])
    O = int(header[4])
    A = int(header[5])
    
    # 解析可选的 bad/constraint/justice/fairness 数量
    idx = 1
    num_bads = 0
    num_constraints = 0
    if len(header) > 6:
        num_bads = int(header[6])
    if len(header) > 7:
        num_constraints = int(header[7])
    
    # 输入: I 行 (每行一个数值)
    inputs = []
    for i in range(I):
        lit = int(lines[idx])
        idx += 1
        inputs.append(lit)
    
    # 锁存器: L 行，每行: latch_lit next_lit [default_val]
    latches = []
    for i in range(L):
        parts = lines[idx].split()
        idx += 1
        latch_lit = int(parts[0])
        next_lit = int(parts[1])
        default_val = 0
        if len(parts) >= 3:
            default_val = int(parts[2])
        latches.append({
            'latch': latch_lit,
            'next': next_lit,
            'default': default_val
        })
    
    # 输出: O 行
    outputs = []
    for i in range(O):
        lit = int(lines[idx])
        idx += 1
        outputs.append(lit)
    
    # Bad states (可选): num_bads 行
    bads = []
    for i in range(num_bads):
        lit = int(lines[idx])
        idx += 1
        bads.append(lit)
    
    # 约束 (可选): num_constraints 行
    constraints = []
    for i in range(num_constraints):
        lit = int(lines[idx])
        idx += 1
        constraints.append(lit)
    
    # AND 门: A 行, 每行: output_lit input1_lit input2_lit
    and_gates = []
    for i in range(A):
        parts = lines[idx].split()
        idx += 1
        o = int(parts[0])
        i1 = int(parts[1])
        i2 = int(parts[2])
        and_gates.append({'o': o, 'i1': i1, 'i2': i2})
    
    # 符号表 (可选): 跳过，直到文件末尾
    # (不需要解析符号)
    
    return {
        'M': M, 'I': I, 'L': L, 'O': O, 'A': A,
        'inputs': inputs,
        'latches': latches,
        'outputs': outputs,
        'bads': bads,
        'constraints': constraints,
        'and_gates': and_gates,
        'num_bads': num_bads,
        'num_constraints': num_constraints,
    }


def parse_witness(witness_text, I, L):
    """
    解析 modelchecker 的 witness 输出。
    返回: (init_latches, input_sequence)
      init_latches: list of bool, 长度 L
      input_sequence: list of list of bool, 每个长度 I, 每帧一个
    """
    lines = [l.strip() for l in witness_text.strip().split('\n') if l.strip()]
    
    # 过滤掉非 witness 行（Warning, result 等）
    witness_lines = []
    in_witness = False
    for line in lines:
        if line == '1':
            in_witness = True
        if not in_witness:
            continue
        if line.startswith('result:') or line.startswith('Warning:'):
            break
        witness_lines.append(line)
    
    # 第一行应为 "1" (表示有 witness)
    if witness_lines[0] == '1':
        witness_lines = witness_lines[1:]
    
    # 第二行 "b0" (bad state index)
    if witness_lines[0].startswith('b'):
        witness_lines = witness_lines[1:]
    
    # 接下来是初始锁存器值: L 个字符 (可能跨多行)
    all_chars = []
    while len(all_chars) < L and witness_lines:
        line = witness_lines[0]
        witness_lines = witness_lines[1:]
        if line == '.':
            break
        # 只取 0/1 字符
        chars = [c for c in line if c in '01']
        all_chars.extend(chars)
    
    if len(all_chars) < L:
        raise ValueError(f"初始锁存器值不足: 需要 {L}, 得到 {len(all_chars)}")
    
    init_latches = [c == '1' for c in all_chars[:L]]
    remaining = all_chars[L:]  # 可能和输入混在一起的第一行
    
    # 读取输入序列: 每 I 个字符为一帧
    all_input_chars = list(remaining)
    while witness_lines:
        line = witness_lines[0]
        witness_lines = witness_lines[1:]
        if line == '.':
            break
        chars = [c for c in line if c in '01']
        all_input_chars.extend(chars)
    
    if len(all_input_chars) % I != 0:
        raise ValueError(f"输入字符数 {len(all_input_chars)} 不是 I={I} 的倍数")
    
    num_frames = len(all_input_chars) // I
    input_sequence = []
    for f in range(num_frames):
        frame_inputs = [c == '1' for c in all_input_chars[f*I:(f+1)*I]]
        input_sequence.append(frame_inputs)
    
    return init_latches, input_sequence


def aig_lit_to_var(lit):
    """AIG literal -> (var_index, polarity)
    var_index: 从 0 开始 (对应 AIG 变量 2)
    polarity: True 表示正相, False 表示反相
    """
    if lit == 0:
        return None, False  # constant false
    if lit == 1:
        return None, True   # constant true
    var = (lit >> 1) - 1    # lit=2 -> var=0, lit=4 -> var=1, ...
    polarity = (lit & 1) == 0  # even = positive
    return var, polarity


def eval_lit(lit, var_values):
    """计算 AIG literal 的布尔值"""
    if lit == 0:
        return False
    if lit == 1:
        return True
    var = (lit >> 1) - 1
    val = var_values[var]
    if lit & 1:  # odd = negated
        return not val
    return val


def simulate(aag, init_latches, input_sequence, verbose=True):
    """
    仿真电路，检查 witness 路径是否有效。
    返回: (is_valid, trace_info)
    """
    I = aag['I']
    L = aag['L']
    A = aag['A']
    latches = aag['latches']
    and_gates = aag['and_gates']
    
    # 确定 bad literal
    if aag['bads']:
        bad_lit = aag['bads'][0]
    else:
        bad_lit = aag['outputs'][0]
    
    total_vars = I + L + A  # 总变量数
    
    # 当前锁存器值
    current_latches = list(init_latches)
    
    trace_info = []
    
    for frame_idx, inputs in enumerate(input_sequence):
        # 构建当前变量值数组
        var_values = [False] * total_vars
        
        # 设置输入值
        for i in range(I):
            var_values[i] = inputs[i]
        
        # 设置锁存器值
        for l in range(L):
            var_values[I + l] = current_latches[l]
        
        # 按顺序计算 AND 门 (AIG 保证拓扑排序)
        for g_idx, gate in enumerate(and_gates):
            v1 = eval_lit(gate['i1'], var_values)
            v2 = eval_lit(gate['i2'], var_values)
            and_result = v1 and v2
            
            o_var, o_pol = aig_lit_to_var(gate['o'])
            # 存储到变量 (AND 门输出变量)
            # 注意: gate['o'] 可能带极性; AND 结果存到无极性变量
            # 如果 o 是奇数，则实际变量值为 NOT(and_result)
            var_values[o_var] = and_result if o_pol else (not and_result)
        
        # 检查 bad 状态
        bad_val = eval_lit(bad_lit, var_values)
        
        # 检查约束 (如果有)
        constraints_satisfied = True
        for cst in aag['constraints']:
            if not eval_lit(cst, var_values):
                constraints_satisfied = False
                break
        
        # 计算下一帧的锁存器值
        next_latches = [False] * L
        for l_idx, latch_info in enumerate(latches):
            next_val = eval_lit(latch_info['next'], var_values)
            next_latches[l_idx] = next_val
        
        trace_info.append({
            'frame': frame_idx,
            'bad': bad_val,
            'constraints_ok': constraints_satisfied,
            'current_latches': list(current_latches),
            'inputs': list(inputs),
            'next_latches': list(next_latches),
        })
        
        if verbose:
            print(f"\n--- Frame {frame_idx} ---")
            print(f"  latches (first 20): {''.join('1' if b else '0' for b in current_latches[:20])}...")
            print(f"  inputs  (first 20): {''.join('1' if b else '0' for b in inputs[:20])}...")
            print(f"  bad = {bad_val}, constraints_ok = {constraints_satisfied}")
            print(f"  next latches (first 20): {''.join('1' if b else '0' for b in next_latches[:20])}...")
        
        if bad_val and constraints_satisfied:
            if verbose:
                print(f"\n✓ Bad state reached at frame {frame_idx}!")
            return True, trace_info, frame_idx
        
        # 更新锁存器
        current_latches = next_latches
    
    if verbose:
        print(f"\n✗ Bad state NOT reached after {len(input_sequence)} frames.")
    
    return False, trace_info, -1


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    aag_path = sys.argv[1]
    
    if len(sys.argv) >= 3:
        witness_path = sys.argv[2]
        with open(witness_path, 'r') as f:
            witness_text = f.read()
    else:
        witness_text = sys.stdin.read()
    
    print(f"解析 AAG 文件: {aag_path}")
    aag = parse_aag(aag_path)
    print(f"  输入: {aag['I']}, 锁存器: {aag['L']}, 输出: {aag['O']}, AND门: {aag['A']}")
    print(f"  Bad states数量: {aag['num_bads']}, 约束数量: {aag['num_constraints']}")
    
    # 显示 bad literal
    if aag['bads']:
        bad_lit = aag['bads'][0]
    else:
        bad_lit = aag['outputs'][0]
    print(f"  Bad literal: {bad_lit}")
    
    # 显示初始状态信息
    print(f"\n锁存器默认值 (前20):")
    for i, latch in enumerate(aag['latches'][:20]):
        print(f"  latch{i}: default={latch['default']}, next_lit={latch['next']}")
    
    print(f"\n解析 witness...")
    init_latches, input_sequence = parse_witness(witness_text, aag['I'], aag['L'])
    print(f"  初始锁存器 (前20): {''.join('1' if b else '0' for b in init_latches[:20])}...")
    print(f"  输入帧数: {len(input_sequence)}")
    
    print(f"\n开始仿真验证...")
    is_valid, trace, bad_frame = simulate(aag, init_latches, input_sequence, verbose=True)
    
    print(f"\n{'='*60}")
    if is_valid:
        print(f"结论: witness 路径有效! Bad 状态在第 {bad_frame} 帧到达。")
    else:
        print(f"结论: witness 路径无效! 沿此输入序列无法到达 bad 状态。")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
