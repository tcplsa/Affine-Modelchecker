"""Multi-frame affine synchronization with a clause-friendly invariant.

The data path remains affine in every phase.  A one-hot phase register injects
precomputed correction vectors so that the left/right difference follows a
chosen nonzero trajectory and becomes exactly zero when ``done`` is asserted.
Unlike ``affine_warmup``, this family has no per-bit muxes in the transition
relation, preserving a large GF(2) subsystem for native Gaussian reasoning.
"""

from __future__ import annotations

import random

from ..netlist import Netlist
from .affine_equiv import _apply_round


def gf2_rank(rows: list[list[int]], width: int) -> int:
    """Return the rank of a binary matrix represented by column supports."""
    basis: dict[int, int] = {}
    for support in rows:
        value = 0
        for column in support:
            value ^= 1 << column
        while value:
            pivot = value.bit_length() - 1
            if pivot in basis:
                value ^= basis[pivot]
            else:
                basis[pivot] = value
                break
    return len(basis)


def full_rank_matrix(
    width: int, weight: int, seed: int, max_attempts: int = 4096
) -> list[list[int]]:
    """Generate a deterministic full-rank fixed-row-weight GF(2) matrix."""
    if width < 2:
        raise ValueError("width must be >= 2")
    if weight < 1 or weight > width:
        raise ValueError("weight must be between 1 and width")
    if weight % 2 == 0:
        raise ValueError(
            "weight must be odd; even row parity makes the all-one vector null"
        )
    if weight == width and width > 1:
        raise ValueError("weight=width produces identical rows")
    if weight == 1:
        order = list(range(width))
        random.Random(seed).shuffle(order)
        return [[column] for column in order]

    rng = random.Random(seed)
    columns = list(range(width))
    for _ in range(max_attempts):
        rows = [sorted(rng.sample(columns, weight)) for _ in range(width)]
        if gf2_rank(rows, width) == width:
            return rows
    raise ValueError(
        f"failed to construct a full-rank width={width} weight={weight} matrix"
    )


def _apply_matrix_bits(rows: list[list[int]], bits: list[int]) -> list[int]:
    return [sum(bits[column] for column in support) & 1 for support in rows]


def _random_nonzero_bits(rng: random.Random, width: int) -> list[int]:
    while True:
        bits = [rng.getrandbits(1) for _ in range(width)]
        if any(bits):
            return bits


def generate_affine_phase_sync(
    width: int = 16,
    weight: int = 9,
    rounds: int = 2,
    delay: int = 3,
    inputs: int = 4,
    topology: str = "balanced",
    seed: int = 0,
) -> Netlist:
    """Generate a SAFE affine system whose equality activates after delay frames."""
    if rounds < 1:
        raise ValueError("rounds must be >= 1")
    if delay < 2:
        raise ValueError("delay must be >= 2")
    if inputs < 0:
        raise ValueError("inputs must be non-negative")

    matrices = [
        full_rank_matrix(width, weight, seed + index * 1_000_003)
        for index in range(rounds)
    ]
    rng = random.Random(seed ^ 0xA771_5A9C)
    left_init = [rng.getrandbits(1) for _ in range(width)]
    differences = [_random_nonzero_bits(rng, width) for _ in range(delay)]
    differences.append([0] * width)
    right_init = [left_init[i] ^ differences[0][i] for i in range(width)]

    def composed(bits: list[int]) -> list[int]:
        value = bits
        for rows in matrices:
            value = _apply_matrix_bits(rows, value)
        return value

    corrections = []
    for phase in range(delay):
        transformed = composed(differences[phase])
        correction = [
            transformed[index] ^ differences[phase + 1][index]
            for index in range(width)
        ]
        corrections.append(correction)

    # Construction-time symbolic check of the intended reachable difference.
    value = differences[0]
    for phase, correction in enumerate(corrections):
        value = [a ^ b for a, b in zip(composed(value), correction)]
        assert value == differences[phase + 1]

    net = Netlist(name=f"affine_phase_sync_w{width}_k{weight}_r{rounds}_d{delay}")
    primary_inputs = [net.add_input() for _ in range(inputs)]
    left = [net.add_latch(f"left_{i}", left_init[i], 0) for i in range(width)]
    right = [net.add_latch(f"right_{i}", right_init[i], 0) for i in range(width)]
    phase = [
        net.add_latch(f"phase_{index}", int(index == 0), 0)
        for index in range(delay)
    ]
    done = net.add_latch("done", 0, 0)

    left_next = list(left)
    right_next = list(right)
    for rows in matrices:
        left_next = _apply_round(
            net, left_next, primary_inputs, rows, topology, input_stride=3
        )
        right_next = _apply_round(
            net, right_next, primary_inputs, rows, topology, input_stride=3
        )

    for phase_index, correction in enumerate(corrections):
        for bit, enabled in enumerate(correction):
            if enabled:
                right_next[bit] = net.xor_gate(right_next[bit], phase[phase_index])

    for index in range(width):
        net.latches[index] = (
            f"left_{index}", left[index], left_init[index], left_next[index]
        )
        net.latches[width + index] = (
            f"right_{index}", right[index], right_init[index], right_next[index]
        )

    phase_offset = 2 * width
    net.latches[phase_offset] = ("phase_0", phase[0], 1, 0)
    for index in range(1, delay):
        net.latches[phase_offset + index] = (
            f"phase_{index}", phase[index], 0, phase[index - 1]
        )
    net.latches[phase_offset + delay] = (
        "done", done, 0, net.or_gate(done, phase[-1])
    )

    differences_now = [net.xor_gate(left[i], right[i]) for i in range(width)]
    any_difference = differences_now[0]
    for difference in differences_now[1:]:
        any_difference = net.or_gate(any_difference, difference)
    net.add_bad(net.and_gate(done, any_difference))
    return net


def reference_check_affine_phase_sync(
    width: int = 16,
    weight: int = 9,
    rounds: int = 2,
    delay: int = 3,
    seed: int = 0,
    **_: object,
) -> dict[str, object]:
    matrices = [
        full_rank_matrix(width, weight, seed + index * 1_000_003)
        for index in range(rounds)
    ]
    return {
        "expected": "SAFE",
        "invariant": "done implies left[i] == right[i] for every state bit",
        "first_enabled_step": delay,
        "matrix_ranks": [gf2_rank(rows, width) for rows in matrices],
    }
