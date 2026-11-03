#!/usr/bin/env python3
"""Compare source-distance obligation orders with the frozen MC-AIG baseline."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}
STRATEGIES = (
    "obligation-source-near",
    "obligation-source-far",
    "obligation-mixed",
)


def load(path: Path, prefix: str) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    return {row["model_id"]: {"_prefix": prefix, **row} for row in rows}


def text(row: dict[str, str], field: str) -> str:
    return row.get(f"{row['_prefix']}_{field}", "")


def number(row: dict[str, str], field: str) -> float:
    try:
        return float(text(row, field))
    except (TypeError, ValueError):
        return 0.0


def convergence(base: dict[str, str], candidate: dict[str, str]) -> tuple[int, int]:
    base_depth = max(number(base, "pdr_depth"), 1.0)
    cand_depth = max(number(candidate, "pdr_depth"), 1.0)
    pairs = (
        (
            number(base, "unpush") / max(number(base, "push"), 1.0),
            number(candidate, "unpush") / max(number(candidate, "push"), 1.0),
        ),
        (number(base, "cti") / base_depth, number(candidate, "cti") / cand_depth),
        (number(base, "mic") / base_depth, number(candidate, "mic") / cand_depth),
    )
    improved = sum(new <= 0.9 * max(old, 1e-12) for old, new in pairs)
    regressed = sum(new >= 1.1 * max(old, 1e-12) for old, new in pairs)
    return improved, regressed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    baseline = load(args.baseline, "aig4_baseline")
    tables = {
        strategy: load(
            args.results / f"{strategy}.tsv",
            "aig4_" + strategy.replace("-", "_"),
        )
        for strategy in STRATEGIES
    }
    model_ids = sorted(baseline)
    lines = [
        "# Source-Distance Obligation Screen",
        "",
        f"Models: {len(model_ids)}; timeout: 600 seconds; four AIG lanes.",
        "",
        "| Policy | Solved | Deeper | Shallower | Conv. improved | Conv. regressed | Median depth ratio |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    details: list[tuple[float, str, str, float, float, int, int]] = []
    for strategy, rows in tables.items():
        solved = deeper = shallower = conv_good = conv_bad = 0
        ratios: list[float] = []
        for model_id in model_ids:
            if model_id not in rows:
                continue
            base = baseline[model_id]
            row = rows[model_id]
            if text(row, "status") in SOLVED:
                solved += 1
            base_depth = number(base, "pdr_depth")
            depth = number(row, "pdr_depth")
            ratios.append((depth + 1.0) / (base_depth + 1.0))
            threshold = max(3.0, 0.25 * max(base_depth, 1.0))
            if depth >= base_depth + threshold:
                deeper += 1
            if depth <= base_depth - threshold:
                shallower += 1
            improved, regressed = convergence(base, row)
            conv_good += improved >= 2 and regressed <= 1
            conv_bad += regressed >= 2 and improved <= 1
            if abs(depth - base_depth) >= threshold:
                details.append(
                    (abs(depth - base_depth), strategy, model_id, base_depth,
                     depth, improved, regressed)
                )
        lines.append(
            f"| `{strategy}` | {solved} | {deeper} | {shallower} | "
            f"{conv_good} | {conv_bad} | {statistics.median(ratios):.3f} |"
        )

    lines.extend([
        "",
        "## Largest Depth Changes",
        "",
        "| Policy | Model | Baseline depth | Candidate depth | Improved counters | Regressed counters |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ])
    for _, strategy, model_id, base_depth, depth, improved, regressed in sorted(
        details, reverse=True
    )[:30]:
        lines.append(
            f"| `{strategy}` | `{model_id}` | {base_depth:g} | {depth:g} | "
            f"{improved} | {regressed} |"
        )
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"models={len(model_ids)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
