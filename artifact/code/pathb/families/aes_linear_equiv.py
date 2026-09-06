"""Sequential equivalence for the AES MixColumns linear diffusion layer."""

from __future__ import annotations

import random

from ..netlist import Netlist
from .affine_equiv import _xor_reduce
from .word_ops import neq_words, xor_word


def _xtime(net: Netlist, byte: list[int], topology: str) -> list[int]:
    high = byte[7]
    reduction = 0x1B
    result = []
    for index in range(8):
        shifted = byte[index - 1] if index else 0
        terms = ([shifted] if shifted else []) + ([high] if (reduction >> index) & 1 else [])
        result.append(_xor_reduce(net, terms, topology))
    return result


def _mix_column(net: Netlist, column: list[list[int]], topology: str) -> list[list[int]]:
    doubled = [_xtime(net, byte, topology) for byte in column]
    tripled = [xor_word(net, doubled[i], column[i], topology=topology) for i in range(4)]
    return [
        xor_word(net, doubled[0], tripled[1], column[2], column[3], topology=topology),
        xor_word(net, column[0], doubled[1], tripled[2], column[3], topology=topology),
        xor_word(net, column[0], column[1], doubled[2], tripled[3], topology=topology),
        xor_word(net, tripled[0], column[1], column[2], doubled[3], topology=topology),
    ]


def _mix_state(
    net: Netlist, state: list[int], columns: int, topology: str
) -> list[int]:
    output = []
    for column_index in range(columns):
        offset = column_index * 32
        bytes_in = [state[offset + byte * 8: offset + (byte + 1) * 8] for byte in range(4)]
        for byte in _mix_column(net, bytes_in, topology):
            output.extend(byte)
    return output


def generate_aes_linear_equiv(
    columns: int = 1,
    rounds: int = 1,
    left_topology: str = "serial",
    right_topology: str = "balanced",
    input_bits: int = 8,
    seed: int = 0,
) -> Netlist:
    if columns not in {1, 2, 4} or rounds < 1:
        raise ValueError("AES MixColumns supports 1, 2, or 4 columns")
    width = columns * 32
    net = Netlist(name=f"aes_mixcolumns_c{columns}_r{rounds}")
    inputs = [net.add_input() for _ in range(input_bits)]
    rng = random.Random(seed ^ 0xAE5)
    initial = rng.getrandbits(width)
    left = [net.add_latch(f"aes_direct_{i}", (initial >> i) & 1, 0) for i in range(width)]
    right = [net.add_latch(f"aes_tree_{i}", (initial >> i) & 1, 0) for i in range(width)]
    left_next, right_next = list(left), list(right)
    for round_index in range(rounds):
        if inputs:
            injection = [inputs[(index + round_index) % len(inputs)] for index in range(width)]
            left_next = xor_word(net, left_next, injection, topology=left_topology)
            right_next = xor_word(net, right_next, injection, topology=right_topology)
        left_next = _mix_state(net, left_next, columns, left_topology)
        right_next = _mix_state(net, right_next, columns, right_topology)
    for index in range(width):
        net.latches[index] = (
            f"aes_direct_{index}", left[index], (initial >> index) & 1, left_next[index]
        )
        net.latches[width + index] = (
            f"aes_tree_{index}", right[index], (initial >> index) & 1, right_next[index]
        )
    net.add_bad(neq_words(net, left, right))
    return net


def reference_check_aes_linear_equiv(
    columns: int, rounds: int, **_: object
) -> dict[str, object]:
    return {
        "expected": "SAFE",
        "invariant": "two AES MixColumns implementations remain equivalent",
        "standard": "FIPS 197 MixColumns over GF(2^8), modulus 0x11b",
        "columns": columns,
        "rounds_per_transition": rounds,
    }

