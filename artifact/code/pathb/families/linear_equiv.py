"""Shared helpers for serial-versus-matrix linear datapath benchmarks."""

from __future__ import annotations

from typing import Set

from ..netlist import Netlist
from .affine_equiv import _xor_reduce


Support = Set[int]


def toggle(*terms: Support) -> Support:
    result: Support = set()
    for term in terms:
        result.symmetric_difference_update(term)
    return result


def instantiate(
    net: Netlist,
    supports: list[Support],
    symbols: list[int],
    topology: str,
) -> list[int]:
    return [
        _xor_reduce(net, [symbols[index] for index in sorted(row)], topology)
        for row in supports
    ]
