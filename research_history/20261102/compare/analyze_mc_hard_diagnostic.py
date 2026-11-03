#!/usr/bin/env python3
"""Summarize MC-AIG breakthroughs and timeout progress by hard family."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--breakthroughs", type=Path, required=True)
    parser.add_argument("--xag-incremental", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def number(value: Optional[str]) -> Optional[float]:
    try:
        return float(value) if value not in {None, ""} else None
    except ValueError:
        return None


def median(values: Iterable[Optional[float]]) -> Optional[float]:
    present = [value for value in values if value is not None]
    return statistics.median(present) if present else None


def fmt(value: Optional[float], digits: int = 1) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def discover_prefix(fields: list[str]) -> str:
    suffix = "_status"
    statuses = [field[:-len(suffix)] for field in fields if field.endswith(suffix)]
    if len(statuses) != 1:
        raise ValueError(f"expected one progress config, found {statuses}")
    return statuses[0]


def main() -> int:
    args = parse_args()
    breakthroughs = json.loads(args.breakthroughs.read_text(encoding="utf-8"))["models"]
    xag_incremental = json.loads(args.xag_incremental.read_text(encoding="utf-8"))["models"]
    with args.progress.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source, delimiter="\t")
        rows = list(reader)
        prefix = discover_prefix(reader.fieldnames or [])

    def field(row: dict[str, str], name: str) -> str:
        return row.get(f"{prefix}_{name}", "")

    buckets: Counter[str] = Counter()
    for model in breakthroughs:
        status = model["mc_aig_legacy4"]["status"]
        depth = int(float(model["mc_aig_legacy4"]["pdr_depth"]))
        if status == "UNSAFE" and depth <= 2:
            buckets["shallow counterexample"] += 1
        elif status == "SAFE" and depth <= 2:
            buckets["immediate induction"] += 1
        elif depth <= 20:
            buckets["multi-frame induction"] += 1
        else:
            buckets["deep convergence"] += 1

    by_family: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_family[row["family"]].append(row)

    lines = [
        "# MC-AIG hard-gap diagnostic",
        "",
        f"- Stock-rIC3-3600 hard cases solved by historical MC-AIG: {len(breakthroughs)}.",
        f"- Additional union cases supplied by either XAG configuration: {len(xag_incremental)}.",
        f"- Diagnostic rows currently available: {len(rows)}.",
        "",
        "## What the existing MC-AIG solves contain",
        "",
        "| Mechanism bucket | Models |",
        "| --- | ---: |",
    ]
    for bucket in (
        "shallow counterexample",
        "immediate induction",
        "multi-frame induction",
        "deep convergence",
    ):
        lines.append(f"| {bucket} | {buckets[bucket]} |")

    lines.extend([
        "",
        "The four buckets must not be explained by one representation claim. Shallow UNSAFE",
        "cases test initial/BMC and model selection; multi-frame SAFE cases test obligations,",
        "generalization, lemma exchange, and push; deep convergence is a separate tail case.",
        "",
        "## Per-family 600-second progress",
        "",
        "| Family | N | Solved | Depth | Queries | CTI | MIC | Push | Frame conflicts/query | Last query role |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ])
    for family, family_rows in sorted(by_family.items(), key=lambda item: (-len(item[1]), item[0])):
        solved = sum(field(row, "status") in {"SAFE", "UNSAFE"} for row in family_rows)
        queries = median(number(field(row, "queries")) for row in family_rows)
        conflicts_per_query = median(
            (number(field(row, "frame_sat_conflicts")) or 0.0)
            / max(1.0, number(field(row, "queries")) or 0.0)
            for row in family_rows
            if number(field(row, "queries")) is not None
        )
        roles = Counter(field(row, "active_query") or "unknown" for row in family_rows)
        role = roles.most_common(1)[0][0]
        lines.append(
            f"| `{family}` | {len(family_rows)} | {solved} | "
            f"{fmt(median(number(field(row, 'pdr_depth')) for row in family_rows), 1)} | "
            f"{fmt(queries, 0)} | "
            f"{fmt(median(number(field(row, 'cti')) for row in family_rows), 0)} | "
            f"{fmt(median(number(field(row, 'mic')) for row in family_rows), 0)} | "
            f"{fmt(median(number(field(row, 'push')) for row in family_rows), 0)} | "
            f"{fmt(conflicts_per_query, 3)} | `{role}` |"
        )

    lines.extend([
        "",
        "## Interpretation rule",
        "",
        "- Low depth with many CTIs/MICs indicates early obligation or generalization pressure.",
        "- High conflicts per query with little depth growth indicates a SAT/backend bottleneck.",
        "- High depth and push volume without convergence indicates lemma propagation pressure.",
        "- An `active_query` value is diagnostic context, not proof that the named role consumed",
        "  the entire timeout; cumulative role counters decide that attribution.",
        "",
        "The next candidate is promoted by additional solved models over four-lane MC-AIG,",
        "then by changed progress on at least three unsolved models. XAG-only coverage remains",
        "an ablation and is not pooled into the MC-AIG improvement count.",
    ])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {args.output} with {len(rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
