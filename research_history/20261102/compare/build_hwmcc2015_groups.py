#!/usr/bin/env python3
"""Build HWMCC benchmark groups from an existing result TSV."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Split HWMCC into regular/hard groups using prior run records."
    )
    parser.add_argument(
        "--year",
        type=str,
        default="2017",
        choices=["2015", "2017", "2019", "2020", "2024", "2025"],
        help="HWMCC year; default 2017",
    )
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--timeout", type=float, default=1800.0)
    return parser.parse_args()


def is_timeout(row: dict[str, str], timeout: float) -> bool:
    if row.get("timed_out") == "1":
        return True
    if row.get("status", "").upper() == "TIMEOUT":
        return True
    try:
        return float(row.get("wall_seconds", "0") or "0") >= timeout
    except ValueError:
        return False


def main() -> int:
    args = parse_args()
    if args.input is None:
        args.input = SCRIPT_DIR / "results" / f"ric3_hwmcc{args.year}.tsv"
    if args.output is None:
        args.output = SCRIPT_DIR / f"hwmcc{args.year}_groups_ric3_{int(args.timeout)}.json"
    if not args.input.exists():
        raise SystemExit(f"missing input TSV: {args.input}")

    groups: dict[str, list[str]] = {"regular": [], "hard": [], "other": []}
    rows: list[dict[str, str]] = []
    with args.input.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            rows.append(row)
            name = row.get("name", "")
            if not name:
                continue
            status = row.get("status", "").upper()
            if is_timeout(row, args.timeout):
                groups["hard"].append(name)
            elif status in {"SAFE", "UNSAFE"}:
                groups["regular"].append(name)
            else:
                groups["other"].append(name)

    for names in groups.values():
        names.sort()

    out = {
        "source": str(args.input),
        "timeout_seconds": args.timeout,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {name: len(values) for name, values in groups.items()},
        "groups": groups,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, sort_keys=True)
        f.write("\n")

    print(
        f"wrote {args.output} "
        f"regular={len(groups['regular'])} hard={len(groups['hard'])} other={len(groups['other'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
