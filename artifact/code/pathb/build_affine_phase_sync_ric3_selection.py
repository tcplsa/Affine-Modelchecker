#!/usr/bin/env python3
"""Freeze phase-sync circuits with two-seed MC Gaussian confirmation."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["name"]: row for row in csv.DictReader(handle, delimiter="\t")}


def stable_names(paths: list[Path]) -> set[str]:
    by_file = [rows(path) for path in paths]
    common = set.intersection(*(set(data) for data in by_file))
    return {
        name
        for name in common
        if all(
            data[name].get("baseline_cadical_4x_status") == "TIMEOUT"
            and data[name].get("mixed_cadical_cmsat_gauss_4x_status") == "SAFE"
            for data in by_file
        )
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument(
        "--confirmation-set", type=Path, action="append", nargs="+", required=True,
        help="Two or more confirmation TSVs for the same generated family",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    names = set().union(*(stable_names(paths) for paths in args.confirmation_set))
    models = []
    for manifest_path in args.manifest:
        for entry in json.loads(manifest_path.read_text(encoding="utf-8")):
            path = Path(entry["paths"]["aag"])
            if path.stem not in names:
                continue
            params = entry["params"]
            models.append({
                "id": path.stem,
                "path": entry["paths"]["aag"],
                "year": "generated",
                "family": entry["family"],
                "expected": entry["expected"],
                "width": params["width"],
                "rounds": params["rounds"],
                "delay": params["delay"],
                "generator_seed": params["seed"],
                "aag_sha256": entry["aag_sha256"],
            })
    models.sort(key=lambda item: (item["generator_seed"], item["rounds"], item["delay"], item["width"]))
    if len(models) != len(names):
        raise SystemExit("confirmation and manifests disagree on selected models")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "selection_rule": (
            "Both MC confirmation seeds: 4x CaDiCaL-XAG TIMEOUT and "
            "3x CaDiCaL + 1x CMSat Gaussian SAFE within 1800 seconds"
        ),
        "models": models,
    }, indent=2) + "\n", encoding="utf-8")
    print("selected=%s" % len(models))
    for model in models:
        print(model["id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
