"""Streaming binary-code syndrome unit with two XOR-network topologies."""

from __future__ import annotations

import random

from ..netlist import Netlist
from .affine_equiv import _xor_reduce
from .word_ops import neq_words


def _rows(check_bits: int, data_bits: int, row_weight: int, seed: int) -> list[list[int]]:
    rng = random.Random(seed ^ (check_bits << 16) ^ data_bits)
    rows = []
    for row in range(check_bits):
        # Include a distinct anchor column so the parity-check matrix has full row rank.
        support = {row % data_bits}
        population = [index for index in range(data_bits) if index not in support]
        support.update(rng.sample(population, min(row_weight - 1, len(population))))
        rows.append(sorted(support))
    return rows


def generate_syndrome_equiv(
    check_bits: int = 32,
    data_bits: int = 256,
    row_weight: int = 17,
    seed: int = 0,
) -> Netlist:
    if check_bits < 2 or data_bits < check_bits or row_weight < 2:
        raise ValueError("invalid syndrome dimensions")
    net = Netlist(name=f"streaming_syndrome_c{check_bits}_d{data_bits}_r{row_weight}")
    data = [net.add_input() for _ in range(data_bits)]
    rng = random.Random(seed ^ 0x51D0)
    initial = rng.getrandbits(check_bits)
    serial = [
        net.add_latch(f"serial_{i}", (initial >> i) & 1, 0)
        for i in range(check_bits)
    ]
    balanced = [
        net.add_latch(f"balanced_{i}", (initial >> i) & 1, 0)
        for i in range(check_bits)
    ]

    serial_next = []
    balanced_next = []
    for index, support in enumerate(_rows(check_bits, data_bits, row_weight, seed)):
        terms = [data[column] for column in support]
        serial_parity = _xor_reduce(net, terms, "serial")
        balanced_parity = _xor_reduce(net, terms, "balanced")
        serial_next.append(net.xor_gate(serial[index], serial_parity))
        balanced_next.append(net.xor_gate(balanced[index], balanced_parity))

    for index in range(check_bits):
        bit = (initial >> index) & 1
        net.latches[index] = (
            f"serial_{index}", serial[index], bit, serial_next[index]
        )
        net.latches[check_bits + index] = (
            f"balanced_{index}", balanced[index], bit, balanced_next[index]
        )
    net.add_bad(neq_words(net, serial, balanced))
    return net


def reference_check_syndrome_equiv(
    check_bits: int, data_bits: int, row_weight: int, **_: object
) -> dict[str, object]:
    return {
        "expected": "SAFE",
        "invariant": "serial_syndrome == balanced_tree_syndrome",
        "check_bits": check_bits,
        "data_bits_per_cycle": data_bits,
        "row_weight": row_weight,
        "application": "streaming linear-code parity-check/syndrome hardware",
    }

