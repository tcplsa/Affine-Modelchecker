#!/usr/bin/env python3
"""Refine the three pure-Gaussian CRC phase-transition boundaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def specs() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    regions = (
        # CRC-16 still solved at 256 bits/transition in the coarse sweep.
        (16, 0x1021, "CRC-16-CCITT", (320, 384, 448, 512, 640, 768, 1024)),
        # CRC-32 solved at 256 and timed out at 384.
        (32, 0x04C11DB7, "CRC-32/IEEE", (272, 288, 304, 320, 336, 352, 368)),
        # CRC-64 solved at 96 and timed out at 128.
        (64, 0x42F0E1EBA9EA3693, "CRC-64/ECMA-182", (100, 104, 108, 112, 116, 120, 124)),
    )
    for width, polynomial, source, symbol_sizes in regions:
        for symbol_bits in symbol_sizes:
            result.append({
                "family": "crc_frame_align",
                "category": "link-coding",
                "semantic": "serial/matrix CRC alignment after a frame boundary",
                "source": source,
                "width": width,
                "polynomial": polynomial,
                "symbol_bits": symbol_bits,
                "seed": 986000 + width * 1000 + symbol_bits,
            })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    models = specs()
    if len(models) != 21:
        raise AssertionError(f"expected 21 specs, got {len(models)}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(models, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"models": len(models), "families": 3}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
