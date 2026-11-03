#!/usr/bin/env python3
"""Summarize trace-only MIC decisions emitted by MC PDR.

The report is deliberately descriptive.  It identifies features associated
with successful and inexpensive literal drops before any feature is allowed to
change the live MIC order.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable


def find_traces(paths: Iterable[Path]) -> list[Path]:
    traces: list[Path] = []
    for path in paths:
        if path.is_dir():
            traces.extend(sorted(path.rglob("*.decision.tsv")))
        elif path.name.endswith(".decision.tsv"):
            traces.append(path)
    return sorted(set(traces))


def as_int(row: dict[str, str], key: str) -> int:
    try:
        return int(row[key])
    except (KeyError, TypeError, ValueError):
        return -1


def as_float(row: dict[str, str], key: str) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return math.nan


def distance_bin(value: int) -> str:
    if value < 0:
        return "unreached"
    if value == 0:
        return "0"
    if value == 1:
        return "1"
    if value <= 3:
        return "2-3"
    if value <= 7:
        return "4-7"
    if value <= 15:
        return "8-15"
    return "16+"


def comb_bin(value: int) -> str:
    if value < 0:
        return "not-direct"
    if value <= 2:
        return "0-2"
    if value <= 5:
        return "3-5"
    if value <= 10:
        return "6-10"
    return "11+"


def history_bin(value: int) -> str:
    if value <= 0:
        return "0"
    if value <= 2:
        return "1-2"
    if value <= 7:
        return "3-7"
    return "8+"


def init_relation(row: dict[str, str]) -> str:
    init_value = as_int(row, "init_value")
    if init_value < 0:
        return "unknown"
    polarity = as_int(row, "polarity")
    return "matches" if init_value == polarity else "opposes"


def median(values: list[float]) -> float:
    return statistics.median(values) if values else math.nan


def fmt(value: float, digits: int = 3) -> str:
    return "-" if not math.isfinite(value) else f"{value:.{digits}f}"


def summarize(rows: list[dict[str, str]], feature, minimum: int) -> list[str]:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[str(feature(row))].append(row)

    lines = [
        "| Bucket | Attempts | Drop success | Median seconds | Mean queries | "
        "Failure seconds |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for bucket in sorted(groups):
        group = groups[bucket]
        if len(group) < minimum:
            continue
        successes = [as_int(row, "result") for row in group]
        elapsed = [as_float(row, "elapsed_seconds") for row in group]
        elapsed = [value for value in elapsed if math.isfinite(value)]
        queries = [as_int(row, "query_delta") for row in group]
        failure_elapsed = [
            as_float(row, "elapsed_seconds")
            for row in group
            if as_int(row, "result") == 0
            and math.isfinite(as_float(row, "elapsed_seconds"))
        ]
        lines.append(
            f"| {bucket} | {len(group)} | {sum(successes) / len(group):.3f} | "
            f"{fmt(median(elapsed), 6)} | {sum(queries) / len(group):.2f} | "
            f"{fmt(sum(failure_elapsed), 3)} |"
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--minimum", type=int, default=20)
    args = parser.parse_args()

    traces = find_traces(args.paths)
    rows: list[dict[str, str]] = []
    for trace in traces:
        with trace.open(newline="") as source:
            for row in csv.DictReader(source, delimiter="\t"):
                if row.get("event") == "mic_attempt":
                    row["_source"] = str(trace)
                    rows.append(row)

    success_count = sum(as_int(row, "result") == 1 for row in rows)
    elapsed = [as_float(row, "elapsed_seconds") for row in rows]
    elapsed = [value for value in elapsed if math.isfinite(value)]
    query_count = sum(max(0, as_int(row, "query_delta")) for row in rows)

    report = [
        "# PDR MIC Decision Trace",
        "",
        f"- Trace files: {len(traces)}",
        f"- MIC attempts: {len(rows)}",
        f"- Successful drops: {success_count}",
        f"- Drop success rate: {success_count / len(rows):.3f}"
        if rows
        else "- Drop success rate: -",
        f"- Recorded MIC time: {sum(elapsed):.3f} seconds",
        f"- Recorded PDR queries: {query_count}",
        "",
        "## Temporal Distance to Bad",
        "",
        *summarize(
            rows,
            lambda row: distance_bin(as_int(row, "bad_distance")),
            args.minimum,
        ),
        "",
        "## Direct Combinational Distance to Bad",
        "",
        *summarize(
            rows,
            lambda row: comb_bin(as_int(row, "bad_comb_distance")),
            args.minimum,
        ),
        "",
        "## Literal Polarity versus Initial State",
        "",
        *summarize(rows, init_relation, args.minimum),
        "",
        "## Prior Lemma Occurrence",
        "",
        *summarize(
            rows,
            lambda row: history_bin(as_int(row, "lemma_occurrences")),
            args.minimum,
        ),
        "",
        "## Interpretation Gate",
        "",
        "A live feature is promoted only when its ordering direction is stable "
        "across multiple models and improves both drop success and failed-attempt "
        "cost.  This report alone does not enable a heuristic.",
        "",
    ]
    output = "\n".join(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
