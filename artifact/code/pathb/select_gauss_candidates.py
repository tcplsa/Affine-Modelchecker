#!/usr/bin/env python3
"""Freeze Gaussian-only candidates from a three-backend screen."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with args.results.open(encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    selected_names = {
        row["name"] for row in rows
        if row["xag_cmsat_gauss_status"] == "SAFE"
        and row["xag_cadical_status"] != "SAFE"
        and row["xag_cmsat_no_gauss_status"] != "SAFE"
    }
    all_models = json.loads(args.manifest.read_text(encoding="utf-8"))
    selected = [model for model in all_models if model["stem"] in selected_names]
    if len(selected) != len(selected_names):
        missing = selected_names - {model["stem"] for model in selected}
        raise SystemExit(f"missing selected manifests: {sorted(missing)}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(selected, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"selected": len(selected), "models": [m["stem"] for m in selected]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
