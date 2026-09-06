#!/usr/bin/env python3
"""Summarize cross-family Gaussian coverage without averaging timeouts away."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


CONFIGS = ("xag_cadical", "xag_cmsat_no_gauss", "xag_cmsat_gauss")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = list(csv.DictReader(args.results.open(encoding="utf-8"), delimiter="\t"))
    manifest = {
        item["stem"]: item
        for item in json.loads(args.manifest.read_text(encoding="utf-8"))
    }
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    strict = []
    accelerated = []
    for row in rows:
        family = row["family"]
        statuses = {config: row[f"{config}_status"] for config in CONFIGS}
        for config, status in statuses.items():
            if status == "SAFE":
                counts[family][config] += 1
        if (statuses["xag_cadical"] != "SAFE"
                and statuses["xag_cmsat_no_gauss"] != "SAFE"
                and statuses["xag_cmsat_gauss"] == "SAFE"):
            strict.append(row["name"])
        if statuses["xag_cadical"] == statuses["xag_cmsat_gauss"] == "SAFE":
            cadical = float(row["xag_cadical_pdr_runtime"])
            gauss = float(row["xag_cmsat_gauss_pdr_runtime"])
            if gauss > 0 and cadical / gauss >= 2:
                accelerated.append((cadical / gauss, row["name"]))

    lines = [
        "# Shallow Linear-Scope Generalization",
        "",
        f"Models: {len(rows)}",
        "",
        "| Family | Models | CaDiCaL solved | native XOR solved | Gaussian solved | Gaussian-only |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    family_sizes = Counter(row["family"] for row in rows)
    for family in sorted(family_sizes):
        family_strict = sum(name in strict for name in (
            row["name"] for row in rows if row["family"] == family
        ))
        lines.append(
            f"| {family} | {family_sizes[family]} | "
            f"{counts[family]['xag_cadical']} | "
            f"{counts[family]['xag_cmsat_no_gauss']} | "
            f"{counts[family]['xag_cmsat_gauss']} | {family_strict} |"
        )
    lines.extend(["", "## Strict Gaussian-only points", ""])
    lines.extend(f"- `{name}`" for name in sorted(strict))
    lines.extend(["", "## At least 2x faster than CaDiCaL", ""])
    lines.extend(
        f"- {ratio:.2f}x `{name}`" for ratio, name in sorted(accelerated, reverse=True)
    )
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "models": len(rows),
        "strict_gaussian_only": len(strict),
        "at_least_2x": len(accelerated),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

