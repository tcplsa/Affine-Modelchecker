#!/usr/bin/env python3
"""Frozen scale-margin suite for affine transition summaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def specs() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for steps in (768, 1024, 1536, 2048, 3072):
        result.append({
            "family": "lfsr_jump_equiv", "category": "prbs",
            "semantic": "PRBS31 jump-ahead scale margin", "standard": "PRBS31",
            "width": 31, "steps": steps, "taps": [30, 27],
            "seed": 1_410_000 + steps,
        })
    for symbol_bits in (768, 1024, 1536, 2048):
        result.append({
            "family": "scrambler_equiv", "category": "link-coding",
            "semantic": "64b/66b parallel scrambler scale margin",
            "standard": "IEEE 802.3 polynomial 1 + x^39 + x^58",
            "symbol_bits": symbol_bits, "seed": 1_420_000 + symbol_bits,
        })
    for width, polynomial, standard, widths in (
        (16, 0x1021, "CRC-16-CCITT", (768, 1024, 1536)),
        (32, 0x04C11DB7, "CRC-32-IEEE", (304, 320, 384, 512)),
        (64, 0x42F0E1EBA9EA3693, "CRC-64-ECMA", (120, 124, 160, 256)),
    ):
        for symbol_bits in widths:
            result.append({
                "family": "crc_frame_align", "category": "link-coding",
                "semantic": "serial versus parallel CRC scale margin",
                "standard": standard, "width": width, "polynomial": polynomial,
                "symbol_bits": symbol_bits,
                "seed": 1_430_000 + width * 1000 + symbol_bits,
            })
    for data_bits in (768, 1024, 1536, 2048):
        result.append({
            "family": "syndrome_equiv", "category": "ecc",
            "semantic": "dense streaming syndrome scale margin",
            "standard": "generic-full-rank-dense", "check_bits": 32,
            "data_bits": data_bits, "row_weight": data_bits // 4 + 1,
            "seed": 1_440_000 + data_bits,
        })
    for width, rounds, delay in (
        (20, 3, 3), (24, 3, 3), (28, 3, 3),
        (32, 3, 3), (24, 4, 3), (32, 4, 3),
    ):
        result.append({
            "family": "affine_phase_sync", "category": "controlled-affine",
            "semantic": "delayed affine synchronization control boundary",
            "width": width, "weight": 9, "rounds": rounds, "delay": delay,
            "inputs": 4, "topology": "balanced",
            "seed": 1_450_000 + width + 100 * rounds + 1000 * delay,
        })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    models = specs()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(models, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"models": len(models), "families": 5}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

