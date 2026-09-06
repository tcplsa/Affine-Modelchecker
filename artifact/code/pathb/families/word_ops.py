"""Shared bit-vector operations for semantic Path-B circuit families."""

from __future__ import annotations

from ..netlist import Netlist
from .adders import _add
from .affine_equiv import _xor_reduce


def xor_word(net: Netlist, *words: list[int], topology: str = "balanced") -> list[int]:
    if not words:
        return []
    width = len(words[0])
    if any(len(word) != width for word in words):
        raise ValueError("word widths differ")
    return [
        _xor_reduce(net, [word[index] for word in words], topology)
        for index in range(width)
    ]


def rotate_left(word: list[int], amount: int) -> list[int]:
    width = len(word)
    amount %= width
    return [word[(index - amount) % width] for index in range(width)]


def rotate_right(word: list[int], amount: int) -> list[int]:
    return rotate_left(word, -amount)


def add_word(net: Netlist, left: list[int], right: list[int], struct: str) -> list[int]:
    result, _carry = _add(net, struct, left, right)
    return result


def neq_words(net: Netlist, left: list[int], right: list[int]) -> int:
    if len(left) != len(right) or not left:
        raise ValueError("non-empty equal-width words required")
    differences = [net.xor_gate(a, b) for a, b in zip(left, right)]
    value = differences[0]
    for difference in differences[1:]:
        value = net.or_gate(value, difference)
    return value


def neq_states(net: Netlist, left: list[list[int]], right: list[list[int]]) -> int:
    if len(left) != len(right) or not left:
        raise ValueError("non-empty equal-shape states required")
    differences = [neq_words(net, a, b) for a, b in zip(left, right)]
    value = differences[0]
    for difference in differences[1:]:
        value = net.or_gate(value, difference)
    return value

