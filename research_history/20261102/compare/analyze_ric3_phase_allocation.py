#!/usr/bin/env python3
"""Analyze native four-lane PPP/LPP allocation experiments."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from analyze_ric3_phase_portfolio import (
    Portfolio,
    clustered_geo_interval,
    discordants,
    table,
)


PORTFOLIOS = tuple(
    Portfolio(f"{ppp}xPPP+{4 - ppp}xLPP", (f"phase_{ppp}p{4 - ppp}l",))
    for ppp in range(4, -1, -1)
)
REFERENCE = PORTFOLIOS[0]


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    duplicates = 0
    for path in args.inputs:
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = (row["model_id"], row["seed_block"])
                if key in seen:
                    duplicates += 1
                    continue
                seen.add(key)
                rows.append(row)
    if not rows:
        raise ValueError("no result rows")

    lines = [
        "# rIC3 native phase-allocation screen", "",
        f"Observations: {len(rows)}; models: {len({row['model_id'] for row in rows})}; "
        f"duplicates ignored: {duplicates}; outcome conflicts: "
        f"{sum(row['outcome_conflict'] == '1' for row in rows)}.",
        "Every candidate is one native four-replica portfolio. A result from any lane "
        "terminates all sibling lanes in that candidate.",
    ]
    table(lines, "Aggregate", rows, REFERENCE, PORTFOLIOS)
    lines += ["", "## Model-clustered common-solve intervals", "", "| Portfolio | Geometric ratio 95% CI |", "|---|---:|"]
    for candidate in PORTFOLIOS:
        low, high = clustered_geo_interval(rows, candidate, REFERENCE)
        lines.append(f"| {candidate.name} | {low:.3f}--{high:.3f} |")
    for tier in ("slow", "timeout"):
        table(lines, f"Tier {tier}", [row for row in rows if row["tier"] == tier], REFERENCE, PORTFOLIOS)
    for outcome in ("SAFE", "UNSAFE"):
        table(lines, f"Outcome {outcome}", [row for row in rows if row["outcome"] == outcome], REFERENCE, PORTFOLIOS)
    for seed in sorted({row["seed_block"] for row in rows}):
        table(lines, f"Seed {seed}", [row for row in rows if row["seed_block"] == seed], REFERENCE, PORTFOLIOS)
    for candidate in PORTFOLIOS[1:]:
        discordants(lines, rows, candidate, REFERENCE)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows={len(rows)} duplicates={duplicates} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
