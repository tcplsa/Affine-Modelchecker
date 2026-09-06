#!/usr/bin/env python3
"""Build scale and protocol margins for guarded-affine CRC transitions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def specs() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    standards = (
        (16, 0x1021, "CRC-16-CCITT", (2048, 3072, 4096)),
        (16, 0x8005, "CRC-16-IBM", (2048, 3072)),
        (32, 0x04C11DB7, "CRC-32-IEEE", (768, 1024, 1536)),
        (32, 0x1EDC6F41, "CRC-32C-Castagnoli", (768, 1024)),
        (64, 0x42F0E1EBA9EA3693, "CRC-64-ECMA", (384, 512, 768)),
    )
    for width, polynomial, standard, symbol_widths in standards:
        for symbol_bits in symbol_widths:
            result.append(
                {
                    "family": "crc_frame_align",
                    "category": "link-coding",
                    "semantic": "guarded CRC frame alignment scale margin",
                    "standard": standard,
                    "width": width,
                    "polynomial": polynomial,
                    "symbol_bits": symbol_bits,
                    "seed": 1_510_000 + width * 10_000 + symbol_bits,
                }
            )

    for width, polynomial, standard, symbol_bits in (
        (16, 0x1021, "CRC-16-CCITT", 512),
        (32, 0x04C11DB7, "CRC-32-IEEE", 256),
        (32, 0x1EDC6F41, "CRC-32C-Castagnoli", 256),
    ):
        for confirm_headers in (2, 4, 8):
            result.append(
                {
                    "family": "crc_frame_lock",
                    "category": "link-control",
                    "semantic": "CRC recovery after multi-block lock acquisition",
                    "standard": standard,
                    "width": width,
                    "polynomial": polynomial,
                    "symbol_bits": symbol_bits,
                    "confirm_headers": confirm_headers,
                    "seed": (
                        1_520_000
                        + width * 10_000
                        + symbol_bits * 10
                        + confirm_headers
                    ),
                }
            )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    models = specs()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(models, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"models": len(models), "families": 2}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
