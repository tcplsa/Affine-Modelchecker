"""Sequential equivalence across adder architectures."""

from __future__ import annotations

import random

from ..netlist import Netlist
from .word_ops import add_word, neq_words


def generate_adder_equiv(
    width: int = 16,
    left_struct: str = "ripple",
    right_struct: str = "prefix",
    rounds: int = 1,
    seed: int = 0,
) -> Netlist:
    if width < 2 or rounds < 1 or left_struct == right_struct:
        raise ValueError("adder equivalence needs distinct valid structures")
    net = Netlist(name=f"adder_equiv_{left_struct}_{right_struct}_w{width}_r{rounds}")
    operand = [net.add_input() for _ in range(width)]
    rng = random.Random(seed ^ 0xADD3)
    initial = rng.getrandbits(width)
    left = [net.add_latch(f"add_left_{i}", (initial >> i) & 1, 0) for i in range(width)]
    right = [net.add_latch(f"add_right_{i}", (initial >> i) & 1, 0) for i in range(width)]
    left_next, right_next = list(left), list(right)
    for _ in range(rounds):
        left_next = add_word(net, left_next, operand, left_struct)
        right_next = add_word(net, right_next, operand, right_struct)
    for index in range(width):
        net.latches[index] = (
            f"add_left_{index}", left[index], (initial >> index) & 1, left_next[index]
        )
        net.latches[width + index] = (
            f"add_right_{index}", right[index], (initial >> index) & 1, right_next[index]
        )
    net.add_bad(neq_words(net, left, right))
    return net


def reference_check_adder_equiv(
    width: int, left_struct: str, right_struct: str, rounds: int = 1, **_: object
) -> dict[str, object]:
    return {
        "expected": "SAFE",
        "invariant": "accumulators using distinct adder structures remain equal modulo 2^width",
        "width": width,
        "left_struct": left_struct,
        "right_struct": right_struct,
        "adds_per_transition": rounds,
    }

