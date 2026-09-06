#!/usr/bin/env python3
"""Build the frozen 100-circuit semantic crypto/arithmetic specification."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def tagged(family: str, category: str, semantic: str, source: str, **params: object) -> dict:
    return {
        "family": family,
        "category": category,
        "semantic": semantic,
        "source": source,
        **params,
    }


def build_specs() -> list[dict]:
    specs: list[dict] = []

    # 18 standard-polynomial CRC equivalence instances.
    for width, polynomial, standard in (
        (8, 0x07, "CRC-8 polynomial 0x07"),
        (16, 0x1021, "CRC-16-CCITT polynomial 0x1021"),
        (32, 0x04C11DB7, "CRC-32 polynomial 0x04C11DB7"),
    ):
        for symbol_bits in (1, 4, 8):
            for updates in (1, 2):
                specs.append(tagged(
                    "crc_equiv", "crypto-linear", "serial-vs-matrix CRC state equivalence",
                    standard, width=width, polynomial=polynomial,
                    symbol_bits=symbol_bits, updates=updates,
                    seed=910000 + width * 100 + symbol_bits * 10 + updates,
                ))

    # 12 AES MixColumns instances: full AES columns at up to 128 state bits.
    for columns in (1, 2, 4):
        for rounds in (1, 2):
            for variant, topologies in enumerate((
                ("serial", "balanced"), ("balanced", "serial")
            )):
                specs.append(tagged(
                    "aes_linear_equiv", "crypto-linear",
                    "dual implementation of AES MixColumns",
                    "FIPS 197 MixColumns", columns=columns, rounds=rounds,
                    left_topology=topologies[0], right_topology=topologies[1],
                    input_bits=8, variant=variant,
                    seed=920000 + columns * 100 + rounds * 10 + variant,
                ))

    # 12 Keccak theta-rho-pi instances (linear part of Keccak-f).
    for lane_width in (2, 4, 8):
        for rounds in (1, 2):
            for variant, topologies in enumerate((
                ("serial", "balanced"), ("balanced", "serial")
            )):
                specs.append(tagged(
                    "keccak_linear_equiv", "crypto-linear",
                    "dual implementation of Keccak theta-rho-pi",
                    "FIPS 202 Keccak-f linear steps", lane_width=lane_width,
                    rounds=rounds, left_topology=topologies[0],
                    right_topology=topologies[1], input_bits=8, variant=variant,
                    seed=930000 + lane_width * 100 + rounds * 10 + variant,
                ))

    # 18 ARX instances: ChaCha quarter-round and Speck round structure.
    architecture_pairs = (("ripple", "prefix"), ("ripple", "carrysave"))
    for width in (8, 16, 32):
        for rounds in (1, 2):
            for variant, (left_struct, right_struct) in enumerate(architecture_pairs):
                specs.append(tagged(
                    "arx_equiv", "crypto-arx", "ChaCha quarter-round state equivalence",
                    "RFC 8439 structure; reduced-width variants are labeled",
                    primitive="chacha", width=width, rounds=rounds,
                    left_struct=left_struct, right_struct=right_struct,
                    variant=variant, seed=940000 + width * 100 + rounds * 10 + variant,
                ))
    for width in (16, 24, 32):
        for variant, (left_struct, right_struct) in enumerate(architecture_pairs):
            specs.append(tagged(
                "arx_equiv", "crypto-arx", "Speck-style round state equivalence",
                "Speck ARX round structure; reduced-width verification variants",
                primitive="speck", width=width, rounds=1,
                left_struct=left_struct, right_struct=right_struct,
                variant=variant, seed=945000 + width * 100 + variant,
            ))

    # 18 sequential adder architecture-equivalence instances.
    adder_pairs = (
        ("ripple", "prefix"),
        ("ripple", "carrysave"),
        ("prefix", "carrysave"),
    )
    for width in (8, 12, 16, 24, 32, 40):
        for variant, (left_struct, right_struct) in enumerate(adder_pairs):
            specs.append(tagged(
                "adder_equiv", "arithmetic-add",
                "sequential accumulator equivalence across adder structures",
                "parameterized arithmetic RTL model", width=width,
                left_struct=left_struct, right_struct=right_struct,
                rounds=1, variant=variant,
                seed=950000 + width * 100 + variant,
            ))

    # 15 multiply-accumulate equivalence instances.
    mac_pairs = (
        ("schoolbook", "wallace", "ripple", "prefix"),
        ("schoolbook", "wallace", "prefix", "ripple"),
        ("schoolbook", "wallace", "carrysave", "prefix"),
    )
    for width in (4, 6, 8, 10, 12):
        for variant, structures in enumerate(mac_pairs):
            lm, rm, la, ra = structures
            specs.append(tagged(
                "mac_equiv", "arithmetic-mul",
                "sequential multiply-accumulate architecture equivalence",
                "parameterized unsigned schoolbook/Wallace-style multiplier",
                width=width, left_multiplier=lm, right_multiplier=rm,
                left_adder=la, right_adder=ra, variant=variant,
                seed=960000 + width * 100 + variant,
            ))

    # Seven proven affine synchronization points, interpreted as duplicated
    # linear scrambler/decoder synchronization rather than anonymous matrices.
    for index, (width, weight, rounds, delay) in enumerate((
        (24, 19, 2, 2), (28, 21, 2, 2), (32, 25, 2, 2), (40, 31, 2, 2),
        (20, 15, 3, 3), (24, 19, 3, 3), (28, 21, 3, 3),
    )):
        specs.append(tagged(
            "affine_phase_sync", "coding-affine",
            "duplicated linear scrambler resynchronization safety",
            "controlled full-rank GF(2) state-transform model",
            width=width, weight=weight, rounds=rounds, delay=delay,
            inputs=4, topology="balanced", seed=970001 + index,
        ))

    if len(specs) != 100:
        raise AssertionError(f"expected 100 specs, got {len(specs)}")
    canonical = [json.dumps(spec, sort_keys=True) for spec in specs]
    if len(set(canonical)) != len(canonical):
        raise AssertionError("duplicate semantic-suite specifications")
    return specs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    specs = build_specs()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(specs, indent=2) + "\n", encoding="utf-8")
    counts = Counter(spec["category"] for spec in specs)
    summary = {
        "total": len(specs),
        "categories": dict(sorted(counts.items())),
        "families": dict(sorted(Counter(spec["family"] for spec in specs).items())),
    }
    if args.summary:
        args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
