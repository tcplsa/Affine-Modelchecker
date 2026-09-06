"""PCS-style CRC recovery after a multi-block lock acquisition sequence.

The model represents a receiver with two equivalent CRC implementations that
start from unrelated recovery state.  While unlocked, ``header_valid`` drives
a consecutive-valid-block detector.  Once enough headers have been observed,
the receiver acquires block lock and both CRC engines reload the standard
all-one frame seed.  A link-loss input drops lock and restarts recovery.

This keeps the real linear CRC data path from ``crc_frame_align`` but adds the
small sequential control protocol that precedes an ordinary frame boundary.
The safety claim is deliberately local to lock: while block lock is asserted,
the serial reference and parallel matrix CRC must agree for arbitrary traffic.
"""

from __future__ import annotations

import random

from ..netlist import Netlist
from .crc_equiv import _crc_serial, _crc_symbolic, _instantiate_matrix
from .word_ops import neq_words


def _mux(net: Netlist, select: int, when_true: int, when_false: int) -> int:
    return net.or_gate(
        net.and_gate(select, when_true),
        net.and_gate(net.not_gate(select), when_false),
    )


def generate_crc_frame_lock(
    width: int = 32,
    polynomial: int = 0x04C11DB7,
    symbol_bits: int = 64,
    confirm_headers: int = 4,
    seed: int = 0,
) -> Netlist:
    """Generate a SAFE CRC property guarded by receiver block lock.

    ``confirm_headers`` is the number of consecutive valid headers required
    before the recovery FSM acquires lock.  It is intentionally parameterized
    rather than presented as one fixed standard-specific threshold.
    """
    if width < 3 or symbol_bits < 1 or confirm_headers < 2:
        raise ValueError("invalid CRC lock dimensions")
    polynomial &= (1 << width) - 1
    if not polynomial & 1:
        raise ValueError("CRC polynomial must have a nonzero constant term")

    net = Netlist(
        name=(
            f"crc_frame_lock_w{width}_p{polynomial:x}_s{symbol_bits}"
            f"_c{confirm_headers}"
        )
    )
    header_valid = net.add_input()
    link_loss = net.add_input()
    valid = net.add_input()
    data = [net.add_input() for _ in range(symbol_bits)]
    rng = random.Random(seed ^ polynomial ^ 0xC1C0)
    serial_init = rng.getrandbits(width)
    matrix_init = rng.getrandbits(width)
    reset = (1 << width) - 1

    serial = [
        net.add_latch(f"serial_crc_{index}", (serial_init >> index) & 1, 0)
        for index in range(width)
    ]
    matrix = [
        net.add_latch(f"matrix_crc_{index}", (matrix_init >> index) & 1, 0)
        for index in range(width)
    ]
    locked = net.add_latch("block_lock", 0, 0)
    # A one-hot run detector. phase[0] means no currently retained header;
    # phase[-1] plus another valid header acquires lock.
    phase = [
        net.add_latch(f"header_run_{index}", 1 if index == 0 else 0, 0)
        for index in range(confirm_headers)
    ]

    not_locked = net.not_gate(locked)
    active_header = net.and_gate(header_valid, net.not_gate(link_loss))
    acquire = net.and_gate(net.and_gate(not_locked, phase[-1]), active_header)
    lock_without_loss = net.or_gate(locked, acquire)
    lock_next = net.and_gate(lock_without_loss, net.not_gate(link_loss))

    serial_update = _crc_serial(net, serial, data, polynomial)
    supports = _crc_symbolic(width, symbol_bits, polynomial)
    matrix_update = _instantiate_matrix(net, supports, matrix, data, "balanced")
    one = net.const_true()
    for index in range(width):
        serial_step = _mux(net, valid, serial_update[index], serial[index])
        matrix_step = _mux(net, valid, matrix_update[index], matrix[index])
        seed_bit = one if (reset >> index) & 1 else 0
        serial_next = _mux(net, acquire, seed_bit, serial_step)
        matrix_next = _mux(net, acquire, seed_bit, matrix_step)
        net.latches[index] = (
            f"serial_crc_{index}",
            serial[index],
            (serial_init >> index) & 1,
            serial_next,
        )
        net.latches[width + index] = (
            f"matrix_crc_{index}",
            matrix[index],
            (matrix_init >> index) & 1,
            matrix_next,
        )

    net.latches[2 * width] = ("block_lock", locked, 0, lock_next)
    phase_base = 2 * width + 1
    for index, current in enumerate(phase):
        if index == 0:
            # Any loss, any acquired lock, or an invalid header restarts the
            # detector at the empty prefix.
            phase_next = _mux(net, lock_next, one, net.not_gate(active_header))
        else:
            shifted = phase[index - 1]
            phase_next = _mux(net, lock_next, 0, net.and_gate(active_header, shifted))
        net.latches[phase_base + index] = (
            f"header_run_{index}", current, 1 if index == 0 else 0, phase_next
        )

    net.add_bad(net.and_gate(locked, neq_words(net, serial, matrix)))
    return net


def reference_check_crc_frame_lock(
    width: int,
    polynomial: int,
    symbol_bits: int,
    confirm_headers: int,
    **_: object,
) -> dict[str, object]:
    return {
        "expected": "SAFE",
        "invariant": "block_lock implies serial_crc == matrix_crc",
        "protocol": "multi-block receiver lock acquisition followed by CRC frame reset",
        "polynomial": hex(polynomial),
        "state_width": width,
        "symbol_bits_per_cycle": symbol_bits,
        "confirm_headers": confirm_headers,
        "reset_seed": hex((1 << width) - 1),
    }
