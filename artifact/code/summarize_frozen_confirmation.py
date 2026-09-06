#!/usr/bin/env python3
"""Summarize strict Gaussian-only outcomes from frozen confirmation TSVs."""

from __future__ import annotations

import csv
import sys
from pathlib import Path


def load(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return {row["name"]: row for row in csv.DictReader(stream, delimiter="\t")}


def main() -> int:
    runs = [load(Path(value)) for value in sys.argv[1:]]
    common = set.intersection(*(set(run) for run in runs))
    strict = [
        name for name in sorted(common)
        if all(
            run[name]["cadical_4x_status"] == "TIMEOUT"
            and run[name]["cmsat_no_gauss_4x_status"] == "TIMEOUT"
            and run[name]["cmsat_gauss_4x_status"] == "SAFE"
            for run in runs
        )
    ]
    print(f"runs={len(runs)}")
    print(f"common_models={len(common)}")
    print(f"strict_gaussian_only={len(strict)}")
    for name in strict:
        times = ",".join(run[name]["cmsat_gauss_4x_wall_seconds"] for run in runs)
        print(f"{name}\t{times}")
    return 0 if len(strict) == len(common) == 15 else 1


if __name__ == "__main__":
    raise SystemExit(main())
