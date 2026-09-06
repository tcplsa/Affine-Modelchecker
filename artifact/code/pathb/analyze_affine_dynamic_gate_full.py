#!/usr/bin/env python3
"""Summarize the two-seed full affine selector and Gaussian-gate experiment."""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter
from pathlib import Path


CONFIGS = (
    "cadical",
    "cmsat_no_gauss",
    "cmsat_gauss",
    "cmsat_dynamic",
    "two_stage_static",
    "two_stage_auto",
)
VALID = {"SAFE", "UNSAFE"}


def is_solved(row: dict[str, str], config: str) -> bool:
    return row.get(f"{config}_status") in VALID


def aggregate(rows: list[dict[str, str]], config: str) -> tuple[int, float]:
    if not rows:
        return 0, 0.0
    timeout = float(rows[0]["timeout_seconds"])
    solved = sum(is_solved(row, config) for row in rows)
    par = sum(
        float(row[f"{config}_wall_seconds"])
        if is_solved(row, config)
        else timeout
        for row in rows
    )
    return solved, par


def ratio(rows: list[dict[str, str]], candidate: str, baseline: str) -> str:
    common = [
        row for row in rows
        if is_solved(row, candidate) and is_solved(row, baseline)
        and float(row[f"{candidate}_wall_seconds"]) > 0
        and float(row[f"{baseline}_wall_seconds"]) > 0
    ]
    if not common:
        return "-"
    logs = [
        math.log(float(row[f"{candidate}_wall_seconds"]))
        - math.log(float(row[f"{baseline}_wall_seconds"]))
        for row in common
    ]
    return f"{math.exp(sum(logs) / len(logs)):.3f} ({len(common)})"


def table(lines: list[str], rows: list[dict[str, str]], title: str) -> None:
    lines += [
        f"## {title}",
        "",
        "| Configuration | Solved | PAR-1 (s) | GM ratio vs CaDiCaL (common n) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for config in CONFIGS:
        solved, par = aggregate(rows, config)
        lines.append(
            f"| `{config}` | {solved}/{len(rows)} | {par:.2f} | "
            f"{ratio(rows, config, 'cadical')} |"
        )
    lines.append("")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    by_seed: list[tuple[str, list[dict[str, str]]]] = []
    for path in args.inputs:
        with path.open(newline="", encoding="utf-8") as handle:
            by_seed.append((path.stem, list(csv.DictReader(handle, delimiter="\t"))))
    rows = [row for _, seed_rows in by_seed for row in seed_rows]

    lines = [
        "# Full affine selector and dynamic Gaussian gate",
        "",
        "Two independent fixed seeds; all configurations are single-lane and use",
        "the same per-model timeout. PAR-1 assigns the timeout to every unsolved run.",
        "",
    ]
    for seed, seed_rows in by_seed:
        table(lines, seed_rows, seed)
    table(lines, rows, "Both seeds pooled as observations")

    lines += [
        "## Scope and family coverage",
        "",
        "| Scope/family | Observations | CaDiCaL | Gaussian | Dynamic | Static auto | Two-stage auto |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    keys = sorted({(row.get("scope", ""), row.get("family", "")) for row in rows})
    for scope, family in keys:
        group = [row for row in rows if row.get("scope", "") == scope and row.get("family", "") == family]
        counts = [
            sum(is_solved(row, config) for row in group)
            for config in (
                "cadical", "cmsat_gauss", "cmsat_dynamic",
                "two_stage_static", "two_stage_auto",
            )
        ]
        lines.append(
            f"| {scope}/{family} | {len(group)} | "
            + " | ".join(map(str, counts)) + " |"
        )

    lines += ["", "## Incremental coverage and decisions", ""]
    for candidate, baseline in (
        ("cmsat_dynamic", "cmsat_gauss"),
        ("two_stage_static", "cadical"),
        ("two_stage_auto", "cadical"),
        ("two_stage_auto", "two_stage_static"),
    ):
        gains = sum(is_solved(row, candidate) and not is_solved(row, baseline) for row in rows)
        losses = sum(is_solved(row, baseline) and not is_solved(row, candidate) for row in rows)
        lines.append(f"- `{candidate}` versus `{baseline}`: +{gains}/-{losses} solved observations.")

    choices = Counter(row.get("two_stage_auto_affine_auto_choice", "") for row in rows)
    disabled = sum(row.get("two_stage_auto_affine_gauss_disabled", "") == "1" for row in rows)
    lines += [
        f"- Two-stage selector choices: `{dict(choices)}`.",
        f"- Dynamic Gaussian shutdowns in two-stage auto: {disabled}/{len(rows)} observations.",
        "",
        "## Cross-seed coverage stability",
        "",
        "| Configuration | Solved in both seeds | Solved in either seed | Seed disagreement |",
        "| --- | ---: | ---: | ---: |",
    ]
    if len(by_seed) == 2:
        maps = [{row["name"]: row for row in seed_rows} for _, seed_rows in by_seed]
        names = sorted(set(maps[0]) & set(maps[1]))
        for config in CONFIGS:
            pairs = [(is_solved(maps[0][name], config), is_solved(maps[1][name], config)) for name in names]
            both = sum(a and b for a, b in pairs)
            either = sum(a or b for a, b in pairs)
            disagree = sum(a != b for a, b in pairs)
            lines.append(f"| `{config}` | {both} | {either} | {disagree} |")
    else:
        lines.append("| n/a | - | - | - |")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
