#!/usr/bin/env python3
"""Build a frozen, depth-stratified UNSAFE affine-datapath cohort."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DEPTHS = (2, 8, 32, 128)


def build_specs() -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    for width, polynomial, standard in (
        (16, 0x1021, "CRC-16-CCITT"),
        (32, 0x04C11DB7, "CRC-32/IEEE"),
    ):
        for symbol_bits in (64, 256, 1024):
            for depth in DEPTHS:
                specs.append({
                    "family": "crc_frame_align_unsafe",
                    "category": "link-coding-unsafe",
                    "semantic": "delayed implementation fault after CRC frame alignment",
                    "source": standard,
                    "width": width,
                    "polynomial": polynomial,
                    "symbol_bits": symbol_bits,
                    "witness_depth": depth,
                    "fault_bit": (width // 3) % width,
                    "seed": 1100000 + width * 10000 + symbol_bits + depth,
                })
    for symbol_bits in (64, 256, 1024):
        for depth in DEPTHS:
            specs.append({
                "family": "scrambler_equiv_unsafe",
                "category": "link-coding-unsafe",
                "semantic": "delayed implementation fault in 64b/66b scrambler",
                "source": "IEEE 802.3 PCS polynomial 1 + x^39 + x^58",
                "symbol_bits": symbol_bits,
                "witness_depth": depth,
                "fault_bit": 17,
                "seed": 1200000 + symbol_bits + depth,
            })
    for check_bits, data_bits, row_weight in (
        (16, 128, 9),
        (32, 256, 17),
        (64, 512, 25),
    ):
        for depth in DEPTHS:
            specs.append({
                "family": "syndrome_equiv_unsafe",
                "category": "ecc-unsafe",
                "semantic": "delayed implementation fault in streaming syndrome unit",
                "source": "parameterized binary linear-code parity check",
                "check_bits": check_bits,
                "data_bits": data_bits,
                "row_weight": row_weight,
                "witness_depth": depth,
                "fault_bit": check_bits // 2,
                "seed": 1300000 + check_bits * 1000 + depth,
            })
    if len(specs) != 48:
        raise AssertionError(f"expected 48 specs, got {len(specs)}")
    return specs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    specs = build_specs()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(specs, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"models": len(specs), "depths": DEPTHS, "families": 3}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
