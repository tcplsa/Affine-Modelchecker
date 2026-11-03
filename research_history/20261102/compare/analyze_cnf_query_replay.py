#!/usr/bin/env python3
"""Summarize frozen-query replay by solver role and trace origin."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


def reduction(reference: float, candidate: float) -> float:
    return 100.0 * (reference - candidate) / reference if reference else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    cells: dict[tuple[str, str, str], dict[str, str]] = {}
    duplicates = 0
    for path in args.inputs:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = (row["trace_key"], row["trace"], row["mode"])
                duplicates += key in cells
                cells[key] = row

    pairs_by_group: defaultdict[tuple[str, str, str, str], list[tuple[dict[str, str], dict[str, str]]]] = defaultdict(list)
    for (trace_key, trace, mode), candidate in cells.items():
        if mode == "recorded":
            continue
        baseline = cells.get((trace_key, trace, "recorded"))
        if baseline is None:
            continue
        group = (
            candidate["representation"], candidate["origin"],
            candidate["solver_role"], mode,
        )
        pairs_by_group[group].append((baseline, candidate))

    mismatch_rows = sum(
        row["replay_status"] != "OK" or int(row.get("mismatches", "0") or 0) != 0
        for row in cells.values()
    )
    lines = [
        "# Frozen SAT Query Replay", "",
        f"Rows: {len(cells)}; duplicates replaced: {duplicates}; non-OK or mismatching rows: {mismatch_rows}.", "",
        "Candidate reductions compare a fresh candidate replay with a fresh replay of the mapping recorded by the originating live PDR run.", "",
        "| Representation | Origin | Solver role | Candidate mapping | Traces | Complete pairs | Replay-time reduction | Conflict reduction | Decision reduction | Propagation reduction |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for group in sorted(pairs_by_group):
        pairs = [
            pair for pair in pairs_by_group[group]
            if pair[0]["replay_status"] == "OK" and pair[1]["replay_status"] == "OK"
            and int(pair[0]["mismatches"] or 0) == 0 and int(pair[1]["mismatches"] or 0) == 0
        ]
        complete = sum(pair[0]["complete"] == "1" and pair[1]["complete"] == "1" for pair in pairs)
        base_time = sum(float(base["replay_seconds"]) for base, _ in pairs)
        candidate_time = sum(float(candidate["replay_seconds"]) for _, candidate in pairs)
        base_conflicts = sum(int(base["replay_conflicts"]) for base, _ in pairs)
        candidate_conflicts = sum(int(candidate["replay_conflicts"]) for _, candidate in pairs)
        base_decisions = sum(int(base["replay_decisions"]) for base, _ in pairs)
        candidate_decisions = sum(int(candidate["replay_decisions"]) for _, candidate in pairs)
        base_propagations = sum(int(base["replay_propagations"]) for base, _ in pairs)
        candidate_propagations = sum(int(candidate["replay_propagations"]) for _, candidate in pairs)
        representation, origin, role, mode = group
        lines.append(
            f"| {representation} | {origin.replace('__', '/')} | {role} | {mode} | "
            f"{len(pairs)} | {complete} | {reduction(base_time, candidate_time):+.2f}% | "
            f"{reduction(base_conflicts, candidate_conflicts):+.2f}% | "
            f"{reduction(base_decisions, candidate_decisions):+.2f}% | "
            f"{reduction(base_propagations, candidate_propagations):+.2f}% |"
        )

    status = Counter(row["replay_status"] for row in cells.values())
    lines.extend(["", f"Replay status counts: {dict(status)}", ""])
    report = "\n".join(lines) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    print(report)
    return 1 if mismatch_rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
