#!/usr/bin/env python3
"""Freeze a protocol-oriented CRC block-lock recovery cohort."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def specs() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    # CRC-32 is the primary affine stressor.  CRC-16 is a useful smaller
    # boundary case, not pooled with the CRC-32 headline result.
    for width, polynomial, source in (
        (32, 0x04C11DB7, "CRC-32/IEEE"),
        (16, 0x1021, "CRC-16-CCITT"),
    ):
        for symbol_bits in (16, 32, 64, 96):
            for confirm_headers in (2, 4, 8, 16):
                result.append({
                    "family": "crc_frame_lock",
                    "category": "link-coding",
                    "semantic": "receiver block-lock recovery with serial/matrix CRC alignment",
                    "source": source,
                    "width": width,
                    "polynomial": polynomial,
                    "symbol_bits": symbol_bits,
                    "confirm_headers": confirm_headers,
                    "seed": 983000 + width * 100 + symbol_bits * 10 + confirm_headers,
                })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    models = specs()
    if len(models) != 32:
        raise AssertionError(f"expected 32 specs, got {len(models)}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(models, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"models": len(models), "families": 1}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
