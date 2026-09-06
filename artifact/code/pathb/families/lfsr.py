"""LFSR / affine state-transform family.

Generates a Galois LFSR of configurable width with a polynomial tap set.
The state update is fully affine (XOR-only):  s' = A s (and optionally plus
an XOR bias).  The property requires sequential reasoning, not combinational
equivalence:

  Property (SAFE):  starting from a nonzero init, the all-zero state is
  unreachable.  For a maximal-period LFSR with nonzero init this is true,
  and the proof needs a sequence of inductive steps over the affine cone.

Options:
  width      : state width (>= 2)
  taps       : list of bit indices with feedback, e.g. [0, 2, 3] for
               x^4+x^3+x^2+1 style Galois taps (see below)
  init       : nonzero initial value (int)
  use_bias   : if True, XOR a constant vector into the update (still affine)

Semantics (Galois LFSR, right-shift feedback):
  fb = s[width-1]                          (the shifted-out top bit)
  for i in range(width):
      s'[i] = s[(i+1) % width]             (rotate left in the feedback loop)
  then for each tap t in taps:
      s'[t] ^= fb                          (XOR feedback into tap position)
"""

from __future__ import annotations

import random

from ..netlist import Netlist


def generate_lfsr(width=8, taps=None, init=None, use_bias=False,
                  seed=0) -> Netlist:
    """Build a Galois LFSR netlist.  Returns (netlist, ref_state)."""
    if width < 2:
        raise ValueError("width must be >= 2")
    taps = taps if taps is not None else [0]
    taps = [t for t in taps if 0 <= t < width]
    if not taps:
        taps = [0]
    rng = random.Random(seed)

    net = Netlist(name=f"lfsr_w{width}")
    # state registers
    state = []
    for i in range(width):
        state.append(net.add_latch(f"st{i}", 0, 0))  # init patched below

    # build next-state affine functions
    fb = state[-1]          # feedback = top bit
    next_lits = []
    for i in range(width):
        nxt = state[(i + 1) % width]
        if i in taps:
            nxt = net.xor_gate(nxt, fb)
        next_lits.append(nxt)
        # patch latch next
        _name, _cur, _init, _old = net.latches[i]
        net.latches[i] = (_name, _cur, _init, next_lits[i])

    # optional constant XOR bias (keeps the map affine, non-homogeneous)
    if use_bias:
        bias = rng.getrandbits(width)
        for i in range(width):
            if (bias >> i) & 1:
                one = net.const_true()
                net.latches[i] = (net.latches[i][0], net.latches[i][1],
                                  net.latches[i][2],
                                  net.xor_gate(net.latches[i][3], one))

    # initial state (nonzero)
    if init is None:
        init = 1
    init = init & ((1 << width) - 1)
    if init == 0:
        init = 1
    # represent init via latches with init value = bit
    for i in range(width):
        bit = (init >> i) & 1
        _name, _cur, _init, nxt = net.latches[i]
        net.latches[i] = (_name, _cur, bit, nxt)

    # bad = all-zero state reached
    # all-zero = AND over ~state[i]  (i.e. NOR over state)
    all_zero = None
    for i in range(width):
        not_s = net.not_gate(state[i])
        all_zero = not_s if all_zero is None else net.and_gate(all_zero, not_s)
    net.add_bad(all_zero)

    return net


def reference_check_lfsr(net: Netlist, width, taps, init, use_bias,
                         steps=256, seed=0) -> dict:
    """Reference simulation: returns whether all-zero is reached.

    Mirrors generate_lfsr's semantics exactly.
    """
    rng = random.Random(seed)
    taps = list(taps) if taps is not None else [0]
    taps = [t for t in taps if 0 <= t < width] or [0]
    state = init & ((1 << width) - 1)
    if state == 0:
        state = 1
    bias = rng.getrandbits(width) if use_bias else 0
    mask = (1 << width) - 1
    for k in range(steps):
        fb = (state >> (width - 1)) & 1          # old top bit
        # rotate right by 1: new bit i = old bit (i+1)
        rot = ((state >> 1) | ((state & 1) << (width - 1))) & mask
        state = rot
        for t in taps:
            state ^= (fb << t)
        if use_bias:
            state ^= bias
        state &= mask
        if state == 0:
            return {"reached_zero": True, "at_step": k}
    return {"reached_zero": False, "at_step": None}
