#!/usr/bin/env python3
"""Summarize the last telemetry snapshot of the composecrc innard probe."""

from __future__ import annotations

import pathlib
import re
import sys


def fields(line: str) -> dict[str, str]:
    return dict(re.findall(r"([a-zA-Z0-9_]+)=([^ ]+)", line))


def last_line(text: str, marker: str) -> str:
    matches = [line for line in text.splitlines() if marker in line]
    return matches[-1] if matches else ""


def remove_prefix(text: str, prefix: str) -> str:
    return text[len(prefix):] if text.startswith(prefix) else text


def main() -> None:
    directory = pathlib.Path(sys.argv[1])
    rows = []
    tops = []
    for log in sorted(directory.glob("*.log")):
        text = log.read_text(errors="replace")
        stats = fields(last_line(text, "c PDR_STATS"))
        probe = fields(last_line(text, "c PDR_INNARD_PROBE"))
        counters = fields(last_line(text, "c PDR_COUNTERS"))
        top = remove_prefix(
            last_line(text, "c PDR_INNARD_TOP"), "c PDR_INNARD_TOP"
        ).strip()
        xor_top = remove_prefix(
            last_line(text, "c PDR_INNARD_XOR_TOP"), "c PDR_INNARD_XOR_TOP"
        ).strip()
        lemmas = int(probe.get("lemmas", "0"))
        with_any = int(probe.get("lemmas_with_candidates", "0"))
        with_xor = int(probe.get("lemmas_with_xor_candidates", "0"))
        candidates = int(probe.get("candidates", "0"))
        prop = int(probe.get("property_candidates", "0"))
        property_xor = int(probe.get("property_xor_candidates", "0"))
        xor_candidates = int(probe.get("xor_candidates", "0"))
        rows.append({
            "model": log.stem,
            "result": stats.get("result", "-"),
            "runtime": stats.get("runtime", "-"),
            "depth": stats.get("depth", "-"),
            "queries": counters.get("queries", "-"),
            "lemmas": str(lemmas),
            "any_rate": f"{with_any / lemmas:.3f}" if lemmas else "-",
            "xor_rate": f"{with_xor / lemmas:.3f}" if lemmas else "-",
            "candidates": str(candidates),
            "property_rate": f"{prop / candidates:.3f}" if candidates else "-",
            "property_xor_rate": (
                f"{property_xor / xor_candidates:.3f}" if xor_candidates else "-"
            ),
            "support_avg": probe.get("support_avg", "-"),
            "xor_support_avg": probe.get("xor_support_avg", "-"),
            "unique": probe.get("unique_candidates", "-"),
        })
        tops.append((log.stem, top, xor_top))

    report = directory / "report.md"
    with report.open("w") as out:
        out.write("# composecrc internal-predicate feasibility probe\n\n")
        out.write("The probe observes ordinary PDR blocking lemmas and does not "
                  "install internal-signal lemmas. Hard runs use a fixed 300-second "
                  "limit; p06 is a same-family solved control.\n\n")
        out.write("| Model | Result | Runtime | Depth | Queries | Blocking lemmas | "
                  "Any-innard rate | XOR-innard rate | Candidates | Property-cone "
                  "rate | Property-XOR rate | Avg support | XOR avg support | Unique |\n")
        out.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for row in rows:
            out.write("| {model} | {result} | {runtime} | {depth} | {queries} | "
                      "{lemmas} | {any_rate} | {xor_rate} | {candidates} | "
                      "{property_rate} | {property_xor_rate} | {support_avg} | "
                      "{xor_support_avg} | "
                      "{unique} |\n".format(**row))
        out.write("\n## Most frequent candidates\n\n")
        for model, top, xor_top in tops:
            out.write(f"- `{model}` all: `{top or '-'}`\n")
            out.write(f"- `{model}` XOR: `{xor_top or '-'}`\n")


if __name__ == "__main__":
    main()
