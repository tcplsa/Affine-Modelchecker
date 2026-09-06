"""Sequential multiply-accumulate equivalence across multiplier trees."""

from __future__ import annotations

from ..netlist import Netlist
from .adders import _full_adder
from .word_ops import add_word, neq_words


def _partial_rows(net: Netlist, left: list[int], right: list[int]) -> list[list[int]]:
    width = len(left)
    output_width = 2 * width
    rows = []
    for right_bit in range(width):
        row = [0] * output_width
        for left_bit in range(width):
            row[left_bit + right_bit] = net.and_gate(left[left_bit], right[right_bit])
        rows.append(row)
    return rows


def _schoolbook(
    net: Netlist, left: list[int], right: list[int], add_struct: str
) -> list[int]:
    rows = _partial_rows(net, left, right)
    result = [0] * (2 * len(left))
    for row in rows:
        result = add_word(net, result, row, add_struct)
    return result


def _compress_three(
    net: Netlist, first: list[int], second: list[int], third: list[int]
) -> tuple[list[int], list[int]]:
    width = len(first)
    summed = [0] * width
    carry = [0] * width
    for index in range(width):
        summed[index], carry_out = _full_adder(
            net, first[index], second[index], third[index]
        )
        if index + 1 < width:
            carry[index + 1] = carry_out
    return summed, carry


def _wallace(
    net: Netlist, left: list[int], right: list[int], final_struct: str
) -> list[int]:
    rows = _partial_rows(net, left, right)
    while len(rows) > 2:
        reduced = []
        index = 0
        while index + 2 < len(rows):
            reduced.extend(_compress_three(net, rows[index], rows[index + 1], rows[index + 2]))
            index += 3
        reduced.extend(rows[index:])
        rows = reduced
    if len(rows) == 1:
        return rows[0]
    return add_word(net, rows[0], rows[1], final_struct)


def _multiply(
    net: Netlist,
    left: list[int],
    right: list[int],
    multiplier: str,
    add_struct: str,
) -> list[int]:
    if multiplier == "schoolbook":
        return _schoolbook(net, left, right, add_struct)
    if multiplier == "wallace":
        return _wallace(net, left, right, add_struct)
    raise ValueError("unknown multiplier structure")


def generate_mac_equiv(
    width: int = 8,
    left_multiplier: str = "schoolbook",
    right_multiplier: str = "wallace",
    left_adder: str = "ripple",
    right_adder: str = "prefix",
    seed: int = 0,
) -> Netlist:
    del seed
    if width < 2:
        raise ValueError("MAC operand width must be >= 2")
    output_width = 2 * width
    net = Netlist(
        name=(f"mac_equiv_{left_multiplier}_{left_adder}_"
              f"{right_multiplier}_{right_adder}_w{width}")
    )
    multiplicand = [net.add_input() for _ in range(width)]
    multiplier = [net.add_input() for _ in range(width)]
    left = [net.add_latch(f"mac_left_{i}", 0, 0) for i in range(output_width)]
    right = [net.add_latch(f"mac_right_{i}", 0, 0) for i in range(output_width)]
    left_product = _multiply(
        net, multiplicand, multiplier, left_multiplier, left_adder
    )
    right_product = _multiply(
        net, multiplicand, multiplier, right_multiplier, right_adder
    )
    left_next = add_word(net, left, left_product, left_adder)
    right_next = add_word(net, right, right_product, right_adder)
    for index in range(output_width):
        net.latches[index] = (f"mac_left_{index}", left[index], 0, left_next[index])
        net.latches[output_width + index] = (
            f"mac_right_{index}", right[index], 0, right_next[index]
        )
    net.add_bad(neq_words(net, left, right))
    return net


def reference_check_mac_equiv(
    width: int,
    left_multiplier: str,
    right_multiplier: str,
    left_adder: str,
    right_adder: str,
    **_: object,
) -> dict[str, object]:
    return {
        "expected": "SAFE",
        "invariant": "multiply-accumulate results remain equal modulo 2^(2*width)",
        "operand_width": width,
        "left_multiplier": left_multiplier,
        "right_multiplier": right_multiplier,
        "left_adder": left_adder,
        "right_adder": right_adder,
    }

