#!/usr/bin/env python3
"""Select balanced hard-2015 circuits for conditional XOR validation."""

from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-pattern", required=True)
    parser.add_argument("--structure", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--per-direction", type=int, default=12)
    parser.add_argument("--candidate-multiplier", type=int, default=2)
    parser.add_argument("--gate-features", type=Path)
    return parser.parse_args()


def number(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def cost(row: dict[str, str], config: str) -> tuple[float, bool]:
    solved = row.get(f"{config}_status") in SOLVED
    penalty = number(row.get("timeout_seconds", "1800"), 1800.0) * 1.5
    return (number(row.get(f"{config}_wall_seconds", ""), penalty) if solved else penalty), solved


def choose(records: list[dict], count: int, family_cap: int = 2) -> list[dict]:
    selected = []
    family_counts = defaultdict(int)
    for record in sorted(records, key=lambda item: (-item["score"], item["family"], item["name"])):
        if family_counts[record["family"]] >= family_cap:
            continue
        selected.append(record)
        family_counts[record["family"]] += 1
        if len(selected) == count:
            break
    if len(selected) < count:
        for record in sorted(records, key=lambda item: (-item["score"], item["name"])):
            if record in selected:
                continue
            selected.append(record)
            if len(selected) == count:
                break
    return selected


def main() -> int:
    args = parse_args()
    structure = {}
    with args.structure.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            structure[row["name"]] = row
    observations = defaultdict(list)
    for path in sorted(glob.glob(args.results_pattern)):
        with open(path, "r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                observations[row["name"]].append(row)
    f23_counts = None
    if args.gate_features:
        f23_counts = defaultdict(int)
        with args.gate_features.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if row["in_next"] == "1" and 2 <= int(row["fanout"]) < 4:
                    f23_counts[row["name"]] += 1
    paths = {path.stem: path for path in args.data_dir.glob("*.aig")}
    records = []
    for name, rows in observations.items():
        if name not in structure or name not in paths:
            continue
        if f23_counts is not None and f23_counts.get(name, 0) == 0:
            continue
        aig_costs, xag_costs = [], []
        aig_solves = xag_solves = 0
        for row in rows:
            aig_cost, aig_solved = cost(row, "aig")
            xag_cost, xag_solved = cost(row, "xag_all")
            aig_costs.append(aig_cost)
            xag_costs.append(xag_cost)
            aig_solves += int(aig_solved)
            xag_solves += int(xag_solved)
        if not aig_solves and not xag_solves:
            continue
        aig_total, xag_total = sum(aig_costs), sum(xag_costs)
        delta = aig_total - xag_total
        direction = "xag_win" if delta > 2 else "aig_win" if delta < -2 else "neutral"
        scale = max(min(aig_total, xag_total), 1.0)
        score = abs(delta) / scale * math.log1p(statistics.median(aig_costs + xag_costs))
        feature = structure[name]
        records.append({
            "name": name,
            "path": str(paths[name]),
            "family": feature.get("family", name),
            "direction": direction,
            "score": score,
            "aig_total": aig_total,
            "xag_total": xag_total,
            "aig_solves": aig_solves,
            "xag_solves": xag_solves,
            "solver_seeds": len(rows),
            "recognized_xors": int(number(feature.get("recognized_xors", "0"))),
            "fanout_2_3_xors": 0 if f23_counts is None else f23_counts.get(name, 0),
        })
    target = args.per_direction * (args.candidate_multiplier if f23_counts is None else 1)
    selected = []
    for direction in ("xag_win", "aig_win"):
        selected.extend(choose([record for record in records if record["direction"] == direction], target))
    if len(selected) < 2 * target:
        remaining = [record for record in records if record not in selected]
        selected.extend(choose(remaining, 2 * target - len(selected)))
    selected.sort(key=lambda item: (item["direction"], item["family"], item["name"]))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "year": "2015",
        "selection_stage": "candidate" if f23_counts is None else "final",
        "counts": {"hard_phase3": len(selected)},
        "groups": {"hard_phase3": [record["name"] for record in selected]},
        "records": selected,
    }
    (args.output_dir / "hwmcc2015_groups_xor_causal_hard.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    (args.output_dir / "hard2015_paths.txt").write_text(
        "".join(record["path"] + "\n" for record in selected), encoding="utf-8",
    )
    print(
        f"stage={payload['selection_stage']} selected={len(selected)} "
        f"xag_win={sum(r['direction']=='xag_win' for r in selected)} "
        f"aig_win={sum(r['direction']=='aig_win' for r in selected)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

