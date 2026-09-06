"""Sequential equivalence for Keccak-f theta-rho-pi linear layers."""

from __future__ import annotations

import random

from ..netlist import Netlist
from .affine_equiv import _xor_reduce
from .word_ops import neq_words, rotate_left, xor_word


RHO_OFFSETS = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)


def _lane(state: list[int], width: int, x: int, y: int) -> list[int]:
    offset = (x + 5 * y) * width
    return state[offset:offset + width]


def _linear_round(net: Netlist, state: list[int], width: int, topology: str) -> list[int]:
    parity = []
    for x in range(5):
        parity.append([
            _xor_reduce(
                net,
                [_lane(state, width, x, y)[bit] for y in range(5)],
                topology,
            )
            for bit in range(width)
        ])
    theta = [[None for _y in range(5)] for _x in range(5)]
    for x in range(5):
        delta = xor_word(
            net,
            parity[(x - 1) % 5],
            rotate_left(parity[(x + 1) % 5], 1),
            topology=topology,
        )
        for y in range(5):
            theta[x][y] = xor_word(
                net, _lane(state, width, x, y), delta, topology=topology
            )
    output = [[None for _y in range(5)] for _x in range(5)]
    for x in range(5):
        for y in range(5):
            out_x = y
            out_y = (2 * x + 3 * y) % 5
            output[out_x][out_y] = rotate_left(theta[x][y], RHO_OFFSETS[x][y])
    flattened = []
    for y in range(5):
        for x in range(5):
            flattened.extend(output[x][y])
    return flattened


def generate_keccak_linear_equiv(
    lane_width: int = 4,
    rounds: int = 1,
    left_topology: str = "serial",
    right_topology: str = "balanced",
    input_bits: int = 8,
    seed: int = 0,
) -> Netlist:
    if lane_width < 2 or rounds < 1:
        raise ValueError("invalid Keccak dimensions")
    width = 25 * lane_width
    net = Netlist(name=f"keccak_theta_rho_pi_w{lane_width}_r{rounds}")
    inputs = [net.add_input() for _ in range(input_bits)]
    rng = random.Random(seed ^ 0xCECACC)
    initial = rng.getrandbits(width)
    left = [net.add_latch(f"keccak_serial_{i}", (initial >> i) & 1, 0) for i in range(width)]
    right = [net.add_latch(f"keccak_tree_{i}", (initial >> i) & 1, 0) for i in range(width)]
    left_next, right_next = list(left), list(right)
    for round_index in range(rounds):
        if inputs:
            injection = [inputs[(index + round_index) % len(inputs)] for index in range(width)]
            left_next = xor_word(net, left_next, injection, topology=left_topology)
            right_next = xor_word(net, right_next, injection, topology=right_topology)
        left_next = _linear_round(net, left_next, lane_width, left_topology)
        right_next = _linear_round(net, right_next, lane_width, right_topology)
    for index in range(width):
        net.latches[index] = (
            f"keccak_serial_{index}", left[index], (initial >> index) & 1, left_next[index]
        )
        net.latches[width + index] = (
            f"keccak_tree_{index}", right[index], (initial >> index) & 1, right_next[index]
        )
    net.add_bad(neq_words(net, left, right))
    return net


def reference_check_keccak_linear_equiv(
    lane_width: int, rounds: int, **_: object
) -> dict[str, object]:
    return {
        "expected": "SAFE",
        "invariant": "serial and balanced Keccak linear layers remain equivalent",
        "standard": "FIPS 202 Keccak-f theta, rho, and pi steps (chi/iota omitted)",
        "lane_width": lane_width,
        "rounds_per_transition": rounds,
    }

