#!/usr/bin/env python3
"""Summarize the controlled affine UNSAFE backend/depth-gate experiment."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path


CONFIG_LABELS = (
    ("xag_cadical", "CaDiCaL"),
    ("cmsat_native_no_gauss", "Native no-Gauss"),
    ("cmsat_native_gauss", "Native Gauss"),
    ("auto_no_gauss", "Summary no-Gauss"),
    ("auto_gauss", "Summary Gauss"),
    ("auto_gate_f4", "Gate f4"),
    ("auto_gate_f16", "Gate f16"),
    ("ric3_4", "rIC3-4"),
)


def solved(row: dict[str, str], config: str) -> bool:
    return row.get(f"{config}_status") == "UNSAFE"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.input.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    configs = [
        (config, label) for config, label in CONFIG_LABELS
        if rows and f"{config}_status" in rows[0]
    ]

    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(row["family"], row["witness_depth"])].append(row)
    lines = [
        "# Affine UNSAFE depth screen",
        "",
        f"Models: {len(rows)}. MC configurations use one PDR lane; rIC3-4, when "
        "present, uses four independent IC3 replicas. All use the same seed.",
        "",
        "| Family | Witness depth | Models | "
        + " | ".join(label for _config, label in configs) + " |",
        "| --- | ---: | ---: | " + " | ".join("---:" for _ in configs) + " |",
    ]
    for (family, depth), members in sorted(
        groups.items(), key=lambda item: (item[0][0], int(item[0][1]))
    ):
        counts = [sum(solved(row, config) for row in members) for config, _ in configs]
        lines.append(
            f"| `{family}` | {depth} | {len(members)} | "
            + " | ".join(str(value) for value in counts) + " |"
        )
    totals = [sum(solved(row, config) for row in rows) for config, _ in configs]
    lines.extend([
        f"| **Total** | - | **{len(rows)}** | "
        + " | ".join(f"**{value}**" for value in totals) + " |",
        "",
        "## Paired runtime on common solves",
        "",
    ])
    baseline = "xag_cadical"
    for config, _label in configs[1:]:
        ratios = []
        for row in rows:
            if solved(row, baseline) and solved(row, config):
                base = float(row[f"{baseline}_wall_seconds"])
                candidate = float(row[f"{config}_wall_seconds"])
                if base > 0 and candidate > 0:
                    ratios.append(candidate / base)
        if ratios:
            gm = math.exp(sum(math.log(value) for value in ratios) / len(ratios))
            lines.append(f"- `{config}`/CaDiCaL: geometric ratio {gm:.3f} on {len(ratios)} models.")
        else:
            lines.append(f"- `{config}`/CaDiCaL: no common solved models.")

    gauss_only = [
        row for row in rows
        if solved(row, "auto_gauss") and not solved(row, "auto_no_gauss")
    ]
    cadical_only = [
        row for row in rows
        if solved(row, "xag_cadical") and not solved(row, "auto_gauss")
    ]
    native_gauss_only = [
        row for row in rows
        if "cmsat_native_gauss_status" in row
        and solved(row, "cmsat_native_gauss")
        and not solved(row, "cmsat_native_no_gauss")
    ]
    native_no_gauss_only = [
        row for row in rows
        if "cmsat_native_gauss_status" in row
        and solved(row, "cmsat_native_no_gauss")
        and not solved(row, "cmsat_native_gauss")
    ]
    lines.extend([
        "",
        "## Coverage differences",
        "",
        f"- Always-on Gaussian solves beyond auto no-Gauss: {len(gauss_only)}.",
        f"- Native Gaussian solves beyond native no-Gauss: {len(native_gauss_only)}.",
        f"- Native no-Gauss solves beyond native Gaussian: {len(native_no_gauss_only)}.",
        f"- CaDiCaL solves beyond always-on Gaussian: {len(cadical_only)}.",
        "",
        "This suite controls witness depth but injects a deterministic one-shot fault. "
        "It measures UNSAFE overhead and depth sensitivity; it is not yet a hard "
        "parity-constrained witness benchmark.",
    ])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows={len(rows)} gauss_only={len(gauss_only)} cadical_only={len(cadical_only)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
