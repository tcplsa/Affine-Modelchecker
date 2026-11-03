#!/usr/bin/env python3
"""Remap a canonical latch invariant between AIGER builds by symbol name."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from analyze_aig_deep_structure import Aag, BinaryAig
from analyze_invariant_semantics import read_invariant, read_symbols


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-aig", type=Path, required=True)
    parser.add_argument("--target-aig", type=Path, required=True)
    parser.add_argument("--invariant", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def unique_reverse(symbols: dict[int, str]) -> tuple[dict[str, int], set[str]]:
    counts = Counter(symbols.values())
    duplicate = {name for name, count in counts.items() if count != 1}
    return ({name: index for index, name in symbols.items() if name not in duplicate}, duplicate)


def read_input_symbols(path: Path) -> dict[int, str]:
    symbols: dict[int, str] = {}
    with path.open("rb") as stream:
        for raw in stream:
            match = re.match(rb"^i(\d+)\s+(.*)$", raw.rstrip())
            if match:
                symbols[int(match.group(1)) + 1] = match.group(2).decode(
                    "utf-8", errors="replace"
                )
    return symbols


def digest(tag: bytes, *values: bytes) -> bytes:
    state = hashlib.sha256()
    state.update(tag)
    for value in values:
        state.update(len(value).to_bytes(4, "big"))
        state.update(value)
    return state.digest()


def structural_latch_colors(path: Path, rounds: int = 8) -> dict[int, bytes]:
    parser = Aag if path.suffix == ".aag" else BinaryAig
    aig = parser(path)
    latch_names = read_symbols(path)
    input_names = read_input_symbols(path)
    colors = {
        index: digest(b"latch-name", name.encode("utf-8"))
        if (name := latch_names.get(index)) is not None
        else digest(b"latch-unnamed")
        for index in range(1, aig.latches + 1)
    }

    for _ in range(rounds):
        nodes: list[bytes] = [b""] * (aig.maxvar + 1)
        nodes[0] = digest(b"constant")
        for index in range(1, aig.inputs + 1):
            name = input_names.get(index)
            nodes[index] = digest(
                b"input-name" if name is not None else b"input-unnamed",
                name.encode("utf-8") if name is not None else b"",
            )
        for index in range(1, aig.latches + 1):
            nodes[aig.inputs + index] = colors[index]

        def literal_color(literal: int) -> bytes:
            base = nodes[literal >> 1]
            return digest(b"not", base) if literal & 1 else base

        for variable in range(aig.gate_start, aig.maxvar + 1):
            if not aig.is_gate(variable):
                continue
            children = sorted(
                (literal_color(aig.left[variable]), literal_color(aig.right[variable]))
            )
            nodes[variable] = digest(b"and", children[0], children[1])
        updated = dict(colors)
        for index in range(1, aig.latches + 1):
            if index not in latch_names:
                updated[index] = digest(
                    b"next-state", literal_color(aig.next_lits[index - 1])
                )
        if updated == colors:
            break
        colors = updated
    return colors


def main() -> int:
    args = parse_args()
    source_symbols = read_symbols(args.source_aig)
    target_symbols = read_symbols(args.target_aig)
    target_by_name, target_duplicates = unique_reverse(target_symbols)
    # The source invariant header belongs to the source model; target size is
    # read from its AIGER symbol range/header below.
    with args.target_aig.open("rb") as stream:
        header = stream.readline().decode("ascii").split()
    target_latches = int(header[3])

    _, cubes = read_invariant(args.invariant)
    source_colors = structural_latch_colors(args.source_aig)
    target_colors = structural_latch_colors(args.target_aig)
    source_color_counts = Counter(source_colors.values())
    target_color_counts = Counter(target_colors.values())
    target_by_color = {
        color: index
        for index, color in target_colors.items()
        if target_color_counts[color] == 1
    }
    structural_map = {
        index: target_by_color[color]
        for index, color in source_colors.items()
        if index not in source_symbols
        and source_color_counts[color] == 1
        and color in target_by_color
        and target_by_color[color] not in target_symbols
    }
    mapped: set[tuple[int, ...]] = set()
    dropped_missing = 0
    dropped_duplicate = 0
    for cube in cubes:
        translated: list[int] = []
        valid = True
        for literal in cube:
            name = source_symbols.get(abs(literal))
            if name is None and abs(literal) in structural_map:
                index = structural_map[abs(literal)]
                translated.append(index if literal > 0 else -index)
                continue
            if name is None or name not in target_by_name:
                valid = False
                if name in target_duplicates:
                    dropped_duplicate += 1
                else:
                    dropped_missing += 1
                break
            index = target_by_name[name]
            translated.append(index if literal > 0 else -index)
        if valid:
            canonical = tuple(sorted(set(translated), key=lambda value: (abs(value), value)))
            if canonical:
                mapped.add(canonical)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="ascii") as stream:
        stream.write(f"mc-pdr-invariant-v1 {target_latches}\n")
        stream.write(
            f"c symbol-remapped source_clauses={len(cubes)} "
            f"mapped_clauses={len(mapped)}\n"
        )
        for cube in sorted(mapped, key=lambda row: (len(row), row)):
            stream.write(" ".join(map(str, cube)) + " 0\n")

    report = {
        "schema": "pdr-invariant-symbol-remap-v1",
        "source_aig": str(args.source_aig),
        "target_aig": str(args.target_aig),
        "source_invariant": str(args.invariant),
        "source_clauses": len(cubes),
        "mapped_clauses": len(mapped),
        "source_named_latches": len(source_symbols),
        "target_named_latches": len(target_symbols),
        "common_unique_names": len(set(source_symbols.values()) & set(target_by_name)),
        "structurally_mapped_unnamed_latches": len(structural_map),
        "dropped_missing_literal": dropped_missing,
        "dropped_duplicate_literal": dropped_duplicate,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
