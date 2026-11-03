#!/usr/bin/env python3
"""Replay a static AIG/XAG selector against completed comparison results."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping


SOLVED = {"SAFE", "UNSAFE"}


@dataclass
class Run:
    status: str
    seconds: float

    @property
    def solved(self) -> bool:
        return self.status in SOLVED


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def index_rows(rows: Iterable[dict[str, str]]) -> Dict[str, dict[str, str]]:
    return {row["name"]: row for row in rows if row.get("name")}


def read_run(row: Mapping[str, str], prefix: str) -> Run:
    status = row.get(f"{prefix}_status", "UNKNOWN").upper()
    wall_text = row.get(f"{prefix}_wall_seconds", row.get(f"{prefix}_wall", ""))
    try:
        seconds = float(wall_text)
    except (TypeError, ValueError):
        seconds = 0.0
    return Run(status, seconds)


def score(run: Run, timeout: float, timeout_multiplier: float) -> float:
    return run.seconds if run.solved else timeout * timeout_multiplier


def percent_gain(baseline: float, candidate: float) -> float:
    return 100.0 * (baseline - candidate) / baseline if baseline else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the frozen deep-XOR selector: choose XAG when next_depth and "
            "estimated AND reduction both exceed their thresholds."
        )
    )
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--aig-prefix", required=True)
    parser.add_argument("--xag-prefix", required=True)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--timeout-multiplier", type=float, default=2.0)
    parser.add_argument("--min-next-depth", type=int, default=120)
    parser.add_argument("--min-and-reduction", type=float, default=0.12)
    parser.add_argument(
        "--ignore-both-unsolved",
        action="store_true",
        help="Drop rows where neither representation solved the model.",
    )
    args = parser.parse_args()

    features = index_rows(read_rows(args.features))
    result_rows = read_rows(args.results)
    totals = {"aig": 0.0, "xag": 0.0, "selector": 0.0, "oracle": 0.0}
    solved = {"aig": 0, "xag": 0, "selector": 0}
    wins = {"aig": 0, "xag": 0, "tie": 0}
    selected = 0
    selected_xag_wins = 0
    selected_aig_wins = 0
    conflicts = 0
    used = 0
    missing_features = 0

    for row in result_rows:
        feature = features.get(row.get("name", ""))
        if feature is None:
            missing_features += 1
            continue
        aig = read_run(row, args.aig_prefix)
        xag = read_run(row, args.xag_prefix)
        if args.ignore_both_unsolved and not aig.solved and not xag.solved:
            continue
        if aig.solved and xag.solved and aig.status != xag.status:
            conflicts += 1
            continue

        use_xag = (
            int(feature["next_depth"]) >= args.min_next_depth
            and float(feature["and_reduction"]) >= args.min_and_reduction
        )
        chosen = xag if use_xag else aig
        if use_xag:
            selected += 1
        used += 1

        aig_score = score(aig, args.timeout, args.timeout_multiplier)
        xag_score = score(xag, args.timeout, args.timeout_multiplier)
        totals["aig"] += aig_score
        totals["xag"] += xag_score
        totals["selector"] += score(chosen, args.timeout, args.timeout_multiplier)
        totals["oracle"] += min(aig_score, xag_score)
        solved["aig"] += int(aig.solved)
        solved["xag"] += int(xag.solved)
        solved["selector"] += int(chosen.solved)

        if abs(aig_score - xag_score) < 1e-9:
            wins["tie"] += 1
        elif xag_score < aig_score:
            wins["xag"] += 1
            selected_xag_wins += int(use_xag)
        else:
            wins["aig"] += 1
            selected_aig_wins += int(use_xag)

    if not used:
        raise SystemExit("no result rows matched the structural feature file")

    print(f"cases\t{used}")
    print(f"missing_features\t{missing_features}")
    print(f"outcome_conflicts\t{conflicts}")
    print(f"selected_xag\t{selected}")
    print(f"selected_xag_rate\t{selected / used:.6f}")
    print(f"selected_region_xag_wins\t{selected_xag_wins}")
    print(f"selected_region_aig_wins\t{selected_aig_wins}")
    print(f"all_xag_wins\t{wins['xag']}")
    print(f"all_aig_wins\t{wins['aig']}")
    print(f"ties\t{wins['tie']}")
    for strategy in ("aig", "xag", "selector", "oracle"):
        print(f"{strategy}_par_score\t{totals[strategy]:.6f}")
    print(f"xag_gain_vs_aig_percent\t{percent_gain(totals['aig'], totals['xag']):.6f}")
    print(
        "selector_gain_vs_aig_percent\t"
        f"{percent_gain(totals['aig'], totals['selector']):.6f}"
    )
    print(
        "selector_oracle_gap_percent\t"
        f"{100.0 * (totals['selector'] - totals['oracle']) / totals['oracle']:.6f}"
    )
    for strategy in ("aig", "xag", "selector"):
        print(f"{strategy}_solved\t{solved[strategy]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
