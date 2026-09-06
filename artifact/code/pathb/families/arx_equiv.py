"""Sequential equivalence for ChaCha- and Speck-style ARX rounds."""

from __future__ import annotations

import random

from ..netlist import Netlist
from .word_ops import add_word, neq_states, rotate_left, rotate_right, xor_word


def _scaled_rotation(constant: int, width: int) -> int:
    if width == 32:
        return constant
    return max(1, min(width - 1, round(constant * width / 32)))


def _chacha_quarter_round(
    net: Netlist, words: list[list[int]], struct: str
) -> list[list[int]]:
    a, b, c, d = words
    r16, r12, r8, r7 = [_scaled_rotation(value, len(a)) for value in (16, 12, 8, 7)]
    a = add_word(net, a, b, struct)
    d = rotate_left(xor_word(net, d, a), r16)
    c = add_word(net, c, d, struct)
    b = rotate_left(xor_word(net, b, c), r12)
    a = add_word(net, a, b, struct)
    d = rotate_left(xor_word(net, d, a), r8)
    c = add_word(net, c, d, struct)
    b = rotate_left(xor_word(net, b, c), r7)
    return [a, b, c, d]


def _speck_round(
    net: Netlist, words: list[list[int]], key: list[int], struct: str
) -> list[list[int]]:
    x, y = words
    alpha, beta = ((7, 2) if len(x) <= 16 else (8, 3))
    x = xor_word(net, add_word(net, rotate_right(x, alpha), y, struct), key)
    y = xor_word(net, rotate_left(y, beta), x)
    return [x, y]


def generate_arx_equiv(
    primitive: str = "chacha",
    width: int = 16,
    rounds: int = 1,
    left_struct: str = "ripple",
    right_struct: str = "prefix",
    seed: int = 0,
) -> Netlist:
    if width < 4 or rounds < 1 or left_struct == right_struct:
        raise ValueError("invalid ARX parameters")
    if primitive not in {"chacha", "speck"}:
        raise ValueError("primitive must be chacha or speck")
    word_count = 4 if primitive == "chacha" else 2
    net = Netlist(name=f"arx_{primitive}_{left_struct}_{right_struct}_w{width}_r{rounds}")
    key = [net.add_input() for _ in range(width)]
    rng = random.Random(seed ^ 0xA4A)
    initial_words = [rng.getrandbits(width) for _ in range(word_count)]
    left = [
        [net.add_latch(f"arx_left_{word}_{bit}", (initial_words[word] >> bit) & 1, 0)
         for bit in range(width)]
        for word in range(word_count)
    ]
    right = [
        [net.add_latch(f"arx_right_{word}_{bit}", (initial_words[word] >> bit) & 1, 0)
         for bit in range(width)]
        for word in range(word_count)
    ]
    left_next = [list(word) for word in left]
    right_next = [list(word) for word in right]
    for _ in range(rounds):
        if primitive == "chacha":
            left_next[1] = xor_word(net, left_next[1], key)
            right_next[1] = xor_word(net, right_next[1], key)
            left_next = _chacha_quarter_round(net, left_next, left_struct)
            right_next = _chacha_quarter_round(net, right_next, right_struct)
        else:
            left_next = _speck_round(net, left_next, key, left_struct)
            right_next = _speck_round(net, right_next, key, right_struct)

    flat_left = [bit for word in left for bit in word]
    flat_right = [bit for word in right for bit in word]
    flat_left_next = [bit for word in left_next for bit in word]
    flat_right_next = [bit for word in right_next for bit in word]
    for index, current in enumerate(flat_left):
        bit = index % width
        word = index // width
        net.latches[index] = (
            f"arx_left_{word}_{bit}", current,
            (initial_words[word] >> bit) & 1, flat_left_next[index]
        )
    offset = len(flat_left)
    for index, current in enumerate(flat_right):
        bit = index % width
        word = index // width
        net.latches[offset + index] = (
            f"arx_right_{word}_{bit}", current,
            (initial_words[word] >> bit) & 1, flat_right_next[index]
        )
    net.add_bad(neq_states(net, left, right))
    return net


def reference_check_arx_equiv(
    primitive: str,
    width: int,
    rounds: int,
    left_struct: str,
    right_struct: str,
    **_: object,
) -> dict[str, object]:
    standard = (
        "RFC 8439 ChaCha quarter-round structure; rotations scaled for reduced widths"
        if primitive == "chacha" else
        "Speck ARX round structure; reduced word widths are verification variants"
    )
    return {
        "expected": "SAFE",
        "invariant": "ARX states using distinct adder structures remain equal",
        "primitive": primitive,
        "standard": standard,
        "width": width,
        "rounds_per_transition": rounds,
        "left_struct": left_struct,
        "right_struct": right_struct,
    }

