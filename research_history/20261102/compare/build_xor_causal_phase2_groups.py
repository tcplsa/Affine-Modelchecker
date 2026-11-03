#!/usr/bin/env python3
"""Filter the phase-1 set to circuits containing next-state fanout-2/3 XORs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase1-design", required=True, type=Path)
    parser.add_argument("--features-pattern", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--years", nargs="+", default=["2015", "2017", "2019", "2020"])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selection = json.loads((args.phase1_design / "selection.json").read_text(encoding="utf-8"))
    records = selection["records"]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    for year in args.years:
        counts = {}
        feature_path = Path(args.features_pattern.format(year=year))
        with feature_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if row["in_next"] == "1" and 2 <= int(row["fanout"]) < 4:
                    counts[row["name"]] = counts.get(row["name"], 0) + 1
        selected = [
            {**record, "fanout_2_3_xors": counts[record["name"]]}
            for record in records
            if record["year"] == year and counts.get(record["name"], 0) > 0
        ]
        payload = {
            "version": 1,
            "year": year,
            "counts": {"phase2": len(selected)},
            "groups": {"phase2": [record["name"] for record in selected]},
            "records": selected,
        }
        (args.output_dir / f"hwmcc{year}_groups_xor_causal_phase2.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        summary.extend(selected)
        print(f"year={year} selected={len(selected)} f23_xors={sum(counts.get(record['name'], 0) for record in selected)}")
    (args.output_dir / "selection.json").write_text(
        json.dumps({"version": 1, "records": summary}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
