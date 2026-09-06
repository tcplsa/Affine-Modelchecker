"""Equivalence of iterative and matrix jump-ahead LFSR hardware."""

from __future__ import annotations

import random

from ..netlist import Netlist
from .affine_equiv import _xor_reduce
from .linear_equiv import instantiate, toggle
from .word_ops import neq_words


def _step_bits(net: Netlist, state: list[int], taps: list[int]) -> list[int]:
    feedback = _xor_reduce(net, [state[index] for index in taps], "serial")
    return [feedback, *state[:-1]]


def _step_supports(state: list[set[int]], taps: list[int]) -> list[set[int]]:
    feedback = toggle(*(state[index] for index in taps))
    return [feedback, *(set(row) for row in state[:-1])]


def generate_lfsr_jump_equiv(
    width: int = 32,
    steps: int = 64,
    taps: list[int] | None = None,
    seed: int = 0,
) -> Netlist:
    if width < 4 or steps < 1:
        raise ValueError("invalid LFSR dimensions")
    if taps is None:
        taps = [width - 1, max(0, width - 2), 1, 0]
    taps = sorted(set(taps))
    if not taps or any(index < 0 or index >= width for index in taps):
        raise ValueError("LFSR taps must index the state")

    net = Netlist(name=f"lfsr_jump_equiv_w{width}_s{steps}")
    rng = random.Random(seed ^ width ^ (steps << 8))
    initial = rng.getrandbits(width) or 1
    iterative = [
        net.add_latch(f"iterative_{i}", (initial >> i) & 1, 0)
        for i in range(width)
    ]
    matrix = [
        net.add_latch(f"matrix_{i}", (initial >> i) & 1, 0)
        for i in range(width)
    ]

    iterative_next = list(iterative)
    supports = [{index} for index in range(width)]
    for _ in range(steps):
        iterative_next = _step_bits(net, iterative_next, taps)
        supports = _step_supports(supports, taps)
    matrix_next = instantiate(net, supports, matrix, "balanced")

    for index in range(width):
        bit = (initial >> index) & 1
        net.latches[index] = (
            f"iterative_{index}", iterative[index], bit, iterative_next[index]
        )
        net.latches[width + index] = (
            f"matrix_{index}", matrix[index], bit, matrix_next[index]
        )
    net.add_bad(neq_words(net, iterative, matrix))
    return net


def reference_check_lfsr_jump_equiv(
    width: int, steps: int, taps: list[int] | None = None, **_: object
) -> dict[str, object]:
    return {
        "expected": "SAFE",
        "invariant": "iterative_lfsr_state == jump_ahead_matrix_state",
        "state_width": width,
        "steps_per_cycle": steps,
        "taps": taps,
        "application": "parallel PRBS/LFSR generation and state advance",
    }

