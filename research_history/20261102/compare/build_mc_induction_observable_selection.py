#!/usr/bin/env python3
"""Build a bounded SAFE cohort for detailed PDR induction observables."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path


CANDIDATE = "xag_sumhigh4"
REFERENCE = "xag_legacy4"
TIERS = ("fast", "medium", "slow", "timeout")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--per-tier", type=int, default=15)
    parser.add_argument("--max-seconds", type=float, default=300.0)
    return parser.parse_args()


def spread_select(records: list[dict[str, object]], count: int) -> list[dict[str, object]]:
    records.sort(key=lambda item: (float(item["runtime"]), str(item["id"])))
    if len(records) <= count:
        return records
    selected = []
    used_families: set[str] = set()
    targets = [index * (len(records) - 1) / (count - 1) for index in range(count)]
    available = list(range(len(records)))
    for target in targets:
        ordered = sorted(available, key=lambda index: (abs(index - target), index))
        index = next(
            (candidate for candidate in ordered
             if str(records[candidate]["family"]) not in used_families),
            ordered[0],
        )
        selected.append(records[index])
        used_families.add(str(records[index]["family"]))
        available.remove(index)
    return selected


def main() -> int:
    args = arguments()
    rows = []
    for path in args.inputs:
        with path.open(encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle, delimiter="\t"))
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["model_id"]].append(row)

    eligible: dict[str, list[dict[str, object]]] = defaultdict(list)
    for model_id, model_rows in grouped.items():
        first = model_rows[0]
        tier = first["tier"]
        if tier not in TIERS or len(model_rows) != len(args.inputs):
            continue
        if any(row["outcome"] != "SAFE" for row in model_rows):
            continue
        if any(
            row[f"{config}_status"] != "SAFE"
            or float(row[f"{config}_wall_seconds"]) > args.max_seconds
            for row in model_rows for config in (CANDIDATE, REFERENCE)
        ):
            continue
        runtimes = [
            math.sqrt(
                float(row[f"{CANDIDATE}_wall_seconds"])
                * float(row[f"{REFERENCE}_wall_seconds"])
            )
            for row in model_rows
        ]
        eligible[tier].append({
            "id": model_id,
            "family": first["family"],
            "tier": tier,
            "runtime": math.exp(sum(math.log(value) for value in runtimes) / len(runtimes)),
        })

    selected = []
    for tier in TIERS:
        if len(eligible[tier]) < args.per_tier:
            raise ValueError(f"only {len(eligible[tier])} eligible {tier} models")
        selected.extend(spread_select(eligible[tier], args.per_tier))
    document = {
        "version": 1,
        "description": (
            "SAFE models solved by legacy and sum-high in all three strict seed blocks, "
            f"each historical run <= {args.max_seconds:g}s; runtime-spread selection."
        ),
        "ids": [item["id"] for item in selected],
        "models": selected,
        "stratum_counts": {
            tier: sum(item["tier"] == tier for item in selected) for tier in TIERS
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"selected={len(selected)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
