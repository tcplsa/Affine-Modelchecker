"""Adder family for Path B.

Implements three structurally different n-bit adder building blocks:
  ripple    : serial carry chain (AND/OR heavy, deep carry path)
  prefix    : carry-lookahead via generate/propagate network (log-depth)
  carrysave : carry-save (XOR for sum, AND for carry, no ripple chain)

Each adder structure is embedded in one of two *sequential* properties so the
task is NOT a single combinational equivalence check:

  mode="invariant" (SAFE):
      Two identical accumulators acc1, acc2, both initialized to 0 and both
      fed the SAME input word a every cycle:
          acc1' = acc1 + a ;  acc2' = acc2 + a   (same structure)
      bad = (acc1 != acc2).
      The property is an inductive invariant and requires PDR to prove the
      latch-level equality across the adder structure.  Expected: SAFE.

  mode="counter" (UNSAFE):
      A free-running accumulator acc' = acc + 1 (input forced to 1):
          acc' = acc + 1
      bad = (acc == target), where target >= 1.
      From init 0, bad is reached after exactly `target` frames, so PDR/BMC
      must unroll `target` frames to find the counterexample.  Expected:
      UNSAFE, with witness depth `target`.
"""

from __future__ import annotations

import random

from ..netlist import Netlist


def _full_adder(net, a, b, cin):
    """Full adder over netlist literals -> (sum, carry_out)."""
    axb = net.xor_gate(a, b)
    s = net.xor_gate(axb, cin)
    ab = net.and_gate(a, b)
    cin_axb = net.and_gate(cin, axb)
    cout = net.or_gate(ab, cin_axb)
    return s, cout


def _add_ripple(net, x, y):
    """Ripple-carry addition of two literal lists; returns (sum, cout)."""
    assert len(x) == len(y)
    w = len(x)
    sum_lits = []
    carry = 0
    for i in range(w):
        s, carry = _full_adder(net, x[i], y[i], carry)
        sum_lits.append(s)
    return sum_lits, carry


def _add_prefix(net, x, y):
    """Carry-lookahead adder (parallel G/P network); returns (sum, cout).

    g_i = x_i & y_i ;  p_i = x_i ^ y_i
    carry chain computed as a prefix OR over generate/propagate, giving a
    structurally distinct (log-depth) network from ripple.
    """
    w = len(x)
    g = [net.and_gate(x[i], y[i]) for i in range(w)]
    p = [net.xor_gate(x[i], y[i]) for i in range(w)]
    carries = []
    acc = 0
    for i in range(w):
        carries.append(acc)
        pacc = net.and_gate(p[i], acc)
        acc = net.or_gate(g[i], pacc)
    sum_lits = []
    for i in range(w):
        sum_lits.append(p[0] if i == 0 else net.xor_gate(p[i], carries[i]))
    return sum_lits, acc


def _add_carrysave(net, x, y):
    """Carry-save addition: sum via XOR, carry via majority (no chain).

    Returns (sum, carry) where the carry bits are shifted left and folded back
    by the caller when a real accumulation is needed.
    """
    w = len(x)
    sum_lits = []
    carry_lits = []
    for i in range(w):
        s, c = _full_adder(net, x[i], y[i], 0)
        sum_lits.append(s)
        carry_lits.append(c)
    return sum_lits, carry_lits


def _add(net, struct, x, y):
    """Dispatch to a structural adder; returns (sum, cout)."""
    if struct == "ripple":
        return _add_ripple(net, x, y)
    if struct == "prefix":
        return _add_prefix(net, x, y)
    if struct == "carrysave":
        sum_lits, carry = _add_carrysave(net, x, y)
        # fold shifted carry back with a ripple pass to produce a real sum
        sh_carry = [0] + carry[:-1]
        return _add_ripple(net, sum_lits, sh_carry)
    raise ValueError(f"unknown adder struct {struct}")


def _eq_literal(net, xs, ys):
    """Build a literal that is true iff word xs equals word ys."""
    any_diff = None
    for a, b in zip(xs, ys):
        d = net.xor_gate(a, b)
        any_diff = d if any_diff is None else net.or_gate(any_diff, d)
    # any_diff is 1 if ANY bit differs -> negate to get equality
    return net.not_gate(any_diff)


def _neq_literal(net, xs, ys):
    """Build a literal that is true iff word xs differs from word ys."""
    any_diff = None
    for a, b in zip(xs, ys):
        d = net.xor_gate(a, b)
        any_diff = d if any_diff is None else net.or_gate(any_diff, d)
    return any_diff


def generate_adder(width=8, struct="ripple", mode="invariant", target=None,
                   seed=0) -> Netlist:
    """Build an n-bit sequential adder benchmark.  Returns a Netlist."""
    if width < 2:
        raise ValueError("width must be >= 2")

    net = Netlist(name=f"adder_{struct}_w{width}")

    if mode == "invariant":
        # SAFE inductive invariant: two identical accumulators with same input.
        a = [net.add_input() for _ in range(width)]
        acc1 = [net.add_latch(f"a1_{i}", 0, 0) for i in range(width)]
        acc2 = [net.add_latch(f"a2_{i}", 0, 0) for i in range(width)]
        nxt1, _c = _add(net, struct, acc1, a)
        nxt2, _c = _add(net, struct, acc2, a)
        for i in range(width):
            net.latches[i] = (f"a1_{i}", acc1[i], 0, nxt1[i])
        for i in range(width):
            net.latches[width + i] = (f"a2_{i}", acc2[i], 0, nxt2[i])
        # bad = (acc1 != acc2); equality is the inductive invariant.
        bad = _neq_literal(net, acc1, acc2)
        net.add_bad(bad)
        return net

    elif mode == "counter":
        # UNSAFE: free-running counter acc' = acc + 1; bad when acc == target.
        # The "+1" is realized as acc + one (a constant-1 word).
        one = net.const_true()  # signal id carrying constant 1
        acc = [net.add_latch(f"cnt_{i}", 0, 0) for i in range(width)]
        one_word = [one if i == 0 else 0 for i in range(width)]
        nxt, _c = _add(net, struct, acc, one_word)
        for i in range(width):
            net.latches[i] = (f"cnt_{i}", acc[i], 0, nxt[i])
        if target is None:
            target = (1 << width) - 1  # full count -> deepest witness
        target &= (1 << width) - 1
        # bad = (acc == target)
        eq = None
        for i in range(width):
            lit = acc[i] if ((target >> i) & 1) else net.not_gate(acc[i])
            eq = lit if eq is None else net.and_gate(eq, lit)
        net.add_bad(eq)
        return net

    raise ValueError(f"unknown mode {mode}")


def reference_check_adder(width, struct, mode, target=None, steps=512,
                          seed=0) -> dict:
    """Reference simulation returning expected outcome / witness depth.

    Mirrors generate_adder's semantics at the integer level.
    """
    mask = (1 << width) - 1
    if mode == "invariant":
        return {"expected": "SAFE", "witness_depth": None}
    elif mode == "counter":
        if target is None:
            target = mask
        target &= mask
        if target == 0:
            return {"expected": "UNSAFE", "witness_depth": 0}
        # acc increments by 1 each step from 0
        return {"expected": "UNSAFE", "witness_depth": target}
    raise ValueError(f"unknown mode {mode}")
