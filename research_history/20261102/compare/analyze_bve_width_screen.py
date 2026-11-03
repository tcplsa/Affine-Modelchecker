#!/usr/bin/env python3
"""Compare width-weighted BVE configurations across seed-block result files."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", choices=("mc", "ric3"), required=True)
    parser.add_argument("--inputs", nargs="+", required=True, type=Path)
    parser.add_argument("--weights", nargs="+", type=int, default=(0, 1, 2, 4))
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def config(tool: str, weight: int) -> str:
    return f"{tool}_width_w{weight}"


def solved(row: dict[str, str], name: str) -> bool:
    return row.get(f"{name}_status") in VALID


def time(row: dict[str, str], name: str) -> float:
    return float(row[f"{name}_wall_seconds"])


def stats(rows: list[dict[str, str]], tool: str, weight: int) -> dict[str, float | int]:
    reference = config(tool, 0)
    candidate = config(tool, weight)
    common = [row for row in rows if solved(row, reference) and solved(row, candidate)]
    informative = [row for row in rows if solved(row, reference) or solved(row, candidate)]
    ratios = [time(row, candidate) / time(row, reference) for row in common]
    penalty = lambda row, name: time(row, name) if solved(row, name) else 1.5 * float(row["timeout_seconds"])
    reference_cost = sum(penalty(row, reference) for row in informative)
    candidate_cost = sum(penalty(row, candidate) for row in informative)
    return {
        "solved": sum(solved(row, candidate) for row in rows),
        "reference": sum(solved(row, reference) for row in rows),
        "only": sum(solved(row, candidate) and not solved(row, reference) for row in rows),
        "lost": sum(solved(row, reference) and not solved(row, candidate) for row in rows),
        "common": len(common),
        "geo": math.exp(statistics.mean(map(math.log, ratios))) if ratios else math.nan,
        "median": statistics.median(ratios) if ratios else math.nan,
        "wins": sum(time(row, candidate) + 2 < time(row, reference) for row in common),
        "losses": sum(time(row, reference) + 2 < time(row, candidate) for row in common),
        "par": candidate_cost / reference_cost if reference_cost else math.nan,
    }


def fmt(value: float | int) -> str:
    return str(value) if isinstance(value, int) else ("-" if math.isnan(value) else f"{value:.3f}")


def table(lines: list[str], title: str, rows: list[dict[str, str]], tool: str, weights: list[int]) -> None:
    lines += ["", f"## {title}", "", "| Weight | Solved candidate/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |", "|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for weight in weights:
        value = stats(rows, tool, weight)
        lines.append(
            f"| {weight} | {value['solved']}/{value['reference']} | "
            f"{value['only']}/{value['lost']} | {value['common']} | "
            f"{fmt(value['geo'])} | {fmt(value['median'])} | "
            f"{value['wins']}/{value['losses']} | {fmt(value['par'])} |"
        )


def main() -> int:
    args = arguments()
    cohorts: list[tuple[str, list[dict[str, str]]]] = []
    all_rows: list[dict[str, str]] = []
    for path in args.inputs:
        with path.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        cohorts.append((path.stem, rows))
        all_rows.extend(rows)
    lines = [f"# BVE width screen: {args.tool}", "", f"Model-seed rows: {len(all_rows)} across {len(cohorts)} files."]
    table(lines, "Aggregate", all_rows, args.tool, args.weights)
    for label, rows in cohorts:
        table(lines, label, rows, args.tool, args.weights)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows={len(all_rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
