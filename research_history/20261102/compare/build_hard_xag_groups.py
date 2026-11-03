#!/usr/bin/env python3
"""Build hard-instance groups for controlled AIG/XAG mechanism experiments."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = SCRIPT_DIR / "results"
SOLVED = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--years", nargs="+", default=["2015", "2017", "2019", "2020"],
    )
    parser.add_argument("--sample-size", type=int, default=60)
    parser.add_argument("--historical-hard-seconds", type=float, default=10.0)
    parser.add_argument("--meaningful-gap", type=float, default=2.0)
    parser.add_argument("--timeout-penalty", type=float, default=2700.0)
    parser.add_argument(
        "--historical-results",
        type=Path,
        default=RESULTS_DIR / "experiments"
        / "20260716_163737_870811_seed3-b788630a_mc_comparef_r_8f302c.tsv",
    )
    parser.add_argument("--historical-aig-id", default="mc_f")
    parser.add_argument("--historical-xag-id", default="mc_r")
    parser.add_argument(
        "--base-pattern", default="hwmcc{year}_groups_mc_60.json",
    )
    parser.add_argument(
        "--features-pattern", default="results/xag_struct_{year}.tsv",
    )
    parser.add_argument(
        "--output-pattern", default="hwmcc{year}_groups_xag_hard.json",
    )
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def number(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, ""))
    except (TypeError, ValueError):
        return default


def evenly_spaced(items: list[dict[str, str]], count: int) -> list[str]:
    if count <= 0:
        return []
    ordered = sorted(
        items,
        key=lambda row: (
            number(row, "aig_ands"),
            number(row, "recognized_xors"),
            row["name"],
        ),
    )
    if count >= len(ordered):
        return [row["name"] for row in ordered]
    if count == 1:
        return [ordered[len(ordered) // 2]["name"]]
    indices = {
        round(index * (len(ordered) - 1) / (count - 1))
        for index in range(count)
    }
    return [ordered[index]["name"] for index in sorted(indices)]


def balanced_timeout_sample(
    names: set[str],
    features: dict[str, dict[str, str]],
    limit: int,
) -> list[str]:
    buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
    for name in sorted(names):
        row = features.get(name, {
            "name": name,
            "xag_tier": "missing",
            "aig_ands": "0",
            "recognized_xors": "0",
        })
        buckets[row.get("xag_tier") or "missing"].append(row)

    selected: list[str] = []
    remaining = {tier: list(rows) for tier, rows in buckets.items()}
    while len(selected) < min(limit, len(names)) and remaining:
        slots = min(limit - len(selected), len(names) - len(selected))
        per_bucket = max(1, slots // len(remaining))
        progressed = False
        for tier in sorted(remaining):
            rows = remaining[tier]
            take = min(per_bucket, len(rows), limit - len(selected))
            chosen = evenly_spaced(rows, take)
            selected.extend(chosen)
            chosen_set = set(chosen)
            remaining[tier] = [
                row for row in rows if row["name"] not in chosen_set
            ]
            progressed = progressed or bool(chosen)
            if len(selected) >= limit:
                break
        remaining = {
            tier: rows for tier, rows in remaining.items() if rows
        }
        if not progressed:
            break
    return selected


def historical_groups(args: argparse.Namespace, unique: set[str]) -> dict[str, list[str]]:
    if not args.historical_results.exists():
        return {}
    rows = read_tsv(args.historical_results)
    aig = args.historical_aig_id
    xag = args.historical_xag_id
    hard: list[str] = []
    xag_wins: list[str] = []
    aig_wins: list[str] = []
    for row in rows:
        name = row["name"]
        if name not in unique:
            continue
        aig_solved = row.get(f"{aig}_status") in SOLVED
        xag_solved = row.get(f"{xag}_status") in SOLVED
        aig_time = number(row, f"{aig}_wall_seconds", args.timeout_penalty)
        xag_time = number(row, f"{xag}_wall_seconds", args.timeout_penalty)
        if aig_solved and aig_time < args.historical_hard_seconds:
            continue
        hard.append(name)
        aig_cost = aig_time if aig_solved else args.timeout_penalty
        xag_cost = xag_time if xag_solved else args.timeout_penalty
        delta = aig_cost - xag_cost
        if delta > args.meaningful_gap:
            xag_wins.append(name)
        elif delta < -args.meaningful_gap:
            aig_wins.append(name)
    return {
        "historical_hard_unique": sorted(hard),
        "historical_xag_win": sorted(xag_wins),
        "historical_aig_win": sorted(aig_wins),
    }


def main() -> int:
    args = parse_args()
    if args.sample_size <= 0:
        raise SystemExit("sample size must be positive")
    for year in args.years:
        base_path = SCRIPT_DIR / args.base_pattern.format(year=year)
        feature_path = SCRIPT_DIR / args.features_pattern.format(year=year)
        output_path = SCRIPT_DIR / args.output_pattern.format(year=year)
        base = json.loads(base_path.read_text(encoding="utf-8"))
        base_groups = base["groups"]
        timeout_unique = set(base_groups["timeout_unique"])
        unique = set(base_groups["unique"])
        feature_rows = read_tsv(feature_path)
        features = {row["name"]: row for row in feature_rows}
        sample = balanced_timeout_sample(
            timeout_unique, features, args.sample_size,
        )
        groups: dict[str, list[str]] = {
            "timeout_unique_all": sorted(timeout_unique),
            "timeout_sample_balanced": sample,
        }
        if year == "2015":
            groups.update(historical_groups(args, unique))
            groups["hard_union"] = sorted(set(
                groups.get("historical_hard_unique", [])
            ) | set(sample))
        else:
            groups["hard_union"] = list(sample)
        output = {
            "version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "year": year,
            "source_groups": str(base_path),
            "source_features": str(feature_path),
            "historical_results": (
                str(args.historical_results) if year == "2015" else ""
            ),
            "sample_size": args.sample_size,
            "counts": {name: len(values) for name, values in groups.items()},
            "groups": groups,
        }
        output_path.write_text(
            json.dumps(output, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            f"{year}: "
            + " ".join(f"{name}={len(values)}" for name, values in groups.items())
            + f" -> {output_path}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
