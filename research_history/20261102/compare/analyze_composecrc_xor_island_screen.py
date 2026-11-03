#!/usr/bin/env python3
"""Summarize a fixed XOR-island screen without treating timeouts as solves."""

from __future__ import annotations

import pathlib
import re
import sys


def last(pattern: str, text: str) -> str:
    values = re.findall(pattern, text)
    return values[-1] if values else "-"


def main() -> None:
    directory = pathlib.Path(sys.argv[1])
    rows = []
    for log in sorted(directory.glob("*.log")):
        text = log.read_text(errors="replace")
        stem, mode = log.name[:-4].rsplit(".", 1)
        stats = next((line for line in text.splitlines() if "PDR_AFFINE" in line), "")
        rows.append({
            "model": stem,
            "mode": mode,
            "result": last(r"result=(safe|unsafe)", text),
            "frames": last(r"\bdepth=([0-9]+)", text),
            "queries": last(r"PDR_COUNTERS queries=([0-9]+)", text),
            "conflicts": last(r"CMSAT_GAUSS_TOTAL[^\n]*\bconflicts=([0-9]+)", text),
            "islands": last(r"island_count=([0-9]+)", stats),
            "replaced": last(r"island_replaced_gates=([0-9]+)", stats),
            "validated": last(r"island_validation_passed=([01])", stats),
        })

    report = directory / "report.md"
    with report.open("w") as out:
        out.write("# composecrc XOR-island short screen\n\n")
        out.write("Fixed 180-second single-process screen. A timeout is not a solve. "
                  "The experiment isolates validated local XOR-island compression "
                  "from the existing CMSat Gaussian lane.\n\n")
        out.write("| Model | Mode | Result | Frames | Queries | Conflicts | Islands | Replaced gates | Validated |\n")
        out.write("|---|---|---:|---:|---:|---:|---:|---:|---:|\n")
        for row in rows:
            out.write("| {model} | {mode} | {result} | {frames} | {queries} | {conflicts} | "
                      "{islands} | {replaced} | {validated} |\n".format(**row))


if __name__ == "__main__":
    main()
