#!/usr/bin/env python3
"""Summarize 3,600-second MIC promotion runs by progress and convergence."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


FILES = {
    "baseline": "baseline.tsv",
    "mic-near": "mic-near.tsv",
    "mic-far": "mic-far.tsv",
    "mic-feedback": "mic-feedback.tsv",
    "mic-distance-feedback": "mic-distance-feedback.tsv",
    "mic-mixed": "mic-mixed.tsv",
    "mic-structure-auto": "mic-structure-auto.tsv",
}


def load(path: Path, strategy: str) -> dict[str, dict[str, str]]:
    prefix = "aig4_" + strategy.replace("-", "_")
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    return {row["model_id"]: {"_prefix": prefix, **row} for row in rows}


def number(row: dict[str, str], field: str) -> float:
    try:
        return float(row.get(f"{row['_prefix']}_{field}", ""))
    except (TypeError, ValueError):
        return 0.0


def value(row: dict[str, str], field: str) -> str:
    return row.get(f"{row['_prefix']}_{field}", "")


def fmt(value_: float) -> str:
    if value_ >= 1000:
        return f"{value_:.0f}"
    return f"{value_:.3f}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    tables = {
        strategy: load(args.results / filename, strategy)
        for strategy, filename in FILES.items()
        if (args.results / filename).exists()
    }
    baseline = tables["baseline"]
    lines = [
        "# Distance MIC 3,600-second Promotion",
        "",
        "All rows use four AIG lanes and the deepest final lane on timeout.",
        "",
        "| Model | Policy | Status | Depth | CTI/depth | MIC/depth | Failed-push | Lemmas/depth | Mean lemma width |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for model_id in sorted(baseline):
        for strategy, rows in tables.items():
            row = rows.get(model_id)
            if row is None:
                continue
            depth = max(number(row, "pdr_depth"), 1.0)
            cti_depth = number(row, "cti") / depth
            mic_depth = number(row, "mic") / depth
            failed_push = number(row, "unpush") / max(number(row, "push"), 1.0)
            lemmas = number(row, "lemma_added")
            lemma_depth = lemmas / depth
            lemma_width = number(row, "lemma_literals") / max(lemmas, 1.0)
            lines.append(
                f"| `{model_id}` | `{strategy}` | {value(row, 'status')} | "
                f"{depth:g} | {fmt(cti_depth)} | {fmt(mic_depth)} | "
                f"{fmt(failed_push)} | {fmt(lemma_depth)} | {fmt(lemma_width)} |"
            )

    lines.extend([
        "",
        "## Interpretation Rule",
        "",
        "A larger depth is not a promotion by itself. A candidate is convergence-positive only when it improves at least two of CTI/depth, MIC/depth, failed-push ratio, and lemmas/depth without materially regressing the others. A solved result always takes precedence.",
    ])
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"models={len(baseline)} strategies={len(tables)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
