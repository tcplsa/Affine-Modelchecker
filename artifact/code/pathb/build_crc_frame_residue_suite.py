#!/usr/bin/env python3
"""Freeze a temporal CRC/FCS residue-checking cohort."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def specs() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for width, polynomial, source, symbol_sizes in (
        (32, 0x04C11DB7, "CRC-32/IEEE", (16, 32, 64, 96)),
        (16, 0x1021, "CRC-16-CCITT", (32, 64)),
    ):
        for symbol_bits in symbol_sizes:
            for payload_cycles in (2, 4, 8):
                result.append({
                    "family": "crc_frame_residue",
                    "category": "link-coding",
                    "semantic": "fixed-length frame CRC residue after a delayed derived FCS",
                    "source": source,
                    "width": width,
                    "polynomial": polynomial,
                    "symbol_bits": symbol_bits,
                    "payload_cycles": payload_cycles,
                    "fcs_topology": "balanced",
                    "seed": 984000 + width * 100 + symbol_bits * 10 + payload_cycles,
                })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    models = specs()
    if len(models) != 18:
        raise AssertionError(f"expected 18 specs, got {len(models)}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(models, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"models": len(models), "families": 1}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
