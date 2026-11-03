#!/usr/bin/env python3
"""Map an exported MC invariant back to AIGER latch symbols.

The invariant format uses one-based latch indices while AIGER symbol records
use zero-based ``lN`` indices.  This report makes cross-property proof transfer
inspectable without depending on the original RTL source tree.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


CATEGORIES = (
    ("formal-monitor", ("$formal$", "$past$", "f_past_valid")),
    ("tlb", ("tlb", "context", "asid", "vpage", "p_tlb")),
    ("pending-valid", ("pending", "valid", "busy", "stalled")),
    ("bus-protocol", ("bus", "ack", "stall", "cyc", "stb", "req")),
    ("error-fault", ("err", "fault", "illegal")),
    ("address-data", ("addr", "data", "word", "page")),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aig", type=Path, required=True)
    parser.add_argument("--invariant", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def read_symbols(path: Path) -> dict[int, str]:
    symbols: dict[int, str] = {}
    with path.open("rb") as stream:
        for raw in stream:
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            match = re.match(r"^l(\d+)\s+(.*)$", line)
            if match:
                symbols[int(match.group(1)) + 1] = match.group(2)
    return symbols


def read_invariant(path: Path) -> tuple[int, list[tuple[int, ...]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split()
    if len(header) != 2 or header[0] != "mc-pdr-invariant-v1":
        raise ValueError(f"unsupported invariant: {path}")
    cubes: list[tuple[int, ...]] = []
    for line in lines[1:]:
        if not line or line[0] in "c#":
            continue
        literals = [int(value) for value in line.split()]
        if not literals or literals[-1] != 0:
            raise ValueError(f"unterminated invariant row: {line}")
        cubes.append(tuple(literals[:-1]))
    return int(header[1]), cubes


def category(name: str) -> str:
    lowered = name.lower()
    for label, needles in CATEGORIES:
        if any(needle in lowered for needle in needles):
            return label
    return "other-state"


def main() -> int:
    args = parse_args()
    symbols = read_symbols(args.aig)
    latches, cubes = read_invariant(args.invariant)
    if symbols and max(symbols) > latches:
        raise ValueError("AIGER symbol index exceeds invariant latch count")

    literal_frequency: Counter[int] = Counter()
    polarity: dict[int, Counter[str]] = defaultdict(Counter)
    category_literals: Counter[str] = Counter()
    category_clauses: Counter[str] = Counter()
    widths: Counter[int] = Counter()
    for cube in cubes:
        widths[len(cube)] += 1
        seen_categories: set[str] = set()
        for literal in cube:
            index = abs(literal)
            literal_frequency[index] += 1
            polarity[index]["positive" if literal > 0 else "negative"] += 1
            label = category(symbols.get(index, f"latch-{index - 1}"))
            category_literals[label] += 1
            seen_categories.add(label)
        category_clauses.update(seen_categories)

    top_latches = []
    for index, count in literal_frequency.most_common(40):
        top_latches.append(
            {
                "latch_literal": index,
                "aiger_symbol_index": index - 1,
                "name": symbols.get(index, f"latch-{index - 1}"),
                "category": category(symbols.get(index, "")),
                "occurrences": count,
                "positive": polarity[index]["positive"],
                "negative": polarity[index]["negative"],
            }
        )

    payload = {
        "schema": "mc-invariant-semantics-v1",
        "aig": str(args.aig),
        "invariant": str(args.invariant),
        "latches": latches,
        "clauses": len(cubes),
        "distinct_latches": len(literal_frequency),
        "width_histogram": dict(sorted(widths.items())),
        "category_literal_occurrences": dict(category_literals.most_common()),
        "category_clause_occurrences": dict(category_clauses.most_common()),
        "top_latches": top_latches,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"clauses={len(cubes)} distinct_latches={len(literal_frequency)} "
        f"top={top_latches[0]['name'] if top_latches else 'none'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
