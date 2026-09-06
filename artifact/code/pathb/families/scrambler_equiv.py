"""Serial-versus-parallel IEEE 64b/66b scrambler equivalence."""

from __future__ import annotations

import random

from ..netlist import Netlist
from .affine_equiv import _xor_reduce
from .linear_equiv import instantiate, toggle
from .word_ops import neq_words


HISTORY_BITS = 58
TAPS = (38, 57)


def _step_bits(net: Netlist, state: list[int], data: int) -> list[int]:
    scrambled = _xor_reduce(net, [data, state[TAPS[0]], state[TAPS[1]]], "serial")
    return [scrambled, *state[:-1]]


def _step_supports(
    state: list[set[int]], data_index: int
) -> list[set[int]]:
    scrambled = toggle({data_index}, state[TAPS[0]], state[TAPS[1]])
    return [scrambled, *(set(row) for row in state[:-1])]


def generate_scrambler_equiv(symbol_bits: int = 64, seed: int = 0) -> Netlist:
    if symbol_bits < 1 or symbol_bits > 2048:
        raise ValueError("symbol_bits must be between 1 and 2048")
    net = Netlist(name=f"eth64b66b_scrambler_equiv_s{symbol_bits}")
    data = [net.add_input() for _ in range(symbol_bits)]
    rng = random.Random(seed ^ 0x6466B58)
    initial = rng.getrandbits(HISTORY_BITS)
    serial = [
        net.add_latch(f"serial_{i}", (initial >> i) & 1, 0)
        for i in range(HISTORY_BITS)
    ]
    parallel = [
        net.add_latch(f"parallel_{i}", (initial >> i) & 1, 0)
        for i in range(HISTORY_BITS)
    ]

    serial_next = list(serial)
    for data_bit in data:
        serial_next = _step_bits(net, serial_next, data_bit)

    supports = [{index} for index in range(HISTORY_BITS)]
    # Matrix symbols place state first and the current payload after it.
    for data_index in range(symbol_bits):
        supports = _step_supports(supports, HISTORY_BITS + data_index)
    parallel_next = instantiate(net, supports, parallel + data, "balanced")

    for index in range(HISTORY_BITS):
        bit = (initial >> index) & 1
        net.latches[index] = (
            f"serial_{index}", serial[index], bit, serial_next[index]
        )
        net.latches[HISTORY_BITS + index] = (
            f"parallel_{index}", parallel[index], bit, parallel_next[index]
        )
    net.add_bad(neq_words(net, serial, parallel))
    return net


def reference_check_scrambler_equiv(symbol_bits: int, **_: object) -> dict[str, object]:
    return {
        "expected": "SAFE",
        "invariant": "serial_scrambler_history == parallel_matrix_history",
        "standard": "IEEE 802.3 64b/66b PCS",
        "polynomial": "1 + x^39 + x^58",
        "symbol_bits_per_cycle": symbol_bits,
    }

