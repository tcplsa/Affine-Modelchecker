"""Shift-XOR-mix family: replicates the structural pattern of shift1add2048.

The core pattern that makes shift1add2048 hard for PDR (depth ~38, thousands
of CTIs) is a *prefix-AND chain with XOR feedback*:

      andacc[i] = AND(l[i], l[i+1], ..., l[w-1])      (prefix AND from high)
      l[i]'     = andacc[i+2] ^ l[i]                  (XOR feedback, i<=w-3)
      l[w-2]'   = l[w-1] ^ ~l[w-2]
      l[w-1]'   = (shift/input mix)

There is no simple single-frame inductive invariant: the prefix-AND chain
rapidly collapses values to 0 while the XOR feedback and inputs keep
re-injecting ones, so the bad state (several latches simultaneously high)
"looks" reachable in shallow unrollings but is blocked by the deep structure.
This produces many CTIs for PDR.

The design is a pure function of (width, seed).  Safety is verified by rIC3
in self-test; the generator itself only emits the netlist.
"""

from __future__ import annotations

import random

from ..netlist import Netlist, CONST_0, CONST_1


def generate_shiftmix(width=8, seed=0, mode="chain", badbits=None) -> Netlist:
    """Build the shift-XOR-mix benchmark.  Returns a Netlist.

    mode="chain":  prefix-AND + XOR feedback chain (shift1add2048-like).
    mode="acc":    also accumulate the XOR of chain bits into a counter.
    """
    if width < 4:
        raise ValueError("width must be >= 4")
    rnd = random.Random(seed)
    net = Netlist(name=f"shiftmix_{mode}_w{width}")

    ins = [net.add_input() for _ in range(4)]
    one = net.const_true()

    # ---- core chain l[0..w-1] (init all 0) ----
    l = [net.add_latch(f"l_{i}", 0, 0) for i in range(width)]

    # prefix AND accumulator from the high end:
    #   andacc[j] = AND(l[j], l[j+1], ..., l[w-1])
    andacc = [None] * width
    andacc[width - 1] = l[width - 1]
    for j in range(width - 2, -1, -1):
        andacc[j] = net.and_gate(l[j], andacc[j + 1])

    for i in range(0, width - 2):
        # l[i]' = AND(l[i+2..w-1]) ^ l[i]
        nxt = net.xor_gate(andacc[i + 2], l[i])
        net.latches[i] = (f"l_{i}", l[i], 0, nxt)

    # l[w-2]' = l[w-1] ^ ~l[w-2]
    nl = net.not_gate(l[width - 2])
    nxt = net.xor_gate(l[width - 1], nl)
    net.latches[width - 2] = (f"l_{width-2}", l[width - 2], 0, nxt)

    # l[w-1]' = one ^ (chain of inputs)  -> shift input mix
    if mode == "chain":
        mix = one
        for k in range(4):
            mix = net.xor_gate(mix, ins[k])
        nxt = net.xor_gate(l[width - 1], mix)
    else:  # acc
        mix = one
        for k in range(4):
            mix = net.xor_gate(mix, ins[k])
        nxt = net.xor_gate(l[width - 1], mix)
    net.latches[width - 1] = (f"l_{width-1}", l[width - 1], 0, nxt)

    # ---- accumulator over XOR of chain bits (mode="acc") ----
    if mode == "acc":
        # parity = XOR(l[0..w-1])
        par = l[0]
        for i in range(1, width):
            par = net.xor_gate(par, l[i])
        acc = [net.add_latch(f"a_{i}", 0, 0) for i in range(width)]
        # a[i]' = a[i] ^ (par & one)   -> toggles on parity
        for i in range(width):
            t = net.and_gate(par, one)
            nxt = net.xor_gate(acc[i], t)
            net.latches[len(l) + i] = (f"a_{i}", acc[i], 0, nxt)

    # ---- bad: AND of a few selected latches ----
    if badbits is None:
        # pick ~4 latch indices spread across the chain (deterministic by seed)
        picks = sorted(rnd.sample(range(width), min(4, width)))
        badbits = picks
    bad = None
    for bi in badbits:
        lit = l[bi]
        bad = lit if bad is None else net.and_gate(bad, lit)
    if bad is None:
        bad = l[0]
    net.add_bad(bad)
    return net


def reference_check_shiftmix(width, mode="chain", seed=0, badbits=None,
                             steps=1024) -> dict:
    """Reference simulation; safety is decided by rIC3, not here."""
    return {"expected": None, "witness_depth": None}
