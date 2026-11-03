#!/usr/bin/env python3
"""Produce detailed, multi-axis summaries for the large state-search campaign."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--baseline", default="state_000")
    parser.add_argument("--timeout-multiplier", type=float, default=1.5)
    parser.add_argument("--min-gap", type=float, default=2.0)
    parser.add_argument("--ratio", type=float, default=1.05)
    parser.add_argument(
        "--metric", choices=["algorithm", "pdr", "wall"], default="algorithm",
    )
    return parser.parse_args()


def number(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, ""))
    except (TypeError, ValueError):
        return default


def representation(config: dict) -> str:
    for field, label in (
        ("forward_aig", "aig"),
        ("forward_xag", "native-xag"),
        ("forward_lowered_xag", "lowered-xag"),
        ("forward_auto", "auto"),
    ):
        if config.get(field, 0):
            return label
    return str(config.get("mode", "unknown"))


def action_cost(
    row: dict[str, str],
    action: str,
    metric: str,
    penalty: float,
) -> tuple[str, float]:
    status = row.get(f"{action}_status", "")
    wall = number(row, f"{action}_wall_seconds", penalty)
    pdr = number(row, f"{action}_pdr_runtime", wall)
    transform = (
        number(row, f"{action}_input_order_runtime")
        + number(row, f"{action}_conversion_runtime")
    )
    measured = wall if metric == "wall" else pdr if metric == "pdr" else pdr + transform
    return status, measured if status in SOLVED else penalty


def compare(
    base_status: str,
    base_cost: float,
    status: str,
    cost: float,
    min_gap: float,
    ratio: float,
) -> str:
    base_solved = base_status in SOLVED
    solved = status in SOLVED
    if solved and not base_solved:
        return "win"
    if base_solved and not solved:
        return "loss"
    if not solved:
        return "unresolved"
    gap = base_cost - cost
    if gap > min_gap and base_cost / max(cost, 1e-9) >= ratio:
        return "win"
    if -gap > min_gap and cost / max(base_cost, 1e-9) >= ratio:
        return "loss"
    return "neutral"


def new_stats() -> dict[str, object]:
    return {
        "observations": 0,
        "models_solved": 0,
        "baseline_solved": 0,
        "wins": 0,
        "losses": 0,
        "neutral": 0,
        "unresolved": 0,
        "candidate_only_solves": 0,
        "baseline_only_solves": 0,
        "cost": 0.0,
        "baseline_cost": 0.0,
        "best_count": 0,
        "both_solved": 0,
        "log_speedup_sum": 0.0,
        "depth_sum": 0.0,
        "queries_sum": 0.0,
        "cti_sum": 0.0,
        "mic_sum": 0.0,
        "encoded_clauses_sum": 0.0,
        "baseline_encoded_clauses_sum": 0.0,
        "encoded_pairs": 0,
    }


def add_observation(
    stats: dict[str, object],
    row: dict[str, str],
    action: str,
    status: str,
    cost: float,
    base_status: str,
    base_cost: float,
    verdict: str,
    is_best: bool,
    baseline: str,
) -> None:
    stats["observations"] += 1
    solved = status in SOLVED
    base_solved = base_status in SOLVED
    stats["models_solved"] += int(solved)
    stats["baseline_solved"] += int(base_solved)
    verdict_field = {
        "win": "wins",
        "loss": "losses",
        "neutral": "neutral",
        "unresolved": "unresolved",
    }[verdict]
    stats[verdict_field] += 1
    stats["candidate_only_solves"] += int(solved and not base_solved)
    stats["baseline_only_solves"] += int(base_solved and not solved)
    stats["cost"] += cost
    stats["baseline_cost"] += base_cost
    stats["best_count"] += int(is_best)
    if solved:
        stats["depth_sum"] += number(row, f"{action}_pdr_depth")
        stats["queries_sum"] += number(row, f"{action}_queries")
        stats["cti_sum"] += number(row, f"{action}_cti")
        stats["mic_sum"] += number(row, f"{action}_mic")
    if solved and base_solved:
        stats["both_solved"] += 1
        stats["log_speedup_sum"] += math.log(
            max(base_cost, 1e-9) / max(cost, 1e-9)
        )
    clauses = number(row, f"{action}_encoded_gate_clauses", -1.0)
    base_clauses = number(row, f"{baseline}_encoded_gate_clauses", -1.0)
    if clauses >= 0.0 and base_clauses > 0.0:
        stats["encoded_clauses_sum"] += clauses
        stats["baseline_encoded_clauses_sum"] += base_clauses
        stats["encoded_pairs"] += 1


def finished_row(key: tuple, fields: list[str], stats: dict[str, object]) -> dict:
    observations = int(stats["observations"])
    solved = int(stats["models_solved"])
    both = int(stats["both_solved"])
    cost = float(stats["cost"])
    baseline_cost = float(stats["baseline_cost"])
    encoded_pairs = int(stats["encoded_pairs"])
    result = dict(zip(fields, key))
    result.update({
        "observations": observations,
        "solved": solved,
        "solve_rate": solved / observations if observations else 0.0,
        "baseline_solved": stats["baseline_solved"],
        "wins": stats["wins"],
        "losses": stats["losses"],
        "neutral": stats["neutral"],
        "unresolved": stats["unresolved"],
        "candidate_only_solves": stats["candidate_only_solves"],
        "baseline_only_solves": stats["baseline_only_solves"],
        "best_count": stats["best_count"],
        "par_cost": f"{cost:.6f}",
        "baseline_par_cost": f"{baseline_cost:.6f}",
        "gain_percent": (
            f"{100.0 * (baseline_cost - cost) / baseline_cost:.6f}"
            if baseline_cost else "0.000000"
        ),
        "both_solved": both,
        "geomean_speedup": (
            f"{math.exp(float(stats['log_speedup_sum']) / both):.6f}"
            if both else ""
        ),
        "mean_depth_solved": (
            f"{float(stats['depth_sum']) / solved:.6f}" if solved else ""
        ),
        "mean_queries_solved": (
            f"{float(stats['queries_sum']) / solved:.6f}" if solved else ""
        ),
        "mean_cti_solved": (
            f"{float(stats['cti_sum']) / solved:.6f}" if solved else ""
        ),
        "mean_mic_solved": (
            f"{float(stats['mic_sum']) / solved:.6f}" if solved else ""
        ),
        "encoded_clause_ratio": (
            f"{float(stats['encoded_clauses_sum']) / float(stats['baseline_encoded_clauses_sum']):.6f}"
            if encoded_pairs and float(stats["baseline_encoded_clauses_sum"]) else ""
        ),
        "encoded_pairs": encoded_pairs,
    })
    return result


def write_tsv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    exact: dict[tuple, dict] = defaultdict(new_stats)
    family: dict[tuple, dict] = defaultdict(new_stats)
    coordinate: dict[tuple, dict] = defaultdict(new_stats)
    context: dict[tuple, dict] = defaultdict(new_stats)
    stability_values: dict[tuple, list[tuple[str, float]]] = defaultdict(list)
    oracle_rows: list[dict] = []
    files_used = 0

    for result_path in args.results:
        design_path = result_path.with_name(result_path.stem + "_design.json")
        if not result_path.exists() or not design_path.exists():
            print(f"skip missing result/design pair: {result_path}")
            continue
        design = json.loads(design_path.read_text(encoding="utf-8"))
        configs = design.get("configs", [])
        config_by_id = {config["id"]: config for config in configs}
        actions = list(config_by_id)
        if args.baseline not in config_by_id:
            print(f"skip design without baseline {args.baseline}: {design_path}")
            continue
        year = str(design.get("year", ""))
        tier = str(design.get("group", ""))
        design_seed = int(design.get("design_seed", 0))
        solver_seed = int(design.get("solver_seed", 0))
        files_used += 1
        with result_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                penalty = (
                    number(row, "timeout_seconds", design.get("timeout", 30.0))
                    * args.timeout_multiplier
                )
                scores = {
                    action: action_cost(
                        row, action, args.metric, penalty,
                    )
                    for action in actions
                }
                base_status, base_cost = scores[args.baseline]
                best = min(actions, key=lambda action: scores[action][1])
                best_status, best_cost = scores[best]
                oracle_rows.append({
                    "year": year,
                    "tier": tier,
                    "design_seed": design_seed,
                    "solver_seed": solver_seed,
                    "name": row.get("name", ""),
                    "baseline_status": base_status,
                    "baseline_cost": f"{base_cost:.6f}",
                    "best_state": best,
                    "best_status": best_status,
                    "best_cost": f"{best_cost:.6f}",
                    "oracle_speedup": f"{base_cost / max(best_cost, 1e-9):.6f}",
                })
                for action, config in config_by_id.items():
                    status, cost = scores[action]
                    verdict = compare(
                        base_status, base_cost, status, cost,
                        args.min_gap, args.ratio,
                    )
                    rep = representation(config)
                    family_name = str(config.get("design_family", rep))
                    policy = str(config.get("xag_policy", "all"))
                    fraction = f"{float(config.get('xag_fraction', 1.0)):g}"
                    order = str(config.get("input_order", "original"))
                    perturb = str(config.get("perturb_modes", "")) or "none"
                    exact_key = (
                        design_seed, action, config.get("label", action),
                        family_name, rep, policy, fraction, order, perturb,
                    )
                    coordinate_key = (
                        family_name, rep, policy, fraction, order, perturb,
                    )
                    for target in (
                        exact[exact_key],
                        family[(family_name,)],
                        coordinate[coordinate_key],
                        context[(year, tier, family_name)],
                    ):
                        add_observation(
                            target, row, action, status, cost,
                            base_status, base_cost, verdict, action == best,
                            args.baseline,
                        )
                    stability_values[(
                        year, tier, design_seed, action, row.get("name", "")
                    )].append((status, cost))

    if not files_used:
        raise SystemExit("no complete result/design pairs")

    exact_rows = [
        finished_row(
            key,
            [
                "design_seed", "state", "label", "family",
                "representation", "xag_policy", "xag_fraction",
                "input_order", "perturb_modes",
            ],
            stats,
        )
        for key, stats in exact.items()
    ]
    family_rows = [
        finished_row(key, ["family"], stats)
        for key, stats in family.items()
    ]
    coordinate_rows = [
        finished_row(
            key,
            [
                "family", "representation", "xag_policy", "xag_fraction",
                "input_order", "perturb_modes",
            ],
            stats,
        )
        for key, stats in coordinate.items()
    ]
    context_rows = [
        finished_row(key, ["year", "tier", "family"], stats)
        for key, stats in context.items()
    ]
    for rows in (exact_rows, family_rows, coordinate_rows, context_rows):
        rows.sort(key=lambda row: float(row["par_cost"]))

    stability_details = []
    stability_summary: dict[tuple, list[dict]] = defaultdict(list)
    for key, values in stability_values.items():
        statuses = [value[0] for value in values]
        solved_costs = [
            value[1] for value in values if value[0] in SOLVED
        ]
        mean = statistics.mean(solved_costs) if solved_costs else 0.0
        cv = (
            statistics.pstdev(solved_costs) / mean
            if len(solved_costs) > 1 and mean > 0.0 else 0.0
        )
        detail = {
            **dict(zip(
                ["year", "tier", "design_seed", "state", "name"], key,
            )),
            "solver_repeats": len(values),
            "solved_repeats": len(solved_costs),
            "same_status": int(len(set(statuses)) == 1),
            "mean_solved_cost": f"{mean:.6f}" if solved_costs else "",
            "median_solved_cost": (
                f"{statistics.median(solved_costs):.6f}"
                if solved_costs else ""
            ),
            "worst_solved_cost": (
                f"{max(solved_costs):.6f}" if solved_costs else ""
            ),
            "coefficient_of_variation": f"{cv:.6f}",
        }
        stability_details.append(detail)
        stability_summary[(key[2], key[3])].append(detail)

    stability_rows = []
    for (design_seed, state), values in stability_summary.items():
        cvs = [float(value["coefficient_of_variation"]) for value in values]
        stability_rows.append({
            "design_seed": design_seed,
            "state": state,
            "model_groups": len(values),
            "all_repeats_solved": sum(
                int(value["solver_repeats"] == value["solved_repeats"])
                for value in values
            ),
            "same_status_groups": sum(value["same_status"] for value in values),
            "mean_cv": f"{statistics.mean(cvs):.6f}" if cvs else "",
            "median_cv": f"{statistics.median(cvs):.6f}" if cvs else "",
            "max_cv": f"{max(cvs):.6f}" if cvs else "",
        })
    stability_rows.sort(key=lambda row: float(row["mean_cv"] or "inf"))

    write_tsv(args.output_dir / "exact_state_summary.tsv", exact_rows)
    write_tsv(args.output_dir / "family_summary.tsv", family_rows)
    write_tsv(args.output_dir / "coordinate_summary.tsv", coordinate_rows)
    write_tsv(args.output_dir / "year_tier_family_summary.tsv", context_rows)
    write_tsv(args.output_dir / "seed_stability_details.tsv", stability_details)
    write_tsv(args.output_dir / "seed_stability_summary.tsv", stability_rows)
    write_tsv(args.output_dir / "model_oracle.tsv", oracle_rows)

    baseline_total = sum(float(row["baseline_cost"]) for row in oracle_rows)
    oracle_total = sum(float(row["best_cost"]) for row in oracle_rows)
    report = [
        "# Large Initial-State Campaign",
        "",
        f"- Result files: {files_used}",
        f"- Model/run observations: {len(oracle_rows)}",
        f"- Metric: {args.metric}",
        f"- Timeout penalty: {args.timeout_multiplier:g}x",
        f"- Meaningful difference: {args.min_gap:g}s and {args.ratio:g}x",
        f"- Baseline PAR cost: {baseline_total:.3f}s",
        f"- Per-run oracle PAR cost: {oracle_total:.3f}s",
        (
            "- Oracle gain: "
            f"{100.0 * (baseline_total - oracle_total) / baseline_total:.2f}%"
            if baseline_total else "- Oracle gain: n/a"
        ),
        "",
        "## Best Families",
        "",
        "| Family | Gain | Solved | Wins | Losses | Clause ratio |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in family_rows[:12]:
        report.append(
            f"| {row['family']} | {row['gain_percent']}% | "
            f"{row['solved']}/{row['observations']} | {row['wins']} | "
            f"{row['losses']} | {row['encoded_clause_ratio'] or 'n/a'} |"
        )
    report.extend([
        "",
        "## Best Exact States",
        "",
        "| Design | State | Label | Gain | Solved | Wins | Losses |",
        "|---:|---|---|---:|---:|---:|---:|",
    ])
    for row in exact_rows[:20]:
        report.append(
            f"| {row['design_seed']} | {row['state']} | {row['label']} | "
            f"{row['gain_percent']}% | {row['solved']}/{row['observations']} | "
            f"{row['wins']} | {row['losses']} |"
        )
    report.extend([
        "",
        "The TSV files retain the full year/tier, coordinate, PDR-counter, "
        "CNF-size, and solver-seed stability breakdowns.",
        "",
    ])
    (args.output_dir / "REPORT.md").write_text(
        "\n".join(report), encoding="utf-8",
    )
    print(
        f"files={files_used} observations={len(oracle_rows)} "
        f"oracle_gain={100.0 * (baseline_total - oracle_total) / baseline_total:.3f}% "
        f"output={args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
