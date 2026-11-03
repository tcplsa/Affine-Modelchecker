#!/usr/bin/env python3
"""Evaluate global and frozen conditional width policies on blind result files."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}
BASE = "ric3_width_w0"
CANDIDATE = "ric3_width_w2"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--inputs", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def solved(row: dict[str, str], config: str) -> bool:
    return row.get(f"{config}_status") in VALID


def runtime(row: dict[str, str], config: str) -> float:
    return float(row[f"{config}_wall_seconds"])


def evaluate(rows: list[dict[str, str]], choose_candidate) -> dict[str, float | int]:
    choices = [CANDIDATE if choose_candidate(row) else BASE for row in rows]
    informative = [
        index for index, row in enumerate(rows)
        if solved(row, BASE) or solved(row, choices[index])
    ]
    common = [
        index for index in informative
        if solved(rows[index], BASE) and solved(rows[index], choices[index])
    ]
    ratios = [runtime(rows[index], choices[index]) / runtime(rows[index], BASE) for index in common]
    penalty = lambda row, config: (
        runtime(row, config) if solved(row, config)
        else 1.5 * float(row["timeout_seconds"])
    )
    base_cost = sum(penalty(rows[index], BASE) for index in informative)
    candidate_cost = sum(penalty(rows[index], choices[index]) for index in informative)
    return {
        "picks": sum(choice == CANDIDATE for choice in choices),
        "solved": sum(solved(row, choice) for row, choice in zip(rows, choices)),
        "base": sum(solved(row, BASE) for row in rows),
        "only": sum(solved(row, choice) and not solved(row, BASE) for row, choice in zip(rows, choices)),
        "lost": sum(solved(row, BASE) and not solved(row, choice) for row, choice in zip(rows, choices)),
        "common": len(common),
        "geo": math.exp(statistics.mean(map(math.log, ratios))) if ratios else math.nan,
        "median": statistics.median(ratios) if ratios else math.nan,
        "wins": sum(runtime(rows[index], choices[index]) + 2 < runtime(rows[index], BASE) for index in common),
        "losses": sum(runtime(rows[index], BASE) + 2 < runtime(rows[index], choices[index]) for index in common),
        "par": candidate_cost / base_cost if base_cost else math.nan,
    }


def fmt(value: float | int) -> str:
    return str(value) if isinstance(value, int) else ("-" if math.isnan(value) else f"{value:.3f}")


def table(lines: list[str], title: str, rows: list[dict[str, str]], metadata, threshold: int) -> None:
    policies = (
        ("Global w2", lambda _row: True),
        (f"Conditional bad-cone >= {threshold}", lambda row: metadata[row["model_id"]] >= threshold),
        (
            "Extremes bad-cone = 0 or >= 100",
            lambda row: metadata[row["model_id"]] == 0 or metadata[row["model_id"]] >= 100,
        ),
    )
    lines += ["", f"## {title}", "", "| Policy | w2 picks | Solved policy/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for label, policy in policies:
        value = evaluate(rows, policy)
        lines.append(
            f"| {label} | {value['picks']} | {value['solved']}/{value['base']} | "
            f"{value['only']}/{value['lost']} | {value['common']} | "
            f"{fmt(value['geo'])} | {fmt(value['median'])} | "
            f"{value['wins']}/{value['losses']} | {fmt(value['par'])} |"
        )


def main() -> int:
    args = arguments()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    bad_counts = {model["id"]: int(model.get("bad_cone_xors", 0)) for model in manifest}
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    threshold = int(selection["bad_cone_threshold"])
    cohorts = []
    all_rows = []
    for path in args.inputs:
        with path.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        cohorts.append((path.stem, rows))
        all_rows.extend(rows)
    lines = ["# Blind conditional BVE width validation", "", f"Frozen models: {len(selection['ids'])}; model-seed rows: {len(all_rows)}."]
    table(lines, "Aggregate", all_rows, bad_counts, threshold)
    for label, rows in cohorts:
        table(lines, label, rows, bad_counts, threshold)
    buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
    by_id = {model["id"]: model for model in selection["models"]}
    for row in all_rows:
        buckets[by_id[row["model_id"]]["bucket"]].append(row)
    for name in ("zero", "1-9", "10-29", "30-99", "100+"):
        table(lines, f"Bucket {name}", buckets[name], bad_counts, threshold)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows={len(all_rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
