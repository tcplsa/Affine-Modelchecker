#!/usr/bin/env python3
"""Freeze a family/year-balanced holdout for conditional width-weight validation."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


BUCKETS = ("zero", "1-9", "10-29", "30-99", "100+")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--exclude", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--per-bucket", type=int, default=48)
    return parser.parse_args()


def bucket(value: object) -> str:
    count = int(value or 0)
    if count == 0:
        return "zero"
    if count < 10:
        return "1-9"
    if count < 30:
        return "10-29"
    if count < 100:
        return "30-99"
    return "100+"


def balanced(models: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for model in models:
        groups[str(model["year"])][str(model.get("family", model["id"]))].append(model)
    for families in groups.values():
        for values in families.values():
            values.sort(key=lambda model: (int(model.get("size_bytes", 0)), model["id"]))
    years = sorted(groups)
    family_keys = {year: sorted(groups[year]) for year in years}
    family_cursor = {year: 0 for year in years}
    selected: list[dict[str, Any]] = []
    year_cursor = 0
    while years and len(selected) < count:
        year = years[year_cursor % len(years)]
        keys = family_keys[year]
        index = family_cursor[year] % len(keys)
        family = keys[index]
        selected.append(groups[year][family].pop(0))
        if not groups[year][family]:
            keys.pop(index)
            if keys:
                family_cursor[year] = index % len(keys)
            else:
                years.remove(year)
                year_cursor -= 1
        else:
            family_cursor[year] = (index + 1) % len(keys)
        year_cursor += 1
    if len(selected) != count:
        raise ValueError(f"requested {count} models but only selected {len(selected)}")
    return selected


def main() -> int:
    args = arguments()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    excluded = set(json.loads(args.exclude.read_text(encoding="utf-8"))["ids"])
    candidates = [
        model for model in manifest
        if model["id"] not in excluded and model.get("tier") == "timeout"
    ]
    selected: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for name in BUCKETS:
        values = [model for model in candidates if bucket(model.get("bad_cone_xors")) == name]
        chosen = balanced(values, args.per_bucket)
        selected.extend(chosen)
        counts[name] = len(chosen)
    payload = {
        "version": 1,
        "description": "Blind BVE width holdout frozen before conditional validation",
        "selection_rule": "tier=timeout, exclude development101, 48 per bad-cone XOR bucket",
        "candidate_policy": "use width=2 iff bad_cone_xors >= 30, otherwise width=0",
        "bad_cone_threshold": 30,
        "bucket_counts": counts,
        "ids": [model["id"] for model in selected],
        "models": [
            {
                "id": model["id"], "year": model["year"],
                "family": model.get("family", model["id"]),
                "bad_cone_xors": int(model.get("bad_cone_xors", 0)),
                "bucket": bucket(model.get("bad_cone_xors")),
            }
            for model in selected
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"selected={len(selected)} buckets={counts} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
