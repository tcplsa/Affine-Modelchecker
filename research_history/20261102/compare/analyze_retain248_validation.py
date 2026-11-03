#!/usr/bin/env python3
"""Analyze frozen retain248 held-out validation without policy retuning."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


CONFIGS = ("aig", "compact_aig", "full_xag", "retain248")
VALID = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--neutral-seconds", type=float, default=2.0)
    parser.add_argument("--timeout-penalty", type=float, default=1.5)
    return parser.parse_args()


def load_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for path in paths:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = (row["model_id"], row["run"], row["config"])
                if key in seen:
                    raise SystemExit(f"duplicate observation {key} in {path}")
                seen.add(key)
                rows.append(row)
    return rows


def median(values: list[float]) -> float:
    return statistics.median(values) if values else math.nan


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = load_rows(args.inputs)
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    metadata: dict[str, dict[str, str]] = {}
    outcomes: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        grouped[(row["model_id"], row["config"])].append(row)
        metadata[row["model_id"]] = row
        if row["status"] in VALID:
            outcomes[row["model_id"]].add(row["status"])

    conflicts = [model_id for model_id, values in outcomes.items() if len(values) > 1]
    if conflicts:
        (args.output_dir / "conflicts.txt").write_text("\n".join(sorted(conflicts)) + "\n")

    per_model: list[dict[str, Any]] = []
    incomplete: list[str] = []
    model_ids = sorted(metadata)
    for model_id in model_ids:
        info = metadata[model_id]
        record: dict[str, Any] = {
            "model_id": model_id,
            "name": info["name"],
            "year": info["year"],
            "group": info["group"],
            "family": info["family"],
            "total_xors": info["total_xors"],
            "retained_xors": info["retained_xors"],
            "removed_xors": info["removed_xors"],
        }
        all_unsolved = True
        for config in CONFIGS:
            observations = grouped.get((model_id, config), [])
            if len(observations) != 4:
                incomplete.append(f"{model_id}\t{config}\t{len(observations)}")
            costs: list[float] = []
            walls: list[float] = []
            solved = 0
            for observation in observations:
                wall = float(observation["wall_seconds"])
                timeout = float(observation["timeout_seconds"])
                if observation["status"] in VALID:
                    costs.append(wall)
                    walls.append(wall)
                    solved += 1
                    all_unsolved = False
                else:
                    costs.append(args.timeout_penalty * timeout)
            record[f"{config}_solved_runs"] = solved
            record[f"{config}_median_cost"] = f"{median(costs):.6f}"
            record[f"{config}_median_solved_wall"] = (
                f"{median(walls):.6f}" if walls else ""
            )
        record["all_configs_unsolved"] = int(all_unsolved)
        per_model.append(record)

    fields = list(per_model[0]) if per_model else []
    write_tsv(args.output_dir / "per_model.tsv", per_model, fields)
    (args.output_dir / "incomplete.tsv").write_text(
        "model_id\tconfig\tobservations\n" + "\n".join(incomplete) + ("\n" if incomplete else ""),
        encoding="utf-8",
    )

    primary = [row for row in per_model if not row["all_configs_unsolved"]]
    summary_rows: list[dict[str, Any]] = []
    retain_total = sum(float(row["retain248_median_cost"]) for row in primary)
    for config in CONFIGS:
        total = sum(float(row[f"{config}_median_cost"]) for row in primary)
        solved_runs = sum(int(row[f"{config}_solved_runs"]) for row in primary)
        solved_models = sum(int(row[f"{config}_solved_runs"]) > 0 for row in primary)
        fully_solved = sum(int(row[f"{config}_solved_runs"]) == 4 for row in primary)
        summary_rows.append({
            "config": config,
            "models": len(primary),
            "median_cost_sum": f"{total:.6f}",
            "improvement_of_retain248_pct": f"{(total / retain_total - 1) * 100:.6f}" if retain_total else "",
            "solved_runs": solved_runs,
            "solved_models_any_run": solved_models,
            "models_solved_all_runs": fully_solved,
        })
    write_tsv(args.output_dir / "summary.tsv", summary_rows, list(summary_rows[0]))

    pair_rows: list[dict[str, Any]] = []
    for baseline in ("aig", "compact_aig", "full_xag"):
        wins = losses = neutral = 0
        ratios: list[float] = []
        for row in primary:
            base = float(row[f"{baseline}_median_cost"])
            candidate = float(row["retain248_median_cost"])
            delta = base - candidate
            if delta > args.neutral_seconds:
                wins += 1
            elif delta < -args.neutral_seconds:
                losses += 1
            else:
                neutral += 1
            if base > 0 and candidate > 0:
                ratios.append(math.log(base / candidate))
        base_total = sum(float(row[f"{baseline}_median_cost"]) for row in primary)
        pair_rows.append({
            "baseline": baseline,
            "models": len(primary),
            "retain248_wins": wins,
            "retain248_losses": losses,
            "neutral": neutral,
            "aggregate_improvement_pct": f"{(base_total / retain_total - 1) * 100:.6f}",
            "geomean_speedup": f"{math.exp(sum(ratios) / len(ratios)):.6f}" if ratios else "",
        })
    write_tsv(args.output_dir / "pairwise.tsv", pair_rows, list(pair_rows[0]))

    strata_rows: list[dict[str, Any]] = []
    for key_name in ("year", "group"):
        values = sorted({row[key_name] for row in primary})
        for value in values:
            subset = [row for row in primary if row[key_name] == value]
            candidate = sum(float(row["retain248_median_cost"]) for row in subset)
            for baseline in ("aig", "compact_aig", "full_xag"):
                base = sum(float(row[f"{baseline}_median_cost"]) for row in subset)
                strata_rows.append({
                    "stratum": key_name,
                    "value": value,
                    "baseline": baseline,
                    "models": len(subset),
                    "aggregate_improvement_pct": f"{(base / candidate - 1) * 100:.6f}" if candidate else "",
                })
    write_tsv(args.output_dir / "strata.tsv", strata_rows, list(strata_rows[0]))

    pair_text = "\n".join(
        f"| {row['baseline']} | {row['retain248_wins']} | {row['retain248_losses']} | "
        f"{row['neutral']} | {float(row['aggregate_improvement_pct']):+.2f}% | "
        f"{float(row['geomean_speedup']):.3f}x |"
        for row in pair_rows
    )
    config_text = "\n".join(
        f"| {row['config']} | {float(row['median_cost_sum']):.2f} | {row['solved_runs']} | "
        f"{row['solved_models_any_run']} | {row['models_solved_all_runs']} |"
        for row in summary_rows
    )
    report = f"""# retain248 Cross-Year Held-Out Validation

The policy was frozen before these runs. Each observation is one real {4}-lane portfolio;
each model/configuration score is the median of four independent portfolio repeats.
Unsolved repeats cost {args.timeout_penalty:.1f} times their timeout. Models unsolved by every
configuration are excluded from aggregate time, but are counted below.

## Coverage

- Recorded task rows: {len(rows)}
- Models in result files: {len(per_model)}
- Primary models (at least one configuration solved): {len(primary)}
- All-configuration unsolved models: {len(per_model) - len(primary)}
- Incomplete model/config cells: {len(incomplete)}
- Outcome conflicts: {len(conflicts)}

## Configuration totals

| Configuration | Sum of per-model median penalized cost (s) | Solved runs | Models solved at least once | Models solved all 4 runs |
|---|---:|---:|---:|---:|
{config_text}

## retain248 against frozen baselines

Differences within {args.neutral_seconds:.1f} seconds are neutral.

| Baseline | Wins | Losses | Neutral | Aggregate improvement | Geometric speedup |
|---|---:|---:|---:|---:|---:|
{pair_text}

See `strata.tsv` for year and difficulty-group breakdowns and `per_model.tsv` for audit data.
"""
    (args.output_dir / "report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
