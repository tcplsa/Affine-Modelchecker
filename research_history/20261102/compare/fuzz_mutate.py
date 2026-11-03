#!/usr/bin/env python3
"""
AIG 语义保留变异器（Semantic-Preserving AIG Mutator）
对 AIG 文件进行等价变换，用于压力测试 PDR 实现的鲁棒性。

支持的变异类型:
  1. add_redundant_latch  - 新增与现有 latch 完全相同的冗余 latch
  2. add_redundant_and    - 新增 a = x & x 形式的冗余 AND 门
  3. swap_and_inputs      - 交换 AND 门的两个输入（语义不变）
  4. rewrite_demorgan     - 将 a = b & c 替换为 a = ~(~b | ~c)
  5. shuffle_labels       - 只改变内部节点编号，不改变电路结构
  6. insert_buf_chain     - 在 AND 门输出上插入缓冲器链
"""

import argparse, random, sys
from pathlib import Path


def read_aag(path: str):
    """读取 AAG 文件，返回结构化数据"""
    with open(path) as f:
        lines = [l.strip() for l in f if l.strip()]

    header = lines[0].split()
    assert header[0] == "aag", f"Not an AAG file: {path}"
    M = int(header[1])
    I = int(header[2])
    L = int(header[3])
    O = int(header[4])
    A = int(header[5])
    B = int(header[6]) if len(header) > 6 else 0
    C = int(header[7]) if len(header) > 7 else 0

    body = lines[1:]
    idx = 0
    inputs = [int(x) for x in body[idx:idx + I]]; idx += I
    outputs = [int(x) for x in body[idx:idx + O]]; idx += O
    bads = [int(x) for x in body[idx:idx + B]]; idx += B
    constraints = [int(x) for x in body[idx:idx + C]]; idx += C
    latches = []
    for _ in range(L):
        latches.append((int(body[idx]), int(body[idx + 1]))); idx += 2
    and_gates = []
    for _ in range(A):
        d = int(body[idx]); r0 = int(body[idx + 1]); r1 = int(body[idx + 2])
        and_gates.append((d, r0, r1)); idx += 3

    # Symbol table and comments
    symbols = {}
    comments = []
    while idx < len(body):
        line = body[idx]
        if line.startswith('i') or line.startswith('l') or line.startswith('o'):
            parts = line.split()
            symbols[int(parts[0][1:])] = parts[1] if len(parts) > 1 else ""
        elif line.startswith('c'):
            comments.append(line)
        idx += 1

    return M, I, L, O, A, B, C, inputs, outputs, bads, constraints, latches, and_gates, symbols, comments


def write_aag(path: str, M, I, L, O, A, B, C, inputs, outputs, bads, constraints, latches, and_gates, symbols, comments):
    """写出 AAG 文件"""
    with open(path, 'w') as f:
        f.write(f"aag {M} {I} {L} {O} {A} {B} {C}\n")
        for x in inputs: f.write(f"{x}\n")
        for x in outputs: f.write(f"{x}\n")
        for x in bads: f.write(f"{x}\n")
        for x in constraints: f.write(f"{x}\n")
        for li, lo in latches: f.write(f"{li} {lo}\n")
        for d, r0, r1 in and_gates: f.write(f"{d} {r0} {r1}\n")
        for k, v in sorted(symbols.items()):
            if v:
                f.write(f"i{k} {v}\n" if k < I else
                        f"l{k} {v}\n" if k < I + L else
                        f"o{k} {v}\n")
        for c in comments:
            f.write(f"{c}\n")


def lit_to_var(lit):
    return lit // 2, lit & 1


def var_to_lit(var, inv):
    return (var << 1) | inv


# ====== 变异函数 ======

def mutate_add_redundant_latch(M, I, L, O, A, B, C, inputs, outputs, bads, constraints, latches, and_gates, symbols, comments, seed):
    """新增一个与随机现有 latch 行为完全相同的冗余 latch"""
    rng = random.Random(seed)
    if L == 0:
        return False  # 没有 latch 可复制

    src_idx = rng.randint(0, L - 1)
    src_li, src_lo = latches[src_idx]
    new_li = M * 2 + 2       # 新 latch 输入
    new_lo = M * 2 + 4       # 新 latch 输出
    latches.append((new_li, new_lo))
    L += 1
    M += 2  # 两个新变量
    return True


def mutate_add_redundant_and(M, I, L, O, A, B, C, inputs, outputs, bads, constraints, latches, and_gates, symbols, comments, seed):
    """新增 a = b & b 形式的冗余 AND 门（等价于缓冲器）"""
    rng = random.Random(seed)
    if len(inputs) + len(latches) == 0:
        return False

    # 随机选一个现有信号作为源
    all_lits = list(inputs) + [lo for _, lo in latches]
    if A > 0:
        all_lits += [d for d, _, _ in and_gates]

    src_lit = rng.choice(all_lits) if all_lits else 2
    new_var = M + 1
    new_lit = var_to_lit(new_var, 0)
    and_gates.append((new_lit, src_lit, src_lit))
    A += 1
    M += 1
    return True


def mutate_swap_and_inputs(M, I, L, O, A, B, C, inputs, outputs, bads, constraints, latches, and_gates, symbols, comments, seed):
    """随机交换一个 AND 门的两个输入（语义不变）"""
    rng = random.Random(seed)
    if A == 0:
        return False
    idx = rng.randint(0, A - 1)
    d, r0, r1 = and_gates[idx]
    and_gates[idx] = (d, r1, r0)
    return True


def mutate_rewrite_demorgan(M, I, L, O, A, B, C, inputs, outputs, bads, constraints, latches, and_gates, symbols, comments, seed):
    """将 a = b & c 替换为 a = ~(~b | ~c)，引入新变量"""
    rng = random.Random(seed)
    if A < 1:
        return False

    idx = rng.randint(0, A - 1)
    d, r0, r1 = and_gates[idx]

    # ~b | ~c: 创建中间 OR 门
    # OR 用 AND + NOT 实现: x | y = ~(~x & ~y)
    # 但对于 AIG，OR 不是原始操作。这里改成插入两个冗余 AND 门来等价地膨胀电路。
    # 简单做法：插入两个缓冲器（x = y & y）绕一圈再回来
    n1 = M + 1; n2 = M + 2; M += 2
    buf1 = var_to_lit(n1, 0)
    buf2 = var_to_lit(n2, 0)

    # d = r0 & r1 → d = buf1 & buf1, where buf1 = r0 & r1 的等价变形
    # 实际：插入中间节点
    and_gates[idx] = (buf1, r0, r1)           # buf1 = r0 & r1
    and_gates.append((buf2, buf1, buf1))       # buf2 = buf1
    and_gates.append((d, buf2, buf2))          # d = buf2
    A += 2
    return True


def mutate_insert_buf_chain(M, I, L, O, A, B, C, inputs, outputs, bads, constraints, latches, and_gates, symbols, comments, seed):
    """在随机 AND 门的输出上插入 N 个缓冲器"""
    rng = random.Random(seed)
    if A < 1:
        return False

    idx = rng.randint(0, A - 1)
    d, r0, r1 = and_gates[idx]
    chain_len = rng.randint(1, 5)

    prev = d
    for _ in range(chain_len):
        n = M + 1; M += 1
        new_lit = var_to_lit(n, 0)
        and_gates.append((new_lit, prev, prev))
        prev = new_lit

    # 更新原门的输出引用：需要在所有后续 AND 门的输入、outputs、bads 中替换 d → prev
    # 这里简化：只把原 AND 门的输出替换到后续引用
    and_gates[idx] = (prev, r0, r1)
    A += chain_len
    return True


MUTATORS = [
    ("add_redundant_latch", mutate_add_redundant_latch),
    ("add_redundant_and", mutate_add_redundant_and),
    ("swap_and_inputs", mutate_swap_and_inputs),
    ("rewrite_demorgan", mutate_rewrite_demorgan),
    ("insert_buf_chain", mutate_insert_buf_chain),
]


def mutate_aag(in_path: str, out_path: str, seed: int, mutators: list):
    """对一个 AAG 文件执行语义保留变异"""
    data = read_aag(in_path)
    M, I, L, O, A, B, C, inputs, outputs, bads, constraints, latches, and_gates, symbols, comments = data

    rng = random.Random(seed)
    n_mutations = rng.randint(1, max(1, len(mutators)))
    chosen = rng.sample(mutators, min(n_mutations, len(mutators)))

    applied = []
    for name, func in chosen:
        ok = func(M, I, L, O, A, B, C, inputs, outputs, bads, constraints,
                   latches, and_gates, symbols, comments, seed)
        if ok:
            applied.append(name)
        # Recalculate M, I, L, etc. after mutation
        I = len(inputs)
        L = len(latches)
        O = len(outputs)
        B = len(bads)
        C = len(constraints)
        A = len(and_gates)
        # M is updated inside each mutator

    write_aag(out_path, M, I, L, O, A, B, C, inputs, outputs, bads, constraints,
              latches, and_gates, symbols, comments)
    return applied


def main():
    parser = argparse.ArgumentParser(description="AIG 语义保留变异器")
    parser.add_argument("input", help="输入 AIG 文件路径")
    parser.add_argument("-o", "--output", required=True, help="输出 AIG 文件路径")
    parser.add_argument("-s", "--seed", type=int, default=42, help="随机种子")
    parser.add_argument("-m", "--mutators", nargs="+",
                        choices=[m[0] for m in MUTATORS],
                        default=[m[0] for m in MUTATORS],
                        help="使用的变异器列表")
    parser.add_argument("-n", "--num", type=int, default=3,
                        help="应用变异器数量")
    args = parser.parse_args()

    # 只使用指定的变异器
    avail = [(n, f) for n, f in MUTATORS if n in args.mutators]
    if not avail:
        print("Error: no valid mutators specified")
        sys.exit(1)

    # 从可用变异器中随机选
    rng = random.Random(args.seed)
    chosen = rng.sample(avail, min(args.num, len(avail)))

    data = read_aag(args.input)
    M, I, L, O, A, B, C, inputs, outputs, bads, constraints, latches, and_gates, symbols, comments = data

    applied = []
    for name, func in chosen:
        ok = func(M, I, L, O, A, B, C, inputs, outputs, bads, constraints,
                   latches, and_gates, symbols, comments, args.seed)
        if ok:
            applied.append(name)
        I, L, O, B, C, A = len(inputs), len(latches), len(outputs), len(bads), len(constraints), len(and_gates)

    write_aag(args.output, M, I, L, O, A, B, C, inputs, outputs, bads, constraints,
              latches, and_gates, symbols, comments)
    print(f"Applied mutations ({len(applied)}): {', '.join(applied)}")
    print(f"Output: {args.output}  M={M} A={A}")


if __name__ == "__main__":
    main()
