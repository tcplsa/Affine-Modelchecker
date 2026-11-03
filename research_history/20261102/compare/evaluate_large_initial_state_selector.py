#!/usr/bin/env python3
"""Evaluate a frozen large-campaign selector on sharded held-out results."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--features", type=Path, nargs="+", required=True)
    parser.add_argument("--results", type=Path, nargs="+", required=True)
    parser.add_argument(
        "--tree", choices=["deployed", "candidate"], default="deployed",
    )
    parser.add_argument("--timeout-multiplier", type=float, default=1.5)
    parser.add_argument("--min-action-span", type=float, default=1.0)
    parser.add_argument(
        "--metric", choices=["algorithm", "pdr", "wall"], default="algorithm",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path)
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def load_features(paths: list[Path]) -> dict[tuple[str, str], dict[str, str]]:
    result = {}
    for path in paths:
        match = re.search(r"(20\d{2})", path.stem)
        inferred_year = match.group(1) if match else ""
        for row in read_tsv(path):
            result[(row.get("year") or inferred_year, row["name"])] = row
    return result


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


def predict(node: dict, features: dict[str, str]) -> str:
    feature = node.get("feature")
    if not feature:
        return str(node["action"])
    value = number(features, str(feature))
    child = node["left"] if value <= float(node["threshold"]) else node["right"]
    return predict(child, features)


def aggregate(values: list[tuple[float, bool, str]]) -> tuple[float, bool, str]:
    cost = max(value for value, _solved, _status in values)
    solved = all(flag for _value, flag, _status in values)
    statuses = {status for _value, _flag, status in values if status in SOLVED}
    status = statuses.pop() if solved and len(statuses) == 1 else "TIMEOUT"
    return cost, solved, status


def summarize(label: str, rows: list[dict], actions: list[str]) -> dict:
    baseline_cost = sum(row["costs"]["aig"] for row in rows)
    selector_cost = sum(row["costs"][row["choice"]] for row in rows)
    oracle_cost = sum(min(row["costs"][action] for action in actions) for row in rows)
    baseline_solved = sum(row["solved"]["aig"] for row in rows)
    selector_solved = sum(row["solved"][row["choice"]] for row in rows)
    conflicts = sum(
        row["solved"]["aig"]
        and row["solved"][row["choice"]]
        and row["statuses"]["aig"] != row["statuses"][row["choice"]]
        for row in rows
    )
    return {
        "scope": label,
        "cases": len(rows),
        "baseline_cost": f"{baseline_cost:.6f}",
        "selector_cost": f"{selector_cost:.6f}",
        "gain_percent": (
            f"{100.0 * (baseline_cost - selector_cost) / baseline_cost:.6f}"
            if baseline_cost else "0.000000"
        ),
        "oracle_gain_percent": (
            f"{100.0 * (baseline_cost - oracle_cost) / baseline_cost:.6f}"
            if baseline_cost else "0.000000"
        ),
        "baseline_solved": baseline_solved,
        "selector_solved": selector_solved,
        "solved_change": selector_solved - baseline_solved,
        "outcome_conflicts": conflicts,
        "choices": json.dumps(
            Counter(row["choice"] for row in rows), sort_keys=True,
        ),
    }


def main() -> int:
    args = parse_args()
    model = json.loads(args.model.read_text(encoding="utf-8"))
    actions = list(model["actions"])
    tree_key = "candidate_tree" if args.tree == "candidate" else "tree"
    tree = model[tree_key]
    features = load_features(args.features)
    shards: dict[
        tuple[str, str, int, str],
        dict[str, list[tuple[float, bool, str]]],
    ] = defaultdict(lambda: defaultdict(list))

    for path in args.results:
        design_path = path.with_name(path.stem + "_design.json")
        design = json.loads(design_path.read_text(encoding="utf-8"))
        year = str(design.get("year", ""))
        tier = str(design.get("group", ""))
        design_seed = int(design.get("design_seed", 0))
        solver_seed = int(design.get("solver_seed", 0))
        configs = design.get("configs", [])
        for row in read_tsv(path):
            key = (year, tier, solver_seed, row["name"])
            penalty = (
                number(row, "timeout_seconds", design.get("timeout", 30.0))
                * args.timeout_multiplier
            )
            for config in configs:
                source = str(config["id"])
                action = (
                    "aig" if source == "state_000"
                    else f"d{design_seed}_{source}"
                )
                if action not in actions:
                    continue
                shards[key][action].append(
                    measured(row, source, args.metric, penalty)
                )

    evaluated = []
    skipped_incomplete = 0
    for (year, tier, solver_seed, name), values in sorted(shards.items()):
        if any(action not in values for action in actions):
            skipped_incomplete += 1
            continue
        feature = features.get((year, name))
        if feature is None:
            raise SystemExit(f"missing features for {year}:{name}")
        combined = {
            action: aggregate(values[action]) for action in actions
        }
        costs = {action: value[0] for action, value in combined.items()}
        if max(costs.values()) - min(costs.values()) <= args.min_action_span:
            continue
        choice = predict(tree, feature)
        evaluated.append({
            "year": year,
            "tier": tier,
            "solver_seed": solver_seed,
            "name": name,
            "choice": choice,
            "costs": costs,
            "solved": {
                action: value[1] for action, value in combined.items()
            },
            "statuses": {
                action: value[2] for action, value in combined.items()
            },
        })

    if not evaluated:
        raise SystemExit("no complete held-out rows remain after filtering")

    scopes = [("combined", evaluated)]
    for seed in sorted({row["solver_seed"] for row in evaluated}):
        scopes.append((
            f"solver_seed_{seed}",
            [row for row in evaluated if row["solver_seed"] == seed],
        ))
    for tier in sorted({row["tier"] for row in evaluated}):
        scopes.append((
            tier,
            [row for row in evaluated if row["tier"] == tier],
        ))
    summaries = [summarize(label, rows, actions) for label, rows in scopes]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(summaries[0]), delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(summaries)

    report_path = args.report_output or args.output.with_suffix(".md")
    report = [
        "# Held-Out Large Initial-State Selector",
        "",
        f"- Model: `{args.model}`",
        f"- Tree: {args.tree}",
        f"- Actions: {len(actions)}",
        f"- Minimum action span: {args.min_action_span:g}s",
        f"- Evaluated rows: {len(evaluated)}",
        f"- Incomplete rows skipped: {skipped_incomplete}",
        "",
        "| Scope | Cases | Gain | Oracle | Solved change | Conflicts |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in summaries:
        report.append(
            f"| {row['scope']} | {row['cases']} | "
            f"{row['gain_percent']}% | {row['oracle_gain_percent']}% | "
            f"{row['solved_change']} | {row['outcome_conflicts']} |"
        )
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"rows={len(evaluated)} skipped_incomplete={skipped_incomplete}")
    for row in summaries:
        print(
            f"{row['scope']} cases={row['cases']} "
            f"gain={row['gain_percent']}% "
            f"solved_change={row['solved_change']}"
        )
    print(f"output={args.output} report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
