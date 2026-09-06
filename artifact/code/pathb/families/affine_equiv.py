"""Dense affine-equivalence safety family for native-XOR PDR studies.

Two independently instantiated state vectors receive the same affine update.
The reachable-state invariant is the clause-friendly relation ``left == right``;
proving its preservation, however, requires reasoning through two dense XOR
networks.  This separates SAT-side affine reasoning from lemma expressiveness.
"""

from __future__ import annotations

import random

from ..netlist import Netlist


def _xor_reduce(net: Netlist, terms: list[int], topology: str) -> int:
    if not terms:
        return 0
    if len(terms) == 1:
        return terms[0]
    if topology == "serial":
        value = terms[0]
        for term in terms[1:]:
            value = net.xor_gate(value, term)
        return value
    if topology == "balanced":
        level = list(terms)
        while len(level) > 1:
            next_level: list[int] = []
            for index in range(0, len(level), 2):
                if index + 1 == len(level):
                    next_level.append(level[index])
                else:
                    next_level.append(net.xor_gate(level[index], level[index + 1]))
            level = next_level
        return level[0]
    raise ValueError(f"unknown XOR topology: {topology}")


def _matrix(width: int, weight: int, seed: int) -> list[list[int]]:
    rng = random.Random(seed)
    weight = max(2, min(weight, width))
    rows: list[list[int]] = []
    for row in range(width):
        # Include the diagonal to keep every old state bit locally relevant,
        # then choose the remaining support deterministically from the row seed.
        candidates = [index for index in range(width) if index != row]
        support = [row, *rng.sample(candidates, weight - 1)]
        rows.append(sorted(support))
    return rows


def _apply_round(
    net: Netlist,
    state: list[int],
    inputs: list[int],
    rows: list[list[int]],
    topology: str,
    input_stride: int,
) -> list[int]:
    result = []
    for row, support in enumerate(rows):
        terms = [state[index] for index in support]
        if inputs and row % input_stride == 0:
            terms.append(inputs[row % len(inputs)])
        result.append(_xor_reduce(net, terms, topology))
    return result


def generate_affine_equiv(
    width: int = 16,
    weight: int = 8,
    rounds: int = 1,
    inputs: int = 4,
    topology: str = "balanced",
    seed: int = 0,
) -> Netlist:
    """Generate a SAFE dense-affine equivalence transition system."""
    if width < 2:
        raise ValueError("width must be >= 2")
    if rounds < 1:
        raise ValueError("rounds must be >= 1")
    if inputs < 0:
        raise ValueError("inputs must be non-negative")

    net = Netlist(name=f"affine_equiv_w{width}_k{weight}_r{rounds}")
    primary_inputs = [net.add_input() for _ in range(inputs)]
    rng = random.Random(seed ^ 0xA771_1E)
    initial = [rng.getrandbits(1) for _ in range(width)]
    left = [net.add_latch(f"left_{i}", initial[i], 0) for i in range(width)]
    right = [net.add_latch(f"right_{i}", initial[i], 0) for i in range(width)]

    left_next = list(left)
    right_next = list(right)
    for round_index in range(rounds):
        rows = _matrix(width, weight, seed + round_index * 1_000_003)
        # The calls intentionally allocate distinct gate networks.  Structural
        # sharing would let Tseitin propagation prove equivalence trivially.
        left_next = _apply_round(
            net, left_next, primary_inputs, rows, topology, input_stride=3
        )
        right_next = _apply_round(
            net, right_next, primary_inputs, rows, topology, input_stride=3
        )

    for index in range(width):
        net.latches[index] = (
            f"left_{index}", left[index], initial[index], left_next[index]
        )
        net.latches[width + index] = (
            f"right_{index}", right[index], initial[index], right_next[index]
        )

    differences = [net.xor_gate(left[i], right[i]) for i in range(width)]
    bad = differences[0]
    for difference in differences[1:]:
        bad = net.or_gate(bad, difference)
    net.add_bad(bad)
    return net


def reference_check_affine_equiv(**_: object) -> dict[str, object]:
    return {
        "expected": "SAFE",
        "invariant": "left[i] == right[i] for every state bit",
    }
