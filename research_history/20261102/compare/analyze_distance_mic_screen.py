#!/usr/bin/env python3
"""Analyze equal-budget distance/feedback MIC policies against MC-AIG."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}
STRATEGIES = (
    "baseline",
    "mic-near",
    "mic-far",
    "mic-feedback",
    "mic-distance-feedback",
    "mic-mixed",
    "mic-structure-auto",
)


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
    improved = sum(cand <= 0.9 * max(control, 1e-12) for control, cand in pairs)
    regressed = sum(cand >= 1.1 * max(control, 1e-12) for control, cand in pairs)
    return improved, regressed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    paths = {
        strategy: (
            args.results / "mic-mixed-depth.tsv"
            if strategy == "mic-mixed"
            and (args.results / "mic-mixed-depth.tsv").exists()
            else args.results / f"{strategy}.tsv"
        )
        for strategy in STRATEGIES
    }
    tables = {
        strategy: load(paths[strategy], strategy)
        for strategy in STRATEGIES
        if paths[strategy].exists()
    }
    baseline = tables["baseline"]
    model_ids = sorted(baseline)
    lines = [
        "# Distance/Feedback MIC Screen",
        "",
        f"Models: {len(model_ids)}; timeout: 600 seconds; four AIG lanes per policy.",
        "",
        "| Policy | Solved | Deeper | Shallower | Conv. improved | Conv. regressed | Median depth ratio |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    useful: dict[str, set[str]] = {}
    promotions: dict[str, set[str]] = {}
    details: list[tuple[float, str, str, float, float, int, int]] = []
    for strategy in STRATEGIES:
        rows = tables.get(strategy, {})
        solved = sum(text(row, "status") in SOLVED for row in rows.values())
        deeper = shallower = conv_good = conv_bad = 0
        ratios: list[float] = []
        useful[strategy] = set()
        for model_id in model_ids:
            if model_id not in rows:
                continue
            base = baseline[model_id]
            row = rows[model_id]
            base_depth = number(base, "pdr_depth")
            depth = number(row, "pdr_depth")
            ratios.append((depth + 1.0) / (base_depth + 1.0))
            threshold = max(3.0, 0.25 * max(base_depth, 1.0))
            if depth >= base_depth + threshold:
                deeper += 1
            if depth <= base_depth - threshold:
                shallower += 1
            improved, regressed = convergence(base, row)
            if improved >= 2 and regressed <= 1:
                conv_good += 1
                useful[strategy].add(model_id)
            if (strategy != "baseline" and depth >= base_depth + threshold
                    and improved == 3 and regressed == 0):
                promotions.setdefault(model_id, set()).add(strategy)
            if regressed >= 2 and improved <= 1:
                conv_bad += 1
            if strategy != "baseline" and abs(depth - base_depth) >= threshold:
                details.append(
                    (abs(depth - base_depth), strategy, model_id, base_depth,
                     depth, improved, regressed)
                )
        lines.append(
            f"| `{strategy}` | {solved} | {deeper} | {shallower} | {conv_good} | "
            f"{conv_bad} | {statistics.median(ratios):.3f} |"
        )

    candidate_strategies = STRATEGIES[1:]
    oracle = set().union(*(useful[strategy] for strategy in candidate_strategies))
    mixed = useful.get("mic-mixed", set())
    automatic = useful.get("mic-structure-auto", set())
    homogeneous = set().union(
        *(useful[strategy] for strategy in candidate_strategies
          if strategy not in {"mic-mixed", "mic-structure-auto"})
    )
    lines.extend(
        [
            "",
            "## Complementarity",
            "",
            f"- Models with a convergence-positive signal in any candidate: {len(oracle)}.",
            f"- Models covered by a homogeneous policy signal: {len(homogeneous)}.",
            f"- Models covered by the mixed policy signal: {len(mixed)}.",
            f"- Models covered by the structure-auto signal: {len(automatic)}.",
            f"- Manual homogeneous oracle models missed by structure-auto: "
            f"{len(homogeneous - automatic)}.",
            f"- Homogeneous-signal models missed by mixed: {len(homogeneous - mixed)}.",
            "",
            "## Largest Depth Changes",
            "",
            "| Policy | Model | Baseline depth | Candidate depth | Improved counters | Regressed counters |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, strategy, model_id, base_depth, depth, improved, regressed in sorted(
        details, reverse=True
    )[:30]:
        lines.append(
            f"| `{strategy}` | `{model_id}` | {base_depth:g} | {depth:g} | "
            f"{improved} | {regressed} |"
        )

    lines.extend(
        [
            "",
            "## 3,600-second Promotions",
            "",
            "Promotion requires a material depth gain and improvement in all "
            "three convergence-normalized counters.",
            "",
            "| Model | Promoted policies |",
            "| --- | --- |",
        ]
    )
    for model_id, strategies in sorted(promotions.items()):
        lines.append(
            f"| `{model_id}` | {', '.join(f'`{item}`' for item in sorted(strategies))} |"
        )

    if args.manifest:
        source_models = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
        selected = []
        for model in source_models:
            model_id = model["id"]
            if model_id not in promotions:
                continue
            selected.append({
                **model,
                "promoted_mic_strategies": sorted(promotions[model_id]),
            })
        (args.results / "promotion_candidates.json").write_text(
            json.dumps(
                {"schema": "mc-distance-mic-promotion-v1", "models": selected},
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )

    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"models={len(model_ids)} oracle={len(oracle)} mixed={len(mixed)} "
        f"promotions={len(promotions)} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
