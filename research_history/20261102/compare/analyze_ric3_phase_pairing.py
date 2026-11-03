#!/usr/bin/env python3
"""Analyze paired-versus-split seed layouts for native phase portfolios."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from analyze_ric3_phase_portfolio import Portfolio, clustered_geo_interval, discordants, table


PORTFOLIOS = (
    Portfolio("4xPPP", ("phase_4ppp",)),
    Portfolio("2PPP+2LPP paired seeds", ("phase_2p2l_paired",)),
    Portfolio("2PPP+2LPP split seeds", ("phase_2p2l_split",)),
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
    for path in args.inputs:
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = (row["model_id"], row["seed_block"])
                if key not in seen:
                    seen.add(key)
                    rows.append(row)
    lines = [
        "# rIC3 phase portfolio seed-layout test", "",
        f"Observations: {len(rows)}; models: {len({row['model_id'] for row in rows})}; "
        f"outcome conflicts: {sum(row['outcome_conflict'] == '1' for row in rows)}.",
        "All candidates use a native four-lane shared-termination portfolio. The paired "
        "candidate repeats the first two random seeds once under PPP and once under LPP; "
        "the split candidate assigns four distinct seeds across the same lane types.",
    ]
    table(lines, "Aggregate", rows, REFERENCE, PORTFOLIOS)
    lines += ["", "## Model-clustered common-solve intervals", "", "| Portfolio | Geometric ratio 95% CI |", "|---|---:|"]
    for candidate in PORTFOLIOS:
        low, high = clustered_geo_interval(rows, candidate, REFERENCE)
        lines.append(f"| {candidate.name} | {low:.3f}--{high:.3f} |")
    for tier in ("slow", "timeout"):
        table(lines, f"Tier {tier}", [row for row in rows if row["tier"] == tier], REFERENCE, PORTFOLIOS)
    for seed in sorted({row["seed_block"] for row in rows}):
        table(lines, f"Seed {seed}", [row for row in rows if row["seed_block"] == seed], REFERENCE, PORTFOLIOS)
    for candidate in PORTFOLIOS[1:]:
        discordants(lines, rows, candidate, REFERENCE)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows={len(rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
