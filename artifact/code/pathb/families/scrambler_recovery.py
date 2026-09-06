"""IEEE 802.3-style 64b/66b self-synchronizing scrambler recovery.

The PCS scrambler polynomial is ``1 + x^39 + x^58``.  The receiver keeps a
history of received scrambled bits; regardless of its arbitrary power-up
history, descrambling becomes correct after 58 received bits.  This family
checks that recovery property for a parameterized number of serial bits per
transition, including the practical 64-bit parallel datapath.
"""

from __future__ import annotations

import random

from ..netlist import Netlist
from .affine_equiv import _xor_reduce


HISTORY_BITS = 58
TAP_A = 39
TAP_B = 58


def _shift_in(bits: list[int], newest: int) -> list[int]:
    return [newest, *bits[:-1]]


def _or_reduce(net: Netlist, terms: list[int]) -> int:
    value = terms[0]
    for term in terms[1:]:
        value = net.or_gate(value, term)
    return value


def generate_scrambler_recovery(
    symbol_bits: int = 64,
    seed: int = 0,
    topology: str = "balanced",
) -> Netlist:
    """Check eventual descrambler correctness after arbitrary history loss."""
    if symbol_bits < 1 or symbol_bits > 128:
        raise ValueError("symbol_bits must be between 1 and 128")
    if topology not in {"serial", "balanced"}:
        raise ValueError("topology must be serial or balanced")

    net = Netlist(name=f"eth64b66b_scrambler_recovery_w{symbol_bits}")
    data = [net.add_input() for _ in range(symbol_bits)]
    rng = random.Random(seed ^ 0x6466_B58)
    tx_init = [rng.getrandbits(1) for _ in range(HISTORY_BITS)]
    rx_init = [rng.getrandbits(1) for _ in range(HISTORY_BITS)]
    tx = [net.add_latch(f"tx_history_{i}", tx_init[i], 0) for i in range(HISTORY_BITS)]
    rx = [net.add_latch(f"rx_history_{i}", rx_init[i], 0) for i in range(HISTORY_BITS)]

    tx_next = list(tx)
    rx_next = list(rx)
    mismatches = []
    for data_bit in data:
        scrambled = _xor_reduce(
            net,
            [data_bit, tx_next[TAP_A - 1], tx_next[TAP_B - 1]],
            topology,
        )
        decoded = _xor_reduce(
            net,
            [scrambled, rx_next[TAP_A - 1], rx_next[TAP_B - 1]],
            topology,
        )
        mismatches.append(net.xor_gate(decoded, data_bit))
        tx_next = _shift_in(tx_next, scrambled)
        rx_next = _shift_in(rx_next, scrambled)

    for index in range(HISTORY_BITS):
        net.latches[index] = (
            f"tx_history_{index}", tx[index], tx_init[index], tx_next[index]
        )
        net.latches[HISTORY_BITS + index] = (
            f"rx_history_{index}", rx[index], rx_init[index], rx_next[index]
        )

    flush_cycles = (HISTORY_BITS + symbol_bits - 1) // symbol_bits
    phase = [
        net.add_latch(f"flush_{index}", int(index == 0), 0)
        for index in range(flush_cycles)
    ]
    ready = net.add_latch("recovered", 0, 0)
    phase_offset = 2 * HISTORY_BITS
    net.latches[phase_offset] = ("flush_0", phase[0], 1, 0)
    for index in range(1, flush_cycles):
        net.latches[phase_offset + index] = (
            f"flush_{index}", phase[index], 0, phase[index - 1]
        )
    net.latches[phase_offset + flush_cycles] = (
        "recovered", ready, 0, net.or_gate(ready, phase[-1])
    )

    any_mismatch = _or_reduce(net, mismatches)
    net.add_bad(net.and_gate(ready, any_mismatch))
    return net


def reference_check_scrambler_recovery(symbol_bits: int, **_: object) -> dict[str, object]:
    return {
        "expected": "SAFE",
        "invariant": "recovered implies descrambled payload equals input payload",
        "standard": "IEEE 802.3 64b/66b PCS self-synchronous scrambler",
        "polynomial": "1 + x^39 + x^58",
        "flush_bits": HISTORY_BITS,
        "flush_cycles": (HISTORY_BITS + symbol_bits - 1) // symbol_bits,
    }
