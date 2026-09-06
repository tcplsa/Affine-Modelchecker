#!/usr/bin/env python3
"""Summarize the controlled semantic-suite Gaussian screen."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


CONFIGS = ("xag_cadical", "xag_cmsat_no_gauss", "xag_cmsat_gauss")
LABELS = {
    "xag_cadical": "CaDiCaL",
    "xag_cmsat_no_gauss": "CMSat, no Gaussian",
    "xag_cmsat_gauss": "CMSat, Gaussian",
}


def status(row: dict[str, str], config: str) -> str:
    return row[f"{config}_status"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    with args.input.open(encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    if not rows:
        raise SystemExit("empty results")

    lines = [
        "# 120-second Single-Lane XOR-Backend Screen",
        "",
        "Each model used the same MC-XAG PDR policy and seed. Only the SAT "
        "backend/Gaussian setting varied. This is a screening experiment, not "
        "an 1,800-second coverage claim.",
        "",
        "## Aggregate coverage",
        "",
        "| Backend | SAFE | TIMEOUT |",
        "| --- | ---: | ---: |",
    ]
    for config in CONFIGS:
        counts = Counter(status(row, config) for row in rows)
        lines.append(
            f"| {LABELS[config]} | {counts['SAFE']} | {counts['TIMEOUT']} |"
        )

    lines.extend([
        "",
        "## Per-family coverage",
        "",
        "| Family | Models | CaDiCaL | CMSat no-Gauss | CMSat Gaussian |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    for family in sorted({row["family"] for row in rows}):
        group = [row for row in rows if row["family"] == family]
        solved = [sum(status(row, config) == "SAFE" for row in group) for config in CONFIGS]
        lines.append(
            f"| `{family}` | {len(group)} | {solved[0]} | {solved[1]} | {solved[2]} |"
        )

    gauss_only = [
        row for row in rows
        if status(row, "xag_cmsat_gauss") == "SAFE"
        and status(row, "xag_cmsat_no_gauss") != "SAFE"
        and status(row, "xag_cadical") != "SAFE"
    ]
    cmsat_only = [
        row for row in rows
        if status(row, "xag_cmsat_no_gauss") == "SAFE"
        and status(row, "xag_cadical") != "SAFE"
    ]
    all_timeout = [
        row for row in rows
        if all(status(row, config) == "TIMEOUT" for config in CONFIGS)
    ]

    lines.extend([
        "",
        "## Attribution candidates",
        "",
        f"- **Gaussian-specific candidates:** {len(gauss_only)}",
        f"- **CMSat-backend candidates (independent of Gaussian):** {len(cmsat_only)}",
        f"- **All-backend timeouts:** {len(all_timeout)}",
        "",
    ])
    if gauss_only:
        lines.extend([
            "### Gaussian-specific",
            "",
            "| Family | Model | Time (s) |",
            "| --- | --- | ---: |",
        ])
        for row in gauss_only:
            lines.append(
                f"| `{row['family']}` | `{row['name']}` | "
                f"{float(row['xag_cmsat_gauss_wall_seconds']):.3f} |"
            )
        lines.append("")
    if cmsat_only:
        lines.extend([
            "### CMSat backend, not Gaussian",
            "",
            "| Family | Model | No-Gauss time (s) | Gaussian time (s) |",
            "| --- | --- | ---: | ---: |",
        ])
        for row in cmsat_only:
            lines.append(
                f"| `{row['family']}` | `{row['name']}` | "
                f"{float(row['xag_cmsat_no_gauss_wall_seconds']):.3f} | "
                f"{float(row['xag_cmsat_gauss_wall_seconds']):.3f} |"
            )
        lines.append("")
    gauss_families = sorted({row["family"] for row in gauss_only})
    crc_gauss = [
        row for row in gauss_only
        if row["family"] in {"crc_frame_align", "crc_frame_lock"}
    ]
    affine_gauss = [row for row in gauss_only if row["family"] == "affine_phase_sync"]
    lines.extend([
        "## Interpretation",
        "",
    ])
    if crc_gauss:
        lines.extend([
            "The application-grounded CRC cohort contains a Gaussian-specific "
            "transition: the listed CRC parallel alignment/recovery instances "
            "time out in both non-Gaussian lanes but complete with Gaussian "
            "reasoning. This is distinct from the CRC-16 cases solved by CMSat "
            "without Gaussian reasoning. The next experiment must repeat both "
            "classes at 1,800 seconds and compare against stock rIC3. The "
            "parameterized block-lock detector must not itself be interpreted as "
            "a deep-PDR result unless the observed frame depth also changes.",
            f"Gaussian-specific families in this screen: {', '.join(gauss_families)}.",
            "",
        ])
    elif affine_gauss:
        lines.extend([
            "The only Gaussian-specific signal is the delayed, dense, full-rank "
            "affine synchronization family. Expand its width/round/delay boundary "
            "at 1,800 seconds and keep other SAT-backend effects separate.",
            "",
        ])
    else:
        lines.extend([
        "No Gaussian-specific candidate was found in this screen. Any CMSat "
            "wins should be treated as native-XOR/SAT-backend effects until a "
            "Gaussian-only transition appears.",
            "",
        ])

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8")
    print(
        f"rows={len(rows)} gauss_only={len(gauss_only)} "
        f"cmsat_only={len(cmsat_only)} all_timeout={len(all_timeout)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
