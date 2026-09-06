#!/usr/bin/env python3
"""Summarize controlled affine-XOR phase sweeps without external packages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ORDER = ("ric3", "mc-aig", "mc-xag", "minisat", "cmsat", "cmsat-gauss")


def cell(row: dict[str, object] | None) -> str:
    if row is None:
        return "-"
    outcome = str(row["result"])
    if outcome == "safe":
        return f"SAFE {float(row['wall_seconds']):.2f}s"
    if outcome == "timeout":
        return "TO"
    return f"{outcome.upper()}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows: dict[tuple[str, str], dict[str, object]] = {}
    timeouts: list[float] = []
    for path in args.report:
        payload = json.loads(path.read_text(encoding="utf-8"))
        timeouts.append(float(payload["timeout"]))
        for row in payload["results"]:
            # Later reports intentionally replace an earlier rerun of a config.
            rows[(str(row["stem"]), str(row["config"]))] = row

    stems = sorted(
        {stem for stem, _ in rows},
        key=lambda stem: (
            int(rows[(stem, next(c for c in ORDER if (stem, c) in rows))]["params"]["rounds"]),
            int(rows[(stem, next(c for c in ORDER if (stem, c) in rows))]["params"]["width"]),
        ),
    )
    lines = [
        "# Affine XOR Phase Sweep",
        "",
        "Each cell is a four-worker PDR portfolio. `TO` means the external "
        "screen time limit elapsed; `ERROR` is never treated as a timeout.",
        "",
        "| rounds | width | rIC3 AIG | MC AIG | MC XAG | MiniSat CNF | CMSat XOR | CMSat XOR+Gauss |",
        "|---:|---:|---|---|---|---|---|---|",
    ]

    gauss_only = []
    xag_gap = []
    for stem in stems:
        exemplar = next(rows[(stem, config)] for config in ORDER if (stem, config) in rows)
        params = exemplar["params"]
        line = [str(params["rounds"]), str(params["width"])]
        for config in ORDER:
            line.append(cell(rows.get((stem, config))))
        lines.append("| " + " | ".join(line) + " |")

        gauss = rows.get((stem, "cmsat-gauss"))
        cmsat = rows.get((stem, "cmsat"))
        xag = rows.get((stem, "mc-xag"))
        aig = rows.get((stem, "mc-aig"))
        if gauss and gauss["result"] == "safe":
            if cmsat and cmsat["result"] != "safe":
                gauss_only.append((stem, params))
            if xag and xag["result"] != "safe":
                xag_gap.append((stem, params, aig["result"] if aig else "-"))

    lines.extend(["", "## Screening Signals", ""])
    if gauss_only:
        lines.append("Gaussian-only (native XOR without Gaussian did not solve):")
        lines.extend(
            f"- r={p['rounds']}, w={p['width']}: `{stem}`" for stem, p in gauss_only
        )
    else:
        lines.append("- No Gaussian-only point at this limit.")
    lines.append("")
    if xag_gap:
        lines.append("Native-XOR/CMSat solves missed by MC-XAG:")
        lines.extend(
            f"- r={p['rounds']}, w={p['width']} (MC-AIG: {aig}): `{stem}`"
            for stem, p, aig in xag_gap
        )
    else:
        lines.append("- No CMSat-only point relative to MC-XAG at this limit.")

    lines.extend(["", "## Interpretation Rule", ""])
    lines.append(
        "A point is promoted to the long-run boundary study only when it is "
        "SAFE under an independently checked invariant, native XOR plus Gaussian "
        "solves it, and at least one lowered-CNF control times out. The long-run "
        "study repeats both the candidate and its controls with fresh launches."
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote={args.output} rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
