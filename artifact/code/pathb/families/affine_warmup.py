"""Multi-frame affine-equivalence safety family for native-XOR PDR studies."""

from __future__ import annotations

import random

from ..netlist import Netlist
from .affine_equiv import _apply_round, _matrix


def _mux(net: Netlist, select: int, when_true: int, when_false: int) -> int:
    """Return select ? when_true : when_false using AIG-compatible gates."""
    positive = net.and_gate(select, when_true)
    negative = net.and_gate(net.not_gate(select), when_false)
    return net.or_gate(positive, negative)


def generate_affine_warmup(
    width: int = 16,
    weight: int = 8,
    rounds: int = 2,
    delay: int = 4,
    inputs: int = 4,
    topology: str = "balanced",
    seed: int = 0,
) -> Netlist:
    """Generate SAFE delayed equality after a synchronization transition.

    The two state vectors start different. On the initial transition both are
    reset to the same input-derived image; later transitions use independent
    copies of the same dense affine network. A delay-stage valid shift register
    gates the equality property, forcing PDR to traverse a phase chain before
    the safety condition becomes active.
    """
    if width < 2:
        raise ValueError("width must be >= 2")
    if rounds < 1:
        raise ValueError("rounds must be >= 1")
    if delay < 2:
        raise ValueError("delay must be >= 2")
    if inputs < 1:
        raise ValueError("inputs must be >= 1")

    net = Netlist(name=f"affine_warmup_w{width}_k{weight}_r{rounds}_d{delay}")
    primary_inputs = [net.add_input() for _ in range(inputs)]
    rng = random.Random(seed ^ 0xA771_9D)
    left_init = [rng.getrandbits(1) for _ in range(width)]
    right_init = [1 - bit for bit in left_init]
    left = [net.add_latch(f"left_{i}", left_init[i], 0) for i in range(width)]
    right = [net.add_latch(f"right_{i}", right_init[i], 0) for i in range(width)]
    valid = [net.add_latch(f"valid_{i}", 0, 0) for i in range(delay)]

    left_next = list(left)
    right_next = list(right)
    for round_index in range(rounds):
        rows = _matrix(width, weight, seed + round_index * 1_000_003)
        left_next = _apply_round(
            net, left_next, primary_inputs, rows, topology, input_stride=3
        )
        right_next = _apply_round(
            net, right_next, primary_inputs, rows, topology, input_stride=3
        )

    reset_image = [primary_inputs[index % len(primary_inputs)] for index in range(width)]
    for index in range(width):
        net.latches[index] = (
            f"left_{index}", left[index], left_init[index],
            _mux(net, valid[0], left_next[index], reset_image[index]),
        )
        net.latches[width + index] = (
            f"right_{index}", right[index], right_init[index],
            _mux(net, valid[0], right_next[index], reset_image[index]),
        )

    one = net.const_true()
    net.latches[2 * width] = ("valid_0", valid[0], 0, one)
    for index in range(1, delay):
        net.latches[2 * width + index] = (
            f"valid_{index}", valid[index], 0, valid[index - 1]
        )

    any_difference = None
    for index in range(width):
        difference = net.xor_gate(left[index], right[index])
        any_difference = (
            difference if any_difference is None else net.or_gate(any_difference, difference)
        )
    net.add_bad(net.and_gate(valid[-1], any_difference))
    return net


def reference_check_affine_warmup(delay: int = 4, **_: object) -> dict[str, object]:
    return {
        "expected": "SAFE",
        "invariant": "valid[i] implies left == right after synchronization",
        "first_enabled_step": delay,
    }
