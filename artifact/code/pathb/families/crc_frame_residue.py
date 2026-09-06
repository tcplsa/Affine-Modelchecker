"""Fixed-length CRC frame/FCS residue checking with an explicit frame protocol.

The receiver starts a frame from the standard CRC seed, consumes a fixed number
of arbitrary payload symbols, captures the linearly derived FCS, consumes that
trailer, and checks the CRC residue in the following cycle.  The property is
only asserted at the check phase.  Consequently, proving it requires a
relation between the frame phase, the accumulated CRC state, and the delayed
FCS register; it is not a global serial-versus-parallel equivalence invariant.
"""

from __future__ import annotations

from ..netlist import Netlist
from .affine_equiv import _xor_reduce
from .crc_equiv import _crc_serial, _crc_symbolic
from .word_ops import neq_words


def _mux(net: Netlist, select: int, when_true: int, when_false: int) -> int:
    return net.or_gate(
        net.and_gate(select, when_true),
        net.and_gate(net.not_gate(select), when_false),
    )


def _crc_update_int(state: int, data: int, width: int, polynomial: int) -> int:
    mask = (1 << width) - 1
    value = state & mask
    for index in range(width):
        feedback = ((value >> (width - 1)) & 1) ^ ((data >> index) & 1)
        value = (value << 1) & mask
        if feedback:
            value ^= polynomial
    return value


def _fcs_supports(width: int, polynomial: int) -> list[set[int]]:
    """Return FCS input bits that drive any CRC state to zero in ``width`` bits."""
    transition = _crc_symbolic(width, width, polynomial)
    state_rows = [sum(1 << bit for bit in support if bit < width) for support in transition]
    input_rows = [
        sum(1 << (bit - width) for bit in support if bit >= width)
        for support in transition
    ]

    # Row-reduce [B | I], where output = A * state xor B * fcs.  The right
    # block gives fcs_i as a linear combination of output rows after B=I.
    rows = [input_rows[index] | (1 << (width + index)) for index in range(width)]
    for column in range(width):
        pivot = next((row for row in range(column, width) if (rows[row] >> column) & 1), None)
        if pivot is None:
            raise ValueError("CRC input response is singular; cannot construct FCS")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        for row in range(width):
            if row != column and ((rows[row] >> column) & 1):
                rows[row] ^= rows[column]
    inverse_rows = [row >> width for row in rows]
    supports = []
    for fcs_index, inverse in enumerate(inverse_rows):
        state_support = 0
        for output_index in range(width):
            if (inverse >> output_index) & 1:
                state_support ^= state_rows[output_index]
        supports.append({index for index in range(width) if (state_support >> index) & 1})

    # The transform is small and deterministic.  Verify every state basis to
    # keep this generator honest if the CRC bit convention changes later.
    for basis in range(width):
        state = 1 << basis
        fcs = sum(
            ((sum((state >> bit) & 1 for bit in support) & 1) << index)
            for index, support in enumerate(supports)
        )
        if _crc_update_int(state, fcs, width, polynomial) != 0:
            raise AssertionError("constructed FCS does not produce zero residue")
    return supports


def generate_crc_frame_residue(
    width: int = 32,
    polynomial: int = 0x04C11DB7,
    symbol_bits: int = 32,
    payload_cycles: int = 4,
    fcs_topology: str = "balanced",
    seed: int = 0,
) -> Netlist:
    """Generate a SAFE CRC frame residue property with a delayed FCS trailer."""
    del seed  # The protocol has a fixed standard seed; no random initial state.
    if width < 3 or symbol_bits < 1 or payload_cycles < 1:
        raise ValueError("invalid CRC residue dimensions")
    polynomial &= (1 << width) - 1
    if not polynomial & 1:
        raise ValueError("CRC polynomial must have a nonzero constant term")
    if fcs_topology not in {"serial", "balanced"}:
        raise ValueError("unknown FCS topology")

    net = Netlist(
        name=(
            f"crc_frame_residue_w{width}_p{polynomial:x}_s{symbol_bits}"
            f"_c{payload_cycles}_{fcs_topology}"
        )
    )
    data = [net.add_input() for _ in range(symbol_bits)]
    reset = (1 << width) - 1
    crc = [net.add_latch(f"crc_{index}", 0, 0) for index in range(width)]
    fcs = [net.add_latch(f"fcs_{index}", 0, 0) for index in range(width)]

    # phase[0] resets the CRC; payload phases follow; then trailer and check.
    phase_count = payload_cycles + 3
    phase = [
        net.add_latch(f"phase_{index}", 1 if index == 0 else 0, 0)
        for index in range(phase_count)
    ]
    trailer_phase = payload_cycles + 1
    check_phase = payload_cycles + 2

    payload_next = _crc_serial(net, crc, data, polynomial)
    trailer_next = _crc_serial(net, crc, fcs, polynomial)
    fcs_supports = _fcs_supports(width, polynomial)
    captured_fcs = [
        _xor_reduce(net, [payload_next[bit] for bit in sorted(support)], fcs_topology)
        for support in fcs_supports
    ]

    crc_next = list(crc)
    for index in range(width):
        reset_bit = net.const_true() if (reset >> index) & 1 else 0
        # Priority is phase0 reset, payload update, trailer update, then hold.
        next_value = _mux(net, phase[trailer_phase], trailer_next[index], crc[index])
        for payload_phase in range(payload_cycles, 0, -1):
            next_value = _mux(net, phase[payload_phase], payload_next[index], next_value)
        crc_next[index] = _mux(net, phase[0], reset_bit, next_value)
        net.latches[index] = (f"crc_{index}", crc[index], 0, crc_next[index])

    last_payload = phase[payload_cycles]
    for index in range(width):
        fcs_next = _mux(net, last_payload, captured_fcs[index], fcs[index])
        net.latches[width + index] = (f"fcs_{index}", fcs[index], 0, fcs_next)

    phase_base = 2 * width
    for index, current in enumerate(phase):
        previous = phase[index - 1] if index else phase[-1]
        net.latches[phase_base + index] = (
            f"phase_{index}", current, 1 if index == 0 else 0, previous
        )
    zero = [0] * width
    net.add_bad(net.and_gate(phase[check_phase], neq_words(net, crc, zero)))
    return net


def reference_check_crc_frame_residue(
    width: int,
    polynomial: int,
    symbol_bits: int,
    payload_cycles: int,
    fcs_topology: str = "balanced",
    **_: object,
) -> dict[str, object]:
    return {
        "expected": "SAFE",
        "invariant": "at check phase, CRC(payload followed by derived FCS) == zero",
        "protocol": "fixed-length CRC frame with delayed FCS residue check",
        "polynomial": hex(polynomial),
        "state_width": width,
        "symbol_bits_per_cycle": symbol_bits,
        "payload_cycles": payload_cycles,
        "fcs_topology": fcs_topology,
        "reset_seed": hex((1 << width) - 1),
    }
