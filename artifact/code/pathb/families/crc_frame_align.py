"""Frame-boundary recovery for dual CRC engines.

Two CRC engines deliberately begin with unrelated register contents.  A
start-of-frame input reloads the standard all-one CRC seed, after which a
bit-serial reference and a parallel matrix implementation must remain equal
under arbitrary valid/data sequences.  This represents recovery at a known
frame boundary rather than an abstract affine correction vector.
"""

from __future__ import annotations

import random

from ..netlist import Netlist
from .affine_equiv import _xor_reduce
from .crc_equiv import _crc_serial, _crc_symbolic, _instantiate_matrix
from .word_ops import neq_words


def _mux(net: Netlist, select: int, when_true: int, when_false: int) -> int:
    return net.or_gate(
        net.and_gate(select, when_true),
        net.and_gate(net.not_gate(select), when_false),
    )


def generate_crc_frame_align(
    width: int = 32,
    polynomial: int = 0x04C11DB7,
    symbol_bits: int = 64,
    seed: int = 0,
) -> Netlist:
    """Generate SAFE CRC alignment after the first arbitrary start-of-frame."""
    if width < 3 or symbol_bits < 1:
        raise ValueError("invalid CRC dimensions")
    polynomial &= (1 << width) - 1
    if not polynomial & 1:
        raise ValueError("CRC polynomial must have a nonzero constant term")

    net = Netlist(name=f"crc_frame_align_w{width}_p{polynomial:x}_s{symbol_bits}")
    sof = net.add_input()
    valid = net.add_input()
    data = [net.add_input() for _ in range(symbol_bits)]
    rng = random.Random(seed ^ polynomial ^ 0xC2C2)
    serial_init = rng.getrandbits(width)
    matrix_init = rng.getrandbits(width)
    reset = (1 << width) - 1
    serial = [
        net.add_latch(f"serial_crc_{i}", (serial_init >> i) & 1, 0)
        for i in range(width)
    ]
    matrix = [
        net.add_latch(f"matrix_crc_{i}", (matrix_init >> i) & 1, 0)
        for i in range(width)
    ]
    seen_sof = net.add_latch("seen_sof", 0, 0)

    serial_update = _crc_serial(net, serial, data, polynomial)
    supports = _crc_symbolic(width, symbol_bits, polynomial)
    matrix_update = _instantiate_matrix(net, supports, matrix, data, "balanced")
    one = net.const_true()
    for index in range(width):
        serial_hold_or_update = _mux(net, valid, serial_update[index], serial[index])
        matrix_hold_or_update = _mux(net, valid, matrix_update[index], matrix[index])
        reset_bit = one if (reset >> index) & 1 else 0
        serial_next = _mux(net, sof, reset_bit, serial_hold_or_update)
        matrix_next = _mux(net, sof, reset_bit, matrix_hold_or_update)
        net.latches[index] = (
            f"serial_crc_{index}", serial[index], (serial_init >> index) & 1, serial_next
        )
        net.latches[width + index] = (
            f"matrix_crc_{index}", matrix[index], (matrix_init >> index) & 1, matrix_next
        )
    net.latches[2 * width] = ("seen_sof", seen_sof, 0, net.or_gate(seen_sof, sof))
    net.add_bad(net.and_gate(seen_sof, neq_words(net, serial, matrix)))
    return net


def reference_check_crc_frame_align(
    width: int, polynomial: int, symbol_bits: int, **_: object
) -> dict[str, object]:
    return {
        "expected": "SAFE",
        "invariant": "seen_sof implies serial_crc == matrix_crc",
        "standard": "CRC frame-boundary reinitialization",
        "polynomial": hex(polynomial),
        "state_width": width,
        "symbol_bits_per_cycle": symbol_bits,
        "reset_seed": hex((1 << width) - 1),
    }
