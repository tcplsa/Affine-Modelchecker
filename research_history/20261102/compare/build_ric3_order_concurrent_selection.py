#!/usr/bin/env python3
"""Freeze an unseen year/tier-stratified set for concurrent rIC3 order validation."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from build_bve_width_blind_selection import balanced


TIERS = ("trivial", "fast", "medium", "slow", "timeout")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--exclude-selection", action="append", default=[], type=Path)
    parser.add_argument("--exclude-tsv", action="append", default=[], type=Path)
    parser.add_argument("--per-stratum", type=int, default=20)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    excluded: set[str] = set()
    for path in args.exclude_selection:
        excluded.update(json.loads(path.read_text(encoding="utf-8"))["ids"])
    for path in args.exclude_tsv:
        with path.open(encoding="utf-8") as handle:
            excluded.update(row["model_id"] for row in csv.DictReader(handle, delimiter="\t"))
    years = sorted({int(model["year"]) for model in manifest})
    selected = []
    counts: Counter[str] = Counter()
    for year in years:
        for tier in TIERS:
            candidates = [
                model for model in manifest
                if model["id"] not in excluded
                and int(model["year"]) == year
                and model.get("tier") == tier
            ]
            chosen = balanced(candidates, min(args.per_stratum, len(candidates)))
            selected.extend(chosen)
            counts[f"{year}:{tier}"] = len(chosen)
    payload = {
        "version": 1,
        "description": "Unseen concurrent rIC3 BVE-order validation set",
        "selection_rule": (
            f"up to {args.per_stratum} models per year/tier stratum; "
            "exclude all BVE-width development and validation models"
        ),
        "ids": [model["id"] for model in selected],
        "stratum_counts": dict(sorted(counts.items())),
        "models": [
            {
                "id": model["id"],
                "year": model["year"],
                "tier": model["tier"],
                "family": model.get("family", model["id"]),
            }
            for model in selected
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"selected={len(selected)} excluded={len(excluded)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
