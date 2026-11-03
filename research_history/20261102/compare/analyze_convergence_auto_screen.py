#!/usr/bin/env python3
"""Analyze convergence-oriented PDR combinations on the frozen hard cohort."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}
STRATEGIES = {
    "baseline": ("mic", "baseline.tsv"),
    "mic-structure-auto": ("mic", "mic-structure-auto.tsv"),
    "obligation-source-near": ("obligation", "obligation-source-near.tsv"),
    "certify-early": ("convergence", "certify-early.tsv"),
    "mic-auto-obligation-near": (
        "convergence", "mic-auto-obligation-near-clean.tsv"
    ),
    "convergence-auto": ("convergence", "convergence-auto.tsv"),
}


def load(path: Path, strategy: str) -> dict[str, dict[str, str]]:
    prefix = "aig4_" + strategy.replace("-", "_")
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


def metrics(row: dict[str, str]) -> tuple[float, float, float, float]:
    depth = max(number(row, "pdr_depth"), 1.0)
    lemmas = number(row, "lemma_added")
    return (
        number(row, "cti") / depth,
        number(row, "mic") / depth,
        number(row, "unpush") / max(number(row, "push"), 1.0),
        lemmas / depth,
    )


def compare(base: dict[str, str], candidate: dict[str, str]) -> tuple[int, int]:
    pairs = zip(metrics(base), metrics(candidate))
    improved = regressed = 0
    for old, new in pairs:
        improved += new <= 0.9 * max(old, 1e-12)
        regressed += new >= 1.1 * max(old, 1e-12)
    return improved, regressed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mic-results", required=True, type=Path)
    parser.add_argument("--obligation-results", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    roots = {
        "mic": args.mic_results,
        "obligation": args.obligation_results,
        "convergence": args.results,
    }
    tables = {
        strategy: load(roots[group] / filename, strategy)
        for strategy, (group, filename) in STRATEGIES.items()
    }
    baseline = tables["baseline"]
    model_ids = sorted(baseline)
    lines = [
        "# Structure-Guided Convergence Screen",
        "",
        f"Models: {len(model_ids)}; timeout: 600 seconds; four AIG lanes.",
        "",
        "| Policy | Solved | Deeper | Shallower | Conv. improved | Conv. regressed | Median depth ratio | Certified | Permanent |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    promoted: dict[str, set[str]] = {}
    details: list[tuple[float, str, str, float, float, int, int]] = []
    for strategy, rows in tables.items():
        solved = deeper = shallower = conv_good = conv_bad = 0
        certified = permanent = 0.0
        ratios: list[float] = []
        for model_id in model_ids:
            row = rows[model_id]
            base = baseline[model_id]
            solved += text(row, "status") in SOLVED
            base_depth = number(base, "pdr_depth")
            depth = number(row, "pdr_depth")
            ratios.append((depth + 1.0) / (base_depth + 1.0))
            threshold = max(3.0, 0.25 * max(base_depth, 1.0))
            deeper += depth >= base_depth + threshold
            shallower += depth <= base_depth - threshold
            improved, regressed = compare(base, row)
            good = improved >= 3 and regressed <= 1
            bad = regressed >= 2 and improved <= 1
            conv_good += good
            conv_bad += bad
            certified += number(row, "certified")
            permanent += number(row, "permanent")
            if strategy != "baseline" and (
                text(row, "status") in SOLVED
                or (depth >= base_depth + threshold and good)
            ):
                promoted.setdefault(model_id, set()).add(strategy)
            if strategy != "baseline" and abs(depth - base_depth) >= threshold:
                details.append(
                    (abs(depth - base_depth), strategy, model_id, base_depth,
                     depth, improved, regressed)
                )
        lines.append(
            f"| `{strategy}` | {solved} | {deeper} | {shallower} | "
            f"{conv_good} | {conv_bad} | {statistics.median(ratios):.3f} | "
            f"{certified:g} | {permanent:g} |"
        )

    lines.extend([
        "",
        "## Largest Depth Changes",
        "",
        "| Policy | Model | Baseline depth | Candidate depth | Improved metrics | Regressed metrics |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ])
    for _, strategy, model_id, base_depth, depth, improved, regressed in sorted(
        details, reverse=True
    )[:30]:
        lines.append(
            f"| `{strategy}` | `{model_id}` | {base_depth:g} | {depth:g} | "
            f"{improved} | {regressed} |"
        )
    lines.extend([
        "",
        "## 3,600-second Promotions",
        "",
        "| Model | Policies |",
        "| --- | --- |",
    ])
    for model_id, policies in sorted(promoted.items()):
        lines.append(
            f"| `{model_id}` | {', '.join(f'`{item}`' for item in sorted(policies))} |"
        )

    source = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    selected = [
        {**model, "promoted_convergence_strategies": sorted(promoted[model["id"]])}
        for model in source if model["id"] in promoted
    ]
    (args.results / "promotion_candidates.json").write_text(
        json.dumps({"schema": "mc-convergence-promotion-v1", "models": selected},
                   indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"models={len(model_ids)} promotions={len(promoted)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
