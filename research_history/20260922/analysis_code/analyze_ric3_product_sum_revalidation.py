#!/usr/bin/env python3
"""Compare recorded product-sum-high runs with paired Native legacy reruns."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}
CONFIG = "ric3_width_w0"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", nargs="+", required=True, type=Path)
    parser.add_argument("--reference", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def read(paths: list[Path]) -> dict[tuple[str, str], dict[str, str]]:
    result: dict[tuple[str, str], dict[str, str]] = {}
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = (row["model_id"], row["seed_block"])
                if key in result:
                    raise ValueError(f"duplicate row: {key}")
                result[key] = row
    return result


def solved(row: dict[str, str]) -> bool:
    return row[f"{CONFIG}_status"] in VALID


def runtime(row: dict[str, str]) -> float:
    return float(row[f"{CONFIG}_wall_seconds"])


def evaluate(keys, candidate, reference) -> dict[str, float | int]:
    pairs = []
    for key in keys:
        cand = candidate[key]
        ref = reference[key]
        pairs.append((solved(cand), solved(ref), runtime(cand), runtime(ref), float(cand["timeout_seconds"])))
    informative = [pair for pair in pairs if pair[0] or pair[1]]
    common = [pair for pair in informative if pair[0] and pair[1]]
    ratios = [pair[2] / pair[3] for pair in common]
    cand_cost = sum(pair[2] if pair[0] else 1.5 * pair[4] for pair in informative)
    ref_cost = sum(pair[3] if pair[1] else 1.5 * pair[4] for pair in informative)
    return {
        "rows": len(pairs),
        "candidate": sum(pair[0] for pair in pairs),
        "reference": sum(pair[1] for pair in pairs),
        "only": sum(pair[0] and not pair[1] for pair in pairs),
        "lost": sum(pair[1] and not pair[0] for pair in pairs),
        "common": len(common),
        "geo": math.exp(statistics.mean(map(math.log, ratios))) if ratios else math.nan,
        "median": statistics.median(ratios) if ratios else math.nan,
        "wins": sum(pair[2] + 2 < pair[3] for pair in common),
        "losses": sum(pair[3] + 2 < pair[2] for pair in common),
        "par": cand_cost / ref_cost if ref_cost else math.nan,
    }


def main() -> int:
    args = arguments()
    candidate = read(args.candidate)
    reference = read(args.reference)
    if candidate.keys() != reference.keys():
        raise ValueError(f"input key mismatch: {len(candidate.keys() ^ reference.keys())}")
    seeds = sorted({key[1] for key in candidate})
    groups = [("Aggregate", sorted(candidate))]
    groups += [(f"Seed {seed}", sorted(key for key in candidate if key[1] == seed)) for seed in seeds]
    lines = [
        "# rIC3 product-sum-high multi-seed revalidation", "",
        "Candidate: Native product-sum-high, four replicas. Reference: Native legacy, four replicas.", "",
        "| Cohort | Rows | Solved candidate/reference | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, keys in groups:
        value = evaluate(keys, candidate, reference)
        lines.append(
            f"| {label} | {value['rows']} | {value['candidate']}/{value['reference']} | "
            f"{value['only']}/{value['lost']} | {value['common']} | {value['geo']:.3f} | "
            f"{value['median']:.3f} | {value['wins']}/{value['losses']} | {value['par']:.3f} |"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows={len(candidate)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
