#!/usr/bin/env python3
"""Analyze controlled mechanism campaigns without fitting a selector."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}
MECHANISM_FIELDS = (
    "encoded_gate_clauses",
    "recognized_xors",
    "pdr_depth",
    "queries",
    "cti",
    "mic",
    "push",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout-multiplier", type=float, default=1.5)
    parser.add_argument("--min-gap", type=float, default=1.0)
    parser.add_argument("--min-sample-span", type=float, default=1.0)
    parser.add_argument(
        "--metric", choices=["algorithm", "pdr", "wall"], default="algorithm",
    )
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def number(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, ""))
    except (TypeError, ValueError):
        return default


def measured(
    row: dict[str, str],
    source: str,
    metric: str,
    penalty: float,
) -> tuple[float, bool, str]:
    status = row.get(f"{source}_status", "")
    solved = status in SOLVED
    wall = number(row, f"{source}_wall_seconds", penalty)
    pdr = number(row, f"{source}_pdr_runtime", wall)
    transform = (
        number(row, f"{source}_input_order_runtime")
        + number(row, f"{source}_conversion_runtime")
    )
    value = wall if metric == "wall" else pdr if metric == "pdr" else pdr + transform
    return (value if solved else penalty), solved, status


def mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def ratio_mean(observations: list[dict], field: str) -> float | None:
    ratios = []
    for observation in observations:
        candidate = observation["stats"].get(field)
        baseline = observation["baseline_stats"].get(field)
        if candidate is not None and baseline not in (None, 0.0):
            ratios.append(candidate / baseline)
    return mean(ratios) if ratios else None


def summarize_strategy(strategy: str, observations: list[dict], min_gap: float) -> dict:
    baseline_cost = sum(item["baseline_cost"] for item in observations)
    candidate_cost = sum(item["cost"] for item in observations)
    solver_gains = []
    for seed in sorted({item["solver_seed"] for item in observations}):
        subset = [item for item in observations if item["solver_seed"] == seed]
        base = sum(item["baseline_cost"] for item in subset)
        cost = sum(item["cost"] for item in subset)
        solver_gains.append(100.0 * (base - cost) / base if base else 0.0)
    transform_gains = []
    transform_seeds = sorted({
        item["transform_seed"] for item in observations
        if item["transform_seed"] > 0
    })
    for seed in transform_seeds:
        subset = [item for item in observations if item["transform_seed"] == seed]
        base = sum(item["baseline_cost"] for item in subset)
        cost = sum(item["cost"] for item in subset)
        transform_gains.append(100.0 * (base - cost) / base if base else 0.0)
    row = {
        "strategy": strategy,
        "representation": observations[0]["representation"],
        "observations": len(observations),
        "circuits": len({
            (item["year"], item["name"]) for item in observations
        }),
        "solver_seeds": len({item["solver_seed"] for item in observations}),
        "transform_seeds": len(transform_seeds),
        "solved": sum(item["solved"] for item in observations),
        "baseline_solved": sum(item["baseline_solved"] for item in observations),
        "candidate_only_solves": sum(
            item["solved"] and not item["baseline_solved"]
            for item in observations
        ),
        "baseline_only_solves": sum(
            item["baseline_solved"] and not item["solved"]
            for item in observations
        ),
        "wins": sum(
            item["baseline_cost"] - item["cost"] > min_gap
            for item in observations
        ),
        "losses": sum(
            item["cost"] - item["baseline_cost"] > min_gap
            for item in observations
        ),
        "neutral": sum(
            abs(item["cost"] - item["baseline_cost"]) <= min_gap
            for item in observations
        ),
        "baseline_cost": f"{baseline_cost:.6f}",
        "candidate_cost": f"{candidate_cost:.6f}",
        "gain_percent": f"{100.0 * (baseline_cost - candidate_cost) / baseline_cost:.6f}"
        if baseline_cost else "0.000000",
        "worst_solver_gain_percent": f"{min(solver_gains):.6f}"
        if solver_gains else "",
        "worst_transform_gain_percent": f"{min(transform_gains):.6f}"
        if transform_gains else "",
        "outcome_conflicts": sum(
            item["solved"] and item["baseline_solved"]
            and item["status"] != item["baseline_status"]
            for item in observations
        ),
    }
    for field in MECHANISM_FIELDS:
        value = ratio_mean(observations, field)
        row[field + "_ratio"] = "" if value is None else f"{value:.6f}"
    return row


def variance_decomposition(strategy: str, observations: list[dict]) -> dict | None:
    transform_seeds = sorted({
        item["transform_seed"] for item in observations
        if item["transform_seed"] > 0
    })
    solver_seeds = sorted({item["solver_seed"] for item in observations})
    if len(transform_seeds) < 2 or len(solver_seeds) < 2:
        return None
    grouped: dict[tuple[str, str], dict[tuple[int, int], float]] = defaultdict(dict)
    for item in observations:
        if item["transform_seed"] <= 0:
            continue
        grouped[(item["year"], item["name"])][
            (item["transform_seed"], item["solver_seed"])
        ] = item["cost"] - item["baseline_cost"]
    shares = []
    complete = 0
    for values in grouped.values():
        if any(
            (transform, solver) not in values
            for transform in transform_seeds
            for solver in solver_seeds
        ):
            continue
        complete += 1
        all_values = list(values.values())
        grand = mean(all_values)
        transform_means = {
            transform: mean([
                values[(transform, solver)] for solver in solver_seeds
            ])
            for transform in transform_seeds
        }
        solver_means = {
            solver: mean([
                values[(transform, solver)] for transform in transform_seeds
            ])
            for solver in solver_seeds
        }
        ss_transform = len(solver_seeds) * sum(
            (value - grand) ** 2 for value in transform_means.values()
        )
        ss_solver = len(transform_seeds) * sum(
            (value - grand) ** 2 for value in solver_means.values()
        )
        ss_residual = sum(
            (
                values[(transform, solver)]
                - transform_means[transform]
                - solver_means[solver]
                + grand
            ) ** 2
            for transform in transform_seeds
            for solver in solver_seeds
        )
        total = ss_transform + ss_solver + ss_residual
        if total > 0:
            shares.append((
                ss_transform / total,
                ss_solver / total,
                ss_residual / total,
            ))
    if not shares:
        return None
    return {
        "strategy": strategy,
        "complete_circuits": complete,
        "transform_seeds": len(transform_seeds),
        "solver_seeds": len(solver_seeds),
        "mean_transform_share": f"{mean([row[0] for row in shares]):.6f}",
        "median_transform_share": f"{statistics.median(row[0] for row in shares):.6f}",
        "mean_solver_share": f"{mean([row[1] for row in shares]):.6f}",
        "median_solver_share": f"{statistics.median(row[1] for row in shares):.6f}",
        "mean_interaction_share": f"{mean([row[2] for row in shares]):.6f}",
        "median_interaction_share": f"{statistics.median(row[2] for row in shares):.6f}",
    }


def mechanism_contrasts(
    by_strategy: dict[str, list[dict]],
    min_gap: float,
) -> list[dict]:
    rows = []
    for strategy, observations in sorted(by_strategy.items()):
        grouped: dict[str, list[dict]] = defaultdict(list)
        for observation in observations:
            delta = observation["baseline_cost"] - observation["cost"]
            outcome = (
                "faster" if delta > min_gap
                else "slower" if delta < -min_gap
                else "neutral"
            )
            grouped[outcome].append(observation)
        for outcome in ("faster", "slower", "neutral"):
            items = grouped.get(outcome, [])
            if not items:
                continue
            mean_delta = mean([
                item["baseline_cost"] - item["cost"] for item in items
            ])
            row = {
                "strategy": strategy,
                "representation": items[0]["representation"],
                "outcome": outcome,
                "observations": len(items),
                "mean_delta_seconds": f"{mean_delta:.6f}",
                "candidate_only_solves": sum(
                    item["solved"] and not item["baseline_solved"]
                    for item in items
                ),
                "baseline_only_solves": sum(
                    item["baseline_solved"] and not item["solved"]
                    for item in items
                ),
            }
            for field in MECHANISM_FIELDS:
                value = ratio_mean(items, field)
                row[field + "_ratio"] = (
                    "" if value is None else f"{value:.6f}"
                )
            rows.append(row)
    return rows


def write_tsv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    observations = []
    axis = ""
    for result_path in args.results:
        design_path = result_path.with_name(result_path.stem + "_design.json")
        if not result_path.exists() or not design_path.exists():
            continue
        design = json.loads(design_path.read_text(encoding="utf-8"))
        axis = axis or str(design["axis"])
        if str(design["axis"]) != axis:
            raise SystemExit("cannot mix XOR and input campaigns")
        year = str(design["year"])
        tier = str(design["group"])
        solver_seed = int(design["solver_seed"])
        configs = {config["id"]: config for config in design["configs"]}
        for row in read_tsv(result_path):
            penalty = (
                number(row, "timeout_seconds", float(design["timeout"]))
                * args.timeout_multiplier
            )
            for config_id, config in configs.items():
                representation = str(
                    config.get(
                        "representation_family",
                        "aig" if config_id == "aig" else "xag",
                    )
                )
                baseline_id = (
                    "aig" if axis == "xor"
                    else f"{representation}_original"
                )
                cost, solved, status = measured(
                    row, config_id, args.metric, penalty,
                )
                base_cost, base_solved, base_status = measured(
                    row, baseline_id, args.metric, penalty,
                )
                stats = {}
                baseline_stats = {}
                for field in MECHANISM_FIELDS:
                    raw = row.get(f"{config_id}_{field}", "")
                    base_raw = row.get(f"{baseline_id}_{field}", "")
                    stats[field] = number(
                        row, f"{config_id}_{field}",
                    ) if raw != "" else None
                    baseline_stats[field] = number(
                        row, f"{baseline_id}_{field}",
                    ) if base_raw != "" else None
                observations.append({
                    "axis": axis,
                    "year": year,
                    "tier": tier,
                    "name": row["name"],
                    "solver_seed": solver_seed,
                    "config_id": config_id,
                    "strategy": str(config["mechanism_strategy"]),
                    "representation": representation,
                    "transform_seed": int(config.get("transform_seed", 0)),
                    "status": status,
                    "solved": solved,
                    "cost": cost,
                    "baseline_id": baseline_id,
                    "baseline_status": base_status,
                    "baseline_solved": base_solved,
                    "baseline_cost": base_cost,
                    "stats": stats,
                    "baseline_stats": baseline_stats,
                })
    if not observations:
        raise SystemExit("no mechanism observations found")

    observations_before_filter = len(observations)
    sample_groups: dict[tuple, list[dict]] = defaultdict(list)
    for observation in observations:
        key = (
            observation["year"],
            observation["name"],
            observation["solver_seed"],
        )
        if axis == "input":
            key += (observation["representation"],)
        sample_groups[key].append(observation)
    informative_keys = {
        key for key, items in sample_groups.items()
        if max(item["cost"] for item in items)
        - min(item["cost"] for item in items) > args.min_sample_span
    }
    observations = [
        observation for key, items in sample_groups.items()
        if key in informative_keys
        for observation in items
    ]
    if not observations:
        raise SystemExit("no observations remain after sample-span filtering")

    by_strategy: dict[str, list[dict]] = defaultdict(list)
    for observation in observations:
        by_strategy[observation["strategy"]].append(observation)
    summaries = [
        summarize_strategy(strategy, rows, args.min_gap)
        for strategy, rows in sorted(by_strategy.items())
    ]
    summaries.sort(
        key=lambda row: float(row["gain_percent"]), reverse=True,
    )
    variances = [
        row for strategy, items in sorted(by_strategy.items())
        if (row := variance_decomposition(strategy, items)) is not None
    ]
    contrasts = mechanism_contrasts(by_strategy, args.min_gap)
    details = []
    for item in observations:
        detail = {
            key: value for key, value in item.items()
            if key not in {"stats", "baseline_stats"}
        }
        detail["delta_seconds"] = f"{item['baseline_cost'] - item['cost']:.6f}"
        for field in MECHANISM_FIELDS:
            detail[field] = (
                "" if item["stats"][field] is None
                else f"{item['stats'][field]:.6f}"
            )
            detail["baseline_" + field] = (
                "" if item["baseline_stats"][field] is None
                else f"{item['baseline_stats'][field]:.6f}"
            )
        details.append(detail)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_tsv(args.output_dir / "strategy_summary.tsv", summaries)
    write_tsv(args.output_dir / "variance_summary.tsv", variances)
    write_tsv(args.output_dir / "mechanism_contrast.tsv", contrasts)
    write_tsv(args.output_dir / "case_details.tsv", details)
    report = [
        f"# {axis.upper()} Mechanism Campaign",
        "",
        f"- Observations before span filter: {observations_before_filter}",
        f"- Observations after >{args.min_sample_span:g}s span filter: "
        f"{len(observations)}",
        f"- Informative sample groups: {len(informative_keys)}",
        f"- Strategies: {len(summaries)}",
        f"- Metric: {args.metric}",
        f"- Meaningful gap: {args.min_gap:g}s",
        "",
        "| Strategy | Gain | Worst solver | Worst transform | Solved delta | W/L/N |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in summaries:
        worst_solver = row["worst_solver_gain_percent"]
        worst_transform = row["worst_transform_gain_percent"]
        report.append(
            f"| {row['strategy']} | {row['gain_percent']}% | "
            f"{worst_solver + '%' if worst_solver else 'n/a'} | "
            f"{worst_transform + '%' if worst_transform else 'n/a'} | "
            f"{int(row['solved']) - int(row['baseline_solved']):+d} | "
            f"{row['wins']}/{row['losses']}/{row['neutral']} |"
        )
    (args.output_dir / "report.md").write_text(
        "\n".join(report) + "\n", encoding="utf-8",
    )
    print(
        f"axis={axis} observations={len(observations)} "
        f"strategies={len(summaries)} output={args.output_dir}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
