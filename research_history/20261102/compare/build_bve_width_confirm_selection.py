#!/usr/bin/env python3
"""Freeze a second holdout for the non-monotonic BVE width hypothesis."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from build_bve_width_blind_selection import BUCKETS, balanced, bucket


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--exclude-selection", action="append", default=[], type=Path)
    parser.add_argument("--exclude-tsv", action="append", default=[], type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--per-bucket", type=int, default=30)
    return parser.parse_args()


def excluded_ids(args: argparse.Namespace) -> set[str]:
    result: set[str] = set()
    for path in args.exclude_selection:
        result.update(json.loads(path.read_text(encoding="utf-8"))["ids"])
    for path in args.exclude_tsv:
        with path.open(encoding="utf-8") as handle:
            result.update(row["model_id"] for row in csv.DictReader(handle, delimiter="\t"))
    return result


def main() -> int:
    args = arguments()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    excluded = excluded_ids(args)
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
        "description": "Independent confirmation holdout for non-monotonic BVE width policy",
        "selection_rule": (
            "tier=timeout; exclude width development and first blind holdout; "
            f"{args.per_bucket} per bad-cone XOR bucket"
        ),
        "candidate_policy": "use width=2 iff bad_cone_xors == 0 or bad_cone_xors >= 100",
        "bad_cone_threshold": 30,
        "bucket_counts": counts,
        "ids": [model["id"] for model in selected],
        "models": [
            {
                "id": model["id"],
                "year": model["year"],
                "family": model.get("family", model["id"]),
                "bad_cone_xors": int(model.get("bad_cone_xors", 0)),
                "bucket": bucket(model.get("bad_cone_xors")),
            }
            for model in selected
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"selected={len(selected)} excluded={len(excluded)} buckets={counts} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
