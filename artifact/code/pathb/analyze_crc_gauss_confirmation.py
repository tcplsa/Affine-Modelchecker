#!/usr/bin/env python3
"""Write a reproducible confirmation report for CRC Gaussian candidates."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


MC_CONFIGS = (
    ("xag_cadical", "MC-XAG, CaDiCaL"),
    ("xag_cmsat_no_gauss", "MC-XAG, native XOR CMSat, no Gaussian"),
    ("xag_cmsat_gauss", "MC-XAG, native XOR CMSat, Gaussian"),
)


def load_tsv(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8") as stream:
        return {row["name"]: row for row in csv.DictReader(stream, delimiter="\t")}


def load_ric3(path: Path) -> dict[str, dict[str, object]]:
    report = json.loads(path.read_text(encoding="utf-8"))
    return {str(row["stem"]): row for row in report["results"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mc", type=Path, action="append", required=True)
    parser.add_argument("--ric3", type=Path, action="append", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    mc_runs = [load_tsv(path) for path in args.mc]
    ric3_runs = [load_ric3(path) for path in args.ric3]
    common = set(mc_runs[0])
    for run in mc_runs[1:]:
        common &= set(run)
    for run in ric3_runs:
        common &= set(run)
    if not common:
        raise SystemExit("no common models across MC and rIC3 runs")

    confirmed = []
    for name in sorted(common):
        all_mc = all(
            row["xag_cadical_status"] == "TIMEOUT"
            and row["xag_cmsat_no_gauss_status"] == "TIMEOUT"
            and row["xag_cmsat_gauss_status"] == "SAFE"
            for row in (run[name] for run in mc_runs)
        )
        all_ric3 = all(run[name]["result"] == "timeout" for run in ric3_runs)
        if all_mc and all_ric3:
            confirmed.append(name)

    lines = [
        "# CRC-32 Gaussian Confirmation at 1,800 Seconds",
        "",
        "## Protocol",
        "",
        "Each model is a SAFE serial-versus-parallel CRC frame-alignment property "
        "with arbitrary traffic after the start-of-frame reset. Every MC run uses "
        "one XAG PDR lane and the same policy; only the SAT backend changes. Stock "
        "rIC3 uses its native four-replica portfolio. The two process launches use "
        "independent seeds.",
        "",
        "## Confirmed Gaussian-specific results",
        "",
        "| Model | CRC data width | MC-XAG CaDiCaL | MC-XAG CMSat no-Gauss | MC-XAG CMSat Gaussian | stock rIC3-4 |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for name in confirmed:
        first = mc_runs[0][name]
        details = []
        for prefix, _label in MC_CONFIGS:
            parts = []
            for row in (run[name] for run in mc_runs):
                state = row[f"{prefix}_status"]
                wall = float(row[f"{prefix}_wall_seconds"])
                parts.append(f"{state} ({wall:.3f}s)" if state == "SAFE" else state)
            details.append("; ".join(parts))
        ric3 = "; ".join(
            f"TIMEOUT ({float(run[name]['wall_seconds']):.3f}s)" for run in ric3_runs
        )
        lines.append(
            f"| `{name}` | {first['width']} | {details[0]} | {details[1]} | "
            f"{details[2]} | {ric3} |"
        )

    lines.extend([
        "",
        "## Interpretation and boundary",
        "",
        f"- Confirmed candidates: **{len(confirmed)}** of {len(common)} common models.",
        "- CMSat without Gaussian also times out, separating this result from a "
        "native-XOR backend effect under the tested policy.",
        "- The rIC3 comparison is a real 1,800-second hard-boundary result, not a "
        "1,800-to-3,600-second frontier speedup.",
        "- These are frame-depth-one inductive proofs. They establish a sharp SAT "
        "and inductive-query advantage for a realistic CRC state-alignment task, but "
        "not yet an advantage on deep PDR obligation management. The separate block-"
        "lock recovery cohort addresses that boundary.",
        "",
    ])
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"common": len(common), "confirmed": len(confirmed)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
