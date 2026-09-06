#!/usr/bin/env python3
"""Build a small, application-grounded XOR-domain cohort.

This cohort is intentionally separate from the abstract affine-phase family.
It provides reproducible protocol-oriented models for functional validation
before any expensive performance screen is scheduled elsewhere.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def specs() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for symbol_bits in (1, 4, 8, 16, 32, 64, 96, 128):
        for topology in ("serial", "balanced"):
            result.append({
                "family": "scrambler_recovery",
                "category": "link-coding",
                "semantic": "64b/66b self-synchronous scrambler lock recovery",
                "source": "IEEE 802.3 PCS polynomial 1 + x^39 + x^58",
                "symbol_bits": symbol_bits,
                "topology": topology,
                "seed": 980000 + symbol_bits + (0 if topology == "serial" else 500),
            })
    for width, polynomial, name in (
        (16, 0x1021, "CRC-16-CCITT"),
        (32, 0x04C11DB7, "CRC-32/IEEE"),
    ):
        for symbol_bits in (8, 16, 32, 64):
            result.append({
                "family": "crc_frame_align",
                "category": "link-coding",
                "semantic": "serial-versus-parallel CRC alignment after SOF",
                "source": name,
                "width": width,
                "polynomial": polynomial,
                "symbol_bits": symbol_bits,
                "seed": 981000 + width * 10 + symbol_bits,
            })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    models = specs()
    if len(models) != 24:
        raise AssertionError(f"expected 24 specs, got {len(models)}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(models, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"models": len(models), "families": 2}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
