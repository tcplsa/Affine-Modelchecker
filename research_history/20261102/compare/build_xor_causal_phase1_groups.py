#!/usr/bin/env python3
"""Select a small multi-year, family-diverse XOR causal discovery set."""

from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=Path(__file__).resolve().parent / "results/initial_state_large")
    parser.add_argument("--features-pattern", default=str(Path(__file__).resolve().parent / "results/xag_struct_{year}.tsv"))
    parser.add_argument("--years", nargs="+", default=["2015", "2017", "2019", "2020"])
    parser.add_argument("--per-year", type=int, default=10)
    parser.add_argument("--min-runtime", type=float, default=5.0)
    parser.add_argument("--max-runtime", type=float, default=60.0)
    parser.add_argument("--min-xors", type=int, default=32)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def number(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def choose_diverse(
    candidates: list[dict],
    count: int,
    initial: list[dict] | None = None,
    family_cap: int = 2,
) -> list[dict]:
    if count <= 0:
        return []
    initial = list(initial or [])
    population = candidates + [item for item in initial if item not in candidates]
    feature_keys = ("runtime", "recognized_xors", "bad_xor_density", "shared_cone_xors")
    vectors = {}
    for key in feature_keys:
        values = [math.log1p(item[key]) if key != "bad_xor_density" else item[key] for item in population]
        low, high = min(values), max(values)
        for item, value in zip(population, values):
            vectors.setdefault(item["name"], []).append((value - low) / (high - low) if high > low else 0.0)
    selected = list(initial)
    picked: list[dict] = []
    family_counts: Counter[str] = Counter(item["family"] for item in selected)
    remaining = sorted(candidates, key=lambda item: (item["family"], item["name"]))
    while remaining and len(picked) < count:
        allowed = [item for item in remaining if family_counts[item["family"]] < family_cap]
        if not allowed:
            family_cap += 1
            continue
        if not selected:
            pick = max(allowed, key=lambda item: (item["recognized_xors"], item["runtime"], item["name"]))
        else:
            def distance(item: dict) -> tuple[float, float, str]:
                vector = vectors[item["name"]]
                nearest = min(
                    sum((left - right) ** 2 for left, right in zip(vector, vectors[other["name"]]))
                    for other in selected
                )
                return nearest, item["runtime"], item["name"]
            pick = max(allowed, key=distance)
        selected.append(pick)
        picked.append(pick)
        family_counts[pick["family"]] += 1
        remaining.remove(pick)
    return picked


def main() -> int:
    args = parse_args()
    observations: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for path in glob.glob(str(args.results_dir / "hwmcc*.tsv")):
        with open(path, "r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if row.get("state_000_status") in SOLVED:
                    observations[(row["year"], row["name"])].append(row)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    for year in args.years:
        feature_rows = {}
        feature_path = Path(args.features_pattern.format(year=year))
        with feature_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                feature_rows[row["name"]] = row
        candidates = []
        for (row_year, name), rows in observations.items():
            if row_year != year or name not in feature_rows:
                continue
            runtime = statistics.median(number(row["state_000_pdr_runtime"]) for row in rows)
            feature = feature_rows[name]
            recognized = int(number(feature.get("recognized_xors", "0")))
            if not (args.min_runtime <= runtime <= args.max_runtime) or recognized < args.min_xors:
                continue
            outcome = Counter(row["state_000_status"] for row in rows).most_common(1)[0][0]
            candidates.append({
                "name": name,
                "path": feature["aig_path"],
                "family": feature["family"],
                "outcome": outcome,
                "runtime": runtime,
                "recognized_xors": recognized,
                "bad_xor_density": number(feature.get("bad_xor_density", "0")),
                "shared_cone_xors": int(number(feature.get("shared_cone_xors", "0"))),
            })
        unsafe_target = min(4, sum(item["outcome"] == "UNSAFE" for item in candidates))
        unsafe = choose_diverse([item for item in candidates if item["outcome"] == "UNSAFE"], unsafe_target)
        safe = choose_diverse(
            [item for item in candidates if item["outcome"] == "SAFE"],
            args.per_year - len(unsafe),
            initial=unsafe,
        )
        selected = unsafe + safe
        if len(selected) < args.per_year:
            remaining = [item for item in candidates if item not in selected]
            selected += choose_diverse(remaining, args.per_year - len(selected), initial=selected)
        selected.sort(key=lambda item: item["name"])
        payload = {
            "version": 1,
            "year": year,
            "selection": {
                "min_runtime": args.min_runtime,
                "max_runtime": args.max_runtime,
                "min_xors": args.min_xors,
                "per_year": args.per_year,
            },
            "counts": {"phase1": len(selected)},
            "groups": {"phase1": [item["name"] for item in selected]},
            "records": selected,
        }
        output = args.output_dir / f"hwmcc{year}_groups_xor_causal.json"
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (args.output_dir / f"hwmcc{year}_xor_causal_paths.txt").write_text(
            "".join(item["path"] + "\n" for item in selected), encoding="utf-8"
        )
        summary.extend({"year": year, **item} for item in selected)
        print(f"year={year} candidates={len(candidates)} selected={len(selected)} unsafe={sum(item['outcome']=='UNSAFE' for item in selected)}")
    (args.output_dir / "selection.json").write_text(
        json.dumps({"version": 1, "records": summary}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
