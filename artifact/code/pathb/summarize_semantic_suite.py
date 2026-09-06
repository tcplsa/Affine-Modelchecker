#!/usr/bin/env python3
"""Summarize and select smoke models from a semantic-suite manifest."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path


GATE_KINDS = ("ands", "xors", "ors", "nots")
FAMILY_DESCRIPTIONS = {
    "crc_equiv": "bit-serial versus matrix-expanded CRC updates for standard polynomials.",
    "aes_linear_equiv": "dual AES MixColumns implementations.",
    "keccak_linear_equiv": "dual Keccak theta-rho-pi implementations.",
    "arx_equiv": "ChaCha quarter-round and Speck-style round equivalence.",
    "adder_equiv": "ripple, prefix, and carry-save accumulator equivalence.",
    "mac_equiv": "schoolbook versus Wallace-style multiply-accumulate equivalence.",
    "affine_phase_sync": "duplicated linear scrambler synchronization.",
    "scrambler_recovery": "IEEE 802.3 64b/66b self-synchronizing scrambler recovery.",
    "crc_frame_align": "serial and parallel CRC state alignment after start-of-frame.",
}


def gate_count(row: dict[str, object]) -> int:
    stats = row["stats"]
    return sum(int(stats[kind]) for kind in GATE_KINDS)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--smoke-manifest", type=Path)
    args = parser.parse_args()

    rows = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not rows:
        raise SystemExit("empty manifest")

    category_counts = Counter(row["classification"]["category"] for row in rows)
    families = sorted({str(row["family"]) for row in rows})
    lines = [
        "# Semantic Sequential Circuit Suite",
        "",
        f"The frozen suite contains **{len(rows)} SAFE sequential circuits** in "
        f"**{len(families)} semantic families**. Each property compares two "
        "meaningful implementations or checks synchronization of duplicated "
        "linear state machines.",
        "",
        "## Category composition",
        "",
        "| Category | Models |",
        "| --- | ---: |",
    ]
    lines.extend(
        f"| {category} | {count} |"
        for category, count in sorted(category_counts.items())
    )
    lines.extend([
        "",
        "## Structural ranges",
        "",
        "| Family | Models | Gates min/median/max | Latches min/max | XOR density min/max |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    smoke = []
    for family in families:
        group = [row for row in rows if row["family"] == family]
        gates = [gate_count(row) for row in group]
        latches = [int(row["stats"]["latches"]) for row in group]
        densities = [float(row["xor_density"]) for row in group]
        lines.append(
            f"| `{family}` | {len(group)} | {min(gates)}/{statistics.median(gates):.0f}/{max(gates)} "
            f"| {min(latches)}/{max(latches)} | {min(densities):.3f}/{max(densities):.3f} |"
        )
        smoke.append(min(group, key=lambda row: (gate_count(row), str(row["stem"]))))

    totals = {
        kind: sum(int(row["stats"][kind]) for row in rows)
        for kind in ("inputs", "latches", *GATE_KINDS)
    }
    lines.extend([
        "",
        "## Aggregate structure",
        "",
        "- Inputs across models: %d" % totals["inputs"],
        "- Latches across models: %d" % totals["latches"],
        "- AND/XOR/OR gates: %d / %d / %d" % (
            totals["ands"], totals["xors"], totals["ors"]
        ),
        "- Every model is emitted as both AAG and XOR-preserving BLIF with SHA-256 hashes.",
        "- Structural/hash validation and randomized sequential simulation are performed by "
        "`validate_semantic_suite.py`.",
        "",
        "## Families",
        "",
    ])
    lines.extend(
        f"- `{family}`: {FAMILY_DESCRIPTIONS.get(family, 'see manifest metadata.')}"
        for family in families
    )
    lines.append("")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8")
    if args.smoke_manifest:
        args.smoke_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.smoke_manifest.write_text(json.dumps(smoke, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "models": len(rows),
        "families": len(families),
        "smoke_models": len(smoke),
        "report": str(args.report),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
