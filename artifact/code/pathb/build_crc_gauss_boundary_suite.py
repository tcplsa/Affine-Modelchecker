#!/usr/bin/env python3
"""Freeze a pure-backend CRC affine-boundary sweep.

The sweep only varies standard CRC polynomial width and the number of payload
bits handled in one transition.  It intentionally keeps the PDR policy and
serial-versus-matrix frame-alignment property fixed, so a SAT-backend phase
transition cannot be attributed to a portfolio mix or a heuristic change.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def specs() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    families = (
        (16, 0x1021, "CRC-16-CCITT", (32, 64, 96, 128, 192, 256)),
        (32, 0x04C11DB7, "CRC-32/IEEE", (8, 16, 32, 64, 96, 128, 160, 192, 256, 384)),
        (64, 0x42F0E1EBA9EA3693, "CRC-64/ECMA-182", (8, 16, 32, 64, 96, 128, 160)),
    )
    for width, polynomial, source, symbol_sizes in families:
        for symbol_bits in symbol_sizes:
            result.append({
                "family": "crc_frame_align",
                "category": "link-coding",
                "semantic": "serial/matrix CRC alignment after a frame boundary",
                "source": source,
                "width": width,
                "polynomial": polynomial,
                "symbol_bits": symbol_bits,
                "seed": 985000 + width * 1000 + symbol_bits,
            })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    models = specs()
    if len(models) != 23:
        raise AssertionError(f"expected 23 specs, got {len(models)}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(models, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"models": len(models), "families": 3}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
