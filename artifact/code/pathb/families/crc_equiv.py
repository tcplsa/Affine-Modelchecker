"""Sequential equivalence between serial and matrix-expanded CRC updates."""

from __future__ import annotations

import random

from ..netlist import Netlist
from .affine_equiv import _xor_reduce
from .word_ops import neq_words


def _crc_serial(
    net: Netlist, state: list[int], data: list[int], polynomial: int
) -> list[int]:
    value = list(state)
    width = len(value)
    for data_bit in data:
        feedback = net.xor_gate(value[-1], data_bit)
        updated = []
        for index in range(width):
            shifted = value[index - 1] if index else 0
            if (polynomial >> index) & 1:
                shifted = feedback if shifted == 0 else net.xor_gate(shifted, feedback)
            updated.append(shifted)
        value = updated
    return value


def _toggle(left: set[int], right: set[int]) -> set[int]:
    return left.symmetric_difference(right)


def _crc_symbolic(width: int, symbol_bits: int, polynomial: int) -> list[set[int]]:
    value = [{index} for index in range(width)]
    for data_index in range(symbol_bits):
        feedback = _toggle(value[-1], {width + data_index})
        updated = []
        for index in range(width):
            shifted = value[index - 1] if index else set()
            updated.append(
                _toggle(shifted, feedback)
                if (polynomial >> index) & 1 else set(shifted)
            )
        value = updated
    return value


def _instantiate_matrix(
    net: Netlist,
    supports: list[set[int]],
    state: list[int],
    data: list[int],
    topology: str,
) -> list[int]:
    symbols = state + data
    return [
        _xor_reduce(net, [symbols[index] for index in sorted(support)], topology)
        for support in supports
    ]


def generate_crc_equiv(
    width: int = 16,
    polynomial: int = 0x1021,
    symbol_bits: int = 8,
    updates: int = 1,
    seed: int = 0,
) -> Netlist:
    if width < 3 or symbol_bits < 1 or updates < 1:
        raise ValueError("invalid CRC dimensions")
    mask = (1 << width) - 1
    polynomial &= mask
    if not polynomial & 1:
        raise ValueError("CRC polynomial must have a nonzero constant term")

    net = Netlist(name=f"crc_equiv_w{width}_p{polynomial:x}_s{symbol_bits}_u{updates}")
    data = [net.add_input() for _ in range(symbol_bits)]
    rng = random.Random(seed ^ polynomial)
    initial = rng.getrandbits(width)
    left = [net.add_latch(f"serial_{i}", (initial >> i) & 1, 0) for i in range(width)]
    right = [net.add_latch(f"matrix_{i}", (initial >> i) & 1, 0) for i in range(width)]

    left_next = list(left)
    right_next = list(right)
    supports = _crc_symbolic(width, symbol_bits, polynomial)
    for _ in range(updates):
        left_next = _crc_serial(net, left_next, data, polynomial)
        right_next = _instantiate_matrix(
            net, supports, right_next, data, topology="balanced"
        )

    for index in range(width):
        net.latches[index] = (
            f"serial_{index}", left[index], (initial >> index) & 1, left_next[index]
        )
        net.latches[width + index] = (
            f"matrix_{index}", right[index], (initial >> index) & 1, right_next[index]
        )
    net.add_bad(neq_words(net, left, right))
    return net


def reference_check_crc_equiv(
    width: int, polynomial: int, symbol_bits: int, updates: int = 1, **_: object
) -> dict[str, object]:
    return {
        "expected": "SAFE",
        "invariant": "serial_crc_state == matrix_expanded_crc_state",
        "standard_polynomial": hex(polynomial),
        "symbol_bits_per_cycle": symbol_bits,
        "updates_per_transition": updates,
        "state_width": width,
    }

