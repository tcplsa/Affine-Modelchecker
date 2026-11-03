#!/usr/bin/env python3
"""Merge canonical latch-cube invariants emitted by the MC PDR engine."""

from __future__ import annotations

import argparse
from pathlib import Path


MAGIC = "mc-pdr-invariant-v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def cube_key(cube: tuple[int, ...]) -> tuple[int, tuple[tuple[int, int], ...]]:
    return len(cube), tuple((abs(literal), literal) for literal in cube)


def read_invariant(path: Path) -> tuple[int, set[tuple[int, ...]]]:
    lines = path.read_text(encoding="ascii").splitlines()
    if not lines:
        raise ValueError(f"empty invariant file: {path}")
    header = lines[0].split()
    if len(header) != 2 or header[0] != MAGIC:
        raise ValueError(f"invalid invariant header: {path}")
    latches = int(header[1])
    cubes: set[tuple[int, ...]] = set()
    for line_number, line in enumerate(lines[1:], 2):
        fields = line.split()
        if not fields or fields[0] in {"c", "#"}:
            continue
        literals = [int(field) for field in fields]
        if not literals or literals[-1] != 0 or 0 in literals[:-1]:
            raise ValueError(f"malformed cube at {path}:{line_number}")
        cube = tuple(sorted(set(literals[:-1]), key=lambda lit: (abs(lit), lit)))
        if not cube or any(abs(literal) > latches for literal in cube):
            raise ValueError(f"invalid latch literal at {path}:{line_number}")
        signs = {(abs(literal), literal > 0) for literal in cube}
        if any((variable, not positive) in signs for variable, positive in signs):
            continue
        cubes.add(cube)
    return latches, cubes


def main() -> int:
    args = parse_args()
    latch_count: int | None = None
    merged: set[tuple[int, ...]] = set()
    for path in args.inputs:
        latches, cubes = read_invariant(path)
        if latch_count is None:
            latch_count = latches
        elif latch_count != latches:
            raise ValueError(
                f"latch count mismatch: {path} has {latches}, expected {latch_count}"
            )
        merged.update(cubes)

    if latch_count is None:
        raise ValueError("no input invariants")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="ascii") as output:
        output.write(f"{MAGIC} {latch_count}\n")
        output.write(f"c merged_sources={len(args.inputs)} unique_cubes={len(merged)}\n")
        for cube in sorted(merged, key=cube_key):
            output.write(" ".join(map(str, cube)))
            output.write(" 0\n")
    print(f"sources={len(args.inputs)} latches={latch_count} cubes={len(merged)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
