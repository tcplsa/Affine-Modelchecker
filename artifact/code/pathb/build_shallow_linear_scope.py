#!/usr/bin/env python3
"""Freeze a focused boundary suite for practical shallow affine datapaths."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def specs() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for steps in (32, 64, 128, 256, 384, 512):
        result.append({
            "family": "lfsr_jump_equiv",
            "category": "prbs",
            "semantic": "iterative versus matrix jump-ahead PRBS generator",
            "width": 32,
            "steps": steps,
            "taps": [31, 21, 1, 0],
            "seed": 991000 + steps,
        })
    for symbol_bits in (64, 128, 256, 384, 512, 768):
        result.append({
            "family": "scrambler_equiv",
            "category": "link-coding",
            "semantic": "serial versus parallel 64b/66b PCS scrambler",
            "standard": "IEEE 802.3 polynomial 1 + x^39 + x^58",
            "symbol_bits": symbol_bits,
            "seed": 992000 + symbol_bits,
        })
    for data_bits, row_weight in (
        (64, 9), (128, 13), (256, 17), (384, 25), (512, 33), (768, 49)
    ):
        result.append({
            "family": "syndrome_equiv",
            "category": "ecc",
            "semantic": "streaming binary-code syndrome network equivalence",
            "check_bits": 32,
            "data_bits": data_bits,
            "row_weight": row_weight,
            "seed": 993000 + data_bits,
        })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    models = specs()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(models, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"models": len(models), "families": 3}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
