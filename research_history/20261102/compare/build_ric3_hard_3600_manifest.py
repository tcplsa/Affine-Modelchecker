#!/usr/bin/env python3
"""Build the 3600-second rIC3 screening manifest from the 1800-second campaign."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}
CONFIGS = ("native_legacy4", "native_product_high4", "native_local4")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--result", required=True, action="append", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    source = json.loads(args.source_manifest.read_text(encoding="utf-8"))
    by_id = {str(model["id"]): model for model in source["models"]}
    selected: list[dict[str, object]] = []
    seen: set[str] = set()

    for result in args.result:
        with result.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                model_id = row["model_id"]
                if model_id in seen:
                    raise SystemExit(f"duplicate model_id in source results: {model_id}")
                seen.add(model_id)
                if any(row[f"{config}_status"] in VALID for config in CONFIGS):
                    continue
                if model_id not in by_id:
                    raise SystemExit(f"model missing from source manifest: {model_id}")
                model = dict(by_id[model_id])
                model["screen_1800"] = {
                    "source": str(result),
                    "timeout_seconds": float(row["timeout_seconds"]),
                    "statuses": {
                        config: row[f"{config}_status"] for config in CONFIGS
                    },
                }
                selected.append(model)

    selected.sort(key=lambda model: (str(model["year"]), str(model["id"])))
    output = {
        "schema": "ric3-hard-3600-screen-v1",
        "description": (
            "Models unsolved by native legacy, product-high, and native-local "
            "rIC3-4 configurations in the 1800-second campaign. This is a "
            "candidate pool, not yet a true-hard set."
        ),
        "source_manifest": str(args.source_manifest),
        "source_results": [str(path) for path in args.result],
        "selection": {
            "timeout_seconds": 1800,
            "configs": list(CONFIGS),
            "required": "all configurations unsolved",
        },
        "counts": {
            "models": len(selected),
            "by_year": dict(sorted(Counter(str(m["year"]) for m in selected).items())),
            "by_family": dict(Counter(str(m.get("family", "unknown")) for m in selected).most_common()),
        },
        "models": selected,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(selected)} candidates to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
