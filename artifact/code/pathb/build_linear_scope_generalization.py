#!/usr/bin/env python3
"""Cross-topology generalization suite for the shallow affine selector."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def specs() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []

    # Standard PRBS/LFSR characteristic-polynomial tap families.  The exact
    # convention is less important than preserving each family across a size
    # sweep; no result file is consulted when choosing these points.
    prbs = (
        (15, [14, 13], "PRBS15"),
        (23, [22, 17], "PRBS23"),
        (31, [30, 27], "PRBS31"),
        (63, [62, 61], "PRBS63"),
    )
    for width, taps, standard in prbs:
        steps_values = (128, 256, 512, 768) if width < 63 else (64, 128, 256, 384)
        for steps in steps_values:
            result.append({
                "family": "lfsr_jump_equiv",
                "category": "prbs",
                "semantic": "iterative versus matrix jump-ahead PRBS generator",
                "standard": standard,
                "width": width,
                "steps": steps,
                "taps": taps,
                "seed": 1_010_000 + width * 1000 + steps,
            })

    # Same IEEE scrambler and widths, independent initial-state launches.  A
    # real structural effect should not depend on the arbitrary reset value.
    for seed_offset in (0, 1000, 2000):
        for symbol_bits in (256, 384, 512, 768):
            result.append({
                "family": "scrambler_equiv",
                "category": "link-coding",
                "semantic": "serial versus parallel 64b/66b PCS scrambler",
                "standard": "IEEE 802.3 polynomial 1 + x^39 + x^58",
                "symbol_bits": symbol_bits,
                "seed": 1_100_000 + seed_offset + symbol_bits,
            })

    # Two parity-check densities at three syndrome widths.  These points test
    # whether rank alone suffices or dense rows are also needed.
    for check_bits in (16, 32, 64):
        for data_bits in (256, 512):
            for density, divisor in (("sparse", 16), ("dense", 4)):
                row_weight = max(5, data_bits // divisor + 1)
                result.append({
                    "family": "syndrome_equiv",
                    "category": "ecc",
                    "semantic": "streaming binary-code syndrome network equivalence",
                    "standard": f"generic-full-rank-{density}",
                    "check_bits": check_bits,
                    "data_bits": data_bits,
                    "row_weight": row_weight,
                    "seed": 1_200_000 + check_bits * 1000 + data_bits + divisor,
                })

    # Alternate deployed CRC polynomials around their expected parallel-width
    # transition.  This tests polynomial independence of the CRC result.
    crc_families = (
        (16, 0x1021, "CRC-16-CCITT", (64, 96, 192)),
        (16, 0x8005, "CRC-16-IBM", (64, 96, 192)),
        (32, 0x04C11DB7, "CRC-32-IEEE", (128, 256, 384)),
        (32, 0x1EDC6F41, "CRC-32C-Castagnoli", (128, 256, 384)),
    )
    for width, polynomial, standard, symbol_widths in crc_families:
        for symbol_bits in symbol_widths:
            result.append({
                "family": "crc_frame_align",
                "category": "link-coding",
                "semantic": "serial versus parallel CRC state alignment",
                "standard": standard,
                "width": width,
                "polynomial": polynomial,
                "symbol_bits": symbol_bits,
                "seed": 1_300_000 + width * 1000 + symbol_bits + (polynomial & 255),
            })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    models = specs()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(models, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"models": len(models), "families": 4}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

