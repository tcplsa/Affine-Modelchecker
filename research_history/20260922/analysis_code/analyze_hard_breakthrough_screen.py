#!/usr/bin/env python3
"""Compare long-budget hard-frontier strategies against four-lane MC-AIG."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}
STRATEGIES = (
    "baseline", "source-init", "source-zero", "source-random", "first-phase", "heuristic",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def load(path: Path, strategy: str) -> dict[str, dict[str, str]]:
    prefix = "aig4_" + strategy.replace("-", "_")
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    return {row["model_id"]: {"prefix": prefix, **row} for row in rows}


def value(row: dict[str, str], field: str) -> str:
    return row.get(f"{row['prefix']}_{field}", "")


def number(row: dict[str, str], field: str) -> float:
    try:
        return float(value(row, field))
    except (TypeError, ValueError):
        return 0.0


def ratio(row: dict[str, str], numerator: str, denominator: str) -> float:
    return number(row, numerator) / max(number(row, denominator), 1.0)


def main() -> int:
    args = parse_args()
    models = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    by_id = {model["id"]: model for model in models}
    tables = {
        strategy: load(args.results / f"{strategy}.tsv", strategy)
        for strategy in STRATEGIES
        if (args.results / f"{strategy}.tsv").exists()
    }
    baseline = tables.get("baseline", {})
    lines = ["# MC hard-breakthrough screen", ""]
    lines.append(f"Candidate models: {len(models)}; completed strategies: {len(tables)}.")
    lines.extend(["", "| Strategy | Rows | Solved | SAFE | UNSAFE | Candidate-only | Baseline-only |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"])
    solved_promotions: set[str] = set()
    details = []
    for strategy in STRATEGIES:
        rows = tables.get(strategy, {})
        solved = {key for key, row in rows.items() if value(row, "status") in SOLVED}
        safe = sum(value(row, "status") == "SAFE" for row in rows.values())
        unsafe = sum(value(row, "status") == "UNSAFE" for row in rows.values())
        base_solved = {key for key, row in baseline.items() if value(row, "status") in SOLVED}
        candidate_only = solved - base_solved if strategy != "baseline" else set()
        baseline_only = base_solved - solved if strategy != "baseline" else set()
        solved_promotions.update(candidate_only)
        lines.append(
            f"| `{strategy}` | {len(rows)} | {len(solved)} | {safe} | {unsafe} | "
            f"{len(candidate_only)} | {len(baseline_only)} |"
        )
        for key in sorted(candidate_only):
            row = rows[key]
            details.append((strategy, key, value(row, "status"), number(row, "wall_seconds"), number(row, "pdr_depth")))

    if details:
        lines.extend(["", "## Candidate-only solves", "", "| Strategy | Model | Family | Result | Seconds | Depth |", "| --- | --- | --- | --- | ---: | ---: |"])
        for strategy, key, status, seconds, depth in sorted(details):
            lines.append(
                f"| `{strategy}` | `{key}` | `{by_id[key]['family']}` | {status} | {seconds:.2f} | {depth:g} |"
            )

    diagnostic_progress: set[str] = set()
    if baseline:
        lines.extend(["", "## Unsolved progress", ""])
        for strategy in STRATEGIES[1:]:
            rows = tables.get(strategy, {})
            gains = []
            for key, row in rows.items():
                if key not in baseline or value(row, "status") in SOLVED:
                    continue
                base_depth = number(baseline[key], "pdr_depth")
                depth = number(row, "pdr_depth")
                if depth >= base_depth + max(3.0, 0.25 * max(base_depth, 1.0)):
                    gains.append((depth - base_depth, key))
            lines.append(f"- `{strategy}`: {len(gains)} models reached a materially deeper frame than baseline.")

        heuristic = tables.get("heuristic", {})
        if heuristic:
            for key, row in heuristic.items():
                if key not in baseline or value(row, "status") in SOLVED:
                    continue
                base = baseline[key]
                base_depth = number(base, "pdr_depth")
                depth = number(row, "pdr_depth")
                if depth < base_depth + max(3.0, 0.25 * max(base_depth, 1.0)):
                    continue
                comparisons = (
                    (ratio(base, "unpush", "push"), ratio(row, "unpush", "push")),
                    (
                        number(base, "cti") / max(base_depth, 1.0),
                        number(row, "cti") / max(depth, 1.0),
                    ),
                    (
                        number(base, "mic") / max(base_depth, 1.0),
                        number(row, "mic") / max(depth, 1.0),
                    ),
                )
                improved = sum(candidate <= 0.9 * max(control, 1e-12)
                               for control, candidate in comparisons)
                regressed = sum(candidate >= 1.1 * max(control, 1e-12)
                                for control, candidate in comparisons)
                if improved >= 2 and regressed <= 1:
                    diagnostic_progress.add(key)
            lines.append(
                f"- `heuristic`: {len(diagnostic_progress)} of the deeper-frame models also "
                "improved at least two convergence-normalized counters."
            )

    promotion = [by_id[key] for key in sorted(solved_promotions)]
    (args.results / "promotion_candidates.json").write_text(
        json.dumps({"schema": "mc-hard-promotion-v1", "models": promotion}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    diagnostic = [by_id[key] for key in sorted(diagnostic_progress)]
    (args.results / "diagnostic_progress_candidates.json").write_text(
        json.dumps({"schema": "mc-hard-diagnostic-progress-v1", "models": diagnostic},
                   indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"strategies={len(tables)} solved_promotions={len(promotion)} "
        f"diagnostic_progress={len(diagnostic)} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
