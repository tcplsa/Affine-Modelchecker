"""Depth-controlled UNSAFE variants of affine datapath equivalence models.

Each variant starts from an existing SAFE dual-implementation model and flips
one bit of the right implementation on a deterministic transition.  The
original transition relation, property, and data inputs are otherwise
unchanged, which makes the SAFE/UNSAFE comparison structurally paired.
"""

from __future__ import annotations

from ..netlist import Netlist
from .crc_frame_align import generate_crc_frame_align
from .scrambler_equiv import HISTORY_BITS, generate_scrambler_equiv
from .syndrome_equiv import generate_syndrome_equiv


def _inject_delayed_fault(
    net: Netlist, target_latch: int, witness_depth: int, fault_bit: int
) -> None:
    """XOR a one-shot pulse into a latch update at ``witness_depth``.

    State depth zero is the initial state.  ``fault_phase_0`` is initially one,
    so a pulse at index ``witness_depth - 1`` changes the transition entering
    the requested bad-state depth.
    """
    if witness_depth < 1:
        raise ValueError("witness_depth must be at least one")
    if target_latch < 0 or target_latch >= len(net.latches):
        raise ValueError("target latch is outside the original model")

    phase_offset = len(net.latches)
    phase = [
        net.add_latch(f"fault_phase_{index}", int(index == 0), 0)
        for index in range(witness_depth)
    ]
    net.latches[phase_offset] = ("fault_phase_0", phase[0], 1, 0)
    for index in range(1, witness_depth):
        net.latches[phase_offset + index] = (
            f"fault_phase_{index}", phase[index], 0, phase[index - 1]
        )

    name, current, initial, next_lit = net.latches[target_latch]
    net.latches[target_latch] = (
        name, current, initial, net.xor_gate(next_lit, phase[-1])
    )
    net.name += f"_faultb{fault_bit}_d{witness_depth}"


def generate_crc_frame_align_unsafe(
    width: int = 32,
    polynomial: int = 0x04C11DB7,
    symbol_bits: int = 64,
    witness_depth: int = 8,
    fault_bit: int = 0,
    seed: int = 0,
) -> Netlist:
    net = generate_crc_frame_align(width, polynomial, symbol_bits, seed)
    if fault_bit < 0 or fault_bit >= width:
        raise ValueError("fault_bit must index the CRC state")
    # The right/matrix implementation occupies latches [width, 2*width).
    _inject_delayed_fault(net, width + fault_bit, witness_depth, fault_bit)
    return net


def generate_scrambler_equiv_unsafe(
    symbol_bits: int = 64,
    witness_depth: int = 8,
    fault_bit: int = 0,
    seed: int = 0,
) -> Netlist:
    net = generate_scrambler_equiv(symbol_bits, seed)
    if fault_bit < 0 or fault_bit >= HISTORY_BITS:
        raise ValueError("fault_bit must index the scrambler history")
    _inject_delayed_fault(net, HISTORY_BITS + fault_bit, witness_depth, fault_bit)
    return net


def generate_syndrome_equiv_unsafe(
    check_bits: int = 32,
    data_bits: int = 256,
    row_weight: int = 17,
    witness_depth: int = 8,
    fault_bit: int = 0,
    seed: int = 0,
) -> Netlist:
    net = generate_syndrome_equiv(check_bits, data_bits, row_weight, seed)
    if fault_bit < 0 or fault_bit >= check_bits:
        raise ValueError("fault_bit must index the syndrome state")
    _inject_delayed_fault(net, check_bits + fault_bit, witness_depth, fault_bit)
    return net


def reference_check_unsafe_fault(
    family: str, witness_depth: int, fault_bit: int = 0, **_: object
) -> dict[str, object]:
    suffix = "_unsafe"
    paired_family = family[:-len(suffix)] if family.endswith(suffix) else family
    return {
        "expected": "UNSAFE",
        "witness_depth": witness_depth,
        "fault_bit": fault_bit,
        "fault_model": "one-shot XOR fault in the right implementation",
        "paired_safe_family": paired_family,
    }
