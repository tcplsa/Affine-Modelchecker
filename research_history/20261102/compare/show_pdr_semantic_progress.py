#!/usr/bin/env python3
"""Show progress for the full semantic-divergence campaign."""

import csv
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "results" / "pdr_semantic_divergence_v1"
SUMMARY = ROOT / "summary.tsv"
EXPECTED = 195 * 2 * 2


def main() -> int:
    if not SUMMARY.exists():
        print(f"completed=0/{EXPECTED}")
        return 0
    with SUMMARY.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    print(f"completed={len(rows)}/{EXPECTED}")
    print(f"statuses={dict(Counter(row['status'] for row in rows))}")
    print(f"representations={dict(Counter(row['representation'] for row in rows))}")
    print(f"capped={sum(row['semantic_capped'] == '1' for row in rows)}")
    report = ROOT / "semantic_divergence_report.md"
    print(f"report={'ready' if report.exists() else 'pending'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
