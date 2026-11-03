#!/usr/bin/env python3
"""Analyze equal-budget four-lane portfolios of phase-specific BVE orders."""

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
from dataclasses import dataclass
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}
REFERENCE = "4xPPP"


@dataclass(frozen=True)
class Portfolio:
    name: str
    configs: tuple[str, ...]


PORTFOLIOS = (
    Portfolio("4xPPP", ("phase_ppp4",)),
    Portfolio("4xLLL", ("phase_lll4",)),
    Portfolio("2xPPP+2xLPP", ("phase_ppp2", "phase_lpp2")),
    Portfolio("2xPPP+2xPLP", ("phase_ppp2", "phase_plp2")),
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def solved_config(row: dict[str, str], config: str) -> bool:
    return row[f"{config}_status"] in VALID


def solved(row: dict[str, str], portfolio: Portfolio) -> bool:
    return any(solved_config(row, config) for config in portfolio.configs)


def runtime(row: dict[str, str], portfolio: Portfolio) -> float:
    times = [
        float(row[f"{config}_wall_seconds"])
        for config in portfolio.configs
        if solved_config(row, config)
    ]
    return min(times) if times else float(row["timeout_seconds"])


def evaluate(
    rows: list[dict[str, str]], candidate: Portfolio, reference: Portfolio
) -> dict[str, float | int]:
    informative = [row for row in rows if solved(row, candidate) or solved(row, reference)]
    common = [row for row in informative if solved(row, candidate) and solved(row, reference)]
    ratios = [runtime(row, candidate) / runtime(row, reference) for row in common]

    def cost(row: dict[str, str], portfolio: Portfolio) -> float:
        if solved(row, portfolio):
            return runtime(row, portfolio)
        return 1.5 * float(row["timeout_seconds"])

    return {
        "solved": sum(solved(row, candidate) for row in rows),
        "reference": sum(solved(row, reference) for row in rows),
        "only": sum(solved(row, candidate) and not solved(row, reference) for row in rows),
        "lost": sum(solved(row, reference) and not solved(row, candidate) for row in rows),
        "common": len(common),
        "geo": math.exp(statistics.mean(map(math.log, ratios))) if ratios else math.nan,
        "median": statistics.median(ratios) if ratios else math.nan,
        "wins": sum(runtime(row, candidate) + 2 < runtime(row, reference) for row in common),
        "losses": sum(runtime(row, reference) + 2 < runtime(row, candidate) for row in common),
        "par": (
            sum(cost(row, candidate) for row in informative)
            / sum(cost(row, reference) for row in informative)
        ) if informative else math.nan,
    }


def table(
    lines: list[str], title: str, rows: list[dict[str, str]], reference: Portfolio,
    portfolios: tuple[Portfolio, ...],
) -> None:
    lines += [
        "", f"## {title}", "",
        f"| Four-lane portfolio | Solved candidate/{reference.name} | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for candidate in portfolios:
        value = evaluate(rows, candidate, reference)
        lines.append(
            f"| {candidate.name} | {value['solved']}/{value['reference']} | "
            f"{value['only']}/{value['lost']} | {value['common']} | "
            f"{value['geo']:.3f} | {value['median']:.3f} | "
            f"{value['wins']}/{value['losses']} | {value['par']:.3f} |"
        )


def clustered_geo_interval(
    rows: list[dict[str, str]], candidate: Portfolio, reference: Portfolio,
    samples: int = 5000, seed: int = 20260811,
) -> tuple[float, float]:
    by_model: dict[str, list[float]] = {}
    for row in rows:
        if solved(row, candidate) and solved(row, reference):
            by_model.setdefault(row["model_id"], []).append(
                math.log(runtime(row, candidate) / runtime(row, reference))
            )
    clusters = list(by_model.values())
    if not clusters:
        return math.nan, math.nan
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        selected = [rng.choice(clusters) for _ in clusters]
        estimates.append(math.exp(statistics.mean(value for cluster in selected for value in cluster)))
    estimates.sort()
    return estimates[int(0.025 * samples)], estimates[int(0.975 * samples)]


def discordants(
    lines: list[str], rows: list[dict[str, str]], candidate: Portfolio, reference: Portfolio
) -> None:
    differences = [
        row for row in rows
        if solved(row, candidate) != solved(row, reference)
    ]
    lines += [
        "", f"## Coverage differences: {candidate.name} vs {reference.name}", "",
        "| Model | Tier | Outcome | Candidate | Reference |",
        "|---|---|---|---:|---:|",
    ]
    if not differences:
        lines.append("| None | - | - | - | - |")
        return
    for row in differences:
        candidate_value = f"{runtime(row, candidate):.3f}s" if solved(row, candidate) else "TIMEOUT"
        reference_value = f"{runtime(row, reference):.3f}s" if solved(row, reference) else "TIMEOUT"
        lines.append(
            f"| {row['model_id']} | {row['tier']} | {row['outcome']} | "
            f"{candidate_value} | {reference_value} |"
        )


def main() -> int:
    args = arguments()
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    duplicates: list[str] = []
    for path in args.inputs:
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = (row.get("model_id", row["name"]), row.get("seed_block", ""))
                if key in seen:
                    duplicates.append(":".join(key))
                    continue
                seen.add(key)
                rows.append(row)

    if not rows:
        raise ValueError("no result rows")
    portfolios = tuple(
        portfolio for portfolio in PORTFOLIOS
        if all(f"{config}_status" in rows[0] for config in portfolio.configs)
    )
    reference = next(portfolio for portfolio in PORTFOLIOS if portfolio.name == REFERENCE)
    lines = [
        "# rIC3 equal-budget phase-order portfolios", "",
        f"Models: {len(rows)}; duplicates ignored: {len(duplicates)}; "
        f"outcome conflicts: {sum(row['outcome_conflict'] == '1' for row in rows)}.",
        "Each candidate has exactly four concurrent rIC3 replicas. Mixed portfolios use "
        "two PPP replicas and two replicas of the complementary phase order.",
    ]
    table(lines, "Aggregate", rows, reference, portfolios)
    lines += ["", "## Model-clustered common-solve intervals", "", "| Portfolio | Geometric ratio 95% CI |", "|---|---:|"]
    for candidate in portfolios:
        low, high = clustered_geo_interval(rows, candidate, reference)
        lines.append(f"| {candidate.name} | {low:.3f}--{high:.3f} |")
    for tier in ("trivial", "fast", "medium", "slow", "timeout"):
        table(lines, f"Tier {tier}", [row for row in rows if row["tier"] == tier], reference, portfolios)
    for outcome in ("SAFE", "UNSAFE"):
        table(lines, f"Outcome {outcome}", [row for row in rows if row["outcome"] == outcome], reference, portfolios)
    for seed in sorted({row.get("seed_block", "") for row in rows}):
        if seed:
            table(
                lines, f"Seed {seed}",
                [row for row in rows if row.get("seed_block") == seed],
                reference, portfolios,
            )
    years = sorted({row["model_id"].split("__", 1)[0] for row in rows})
    for year in years:
        table(
            lines, f"Year {year}",
            [row for row in rows if row["model_id"].startswith(f"{year}__")],
            reference, portfolios,
        )
    for candidate in portfolios:
        if candidate == reference:
            continue
        discordants(lines, rows, candidate, reference)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows={len(rows)} duplicates={len(duplicates)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
