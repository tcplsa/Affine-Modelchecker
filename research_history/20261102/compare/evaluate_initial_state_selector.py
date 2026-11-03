#!/usr/bin/env python3
"""Evaluate a frozen initial-state selector without refitting it."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate a frozen selector on held-out initial-state runs."
    )
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--features", type=Path, nargs="+", required=True)
    parser.add_argument("--results", type=Path, nargs="+", required=True)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--timeout-multiplier", type=float, default=1.5)
    parser.add_argument(
        "--metric", choices=["algorithm", "pdr", "wall"], default="algorithm"
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def load_features(paths: list[Path]) -> dict[tuple[str, str], dict[str, str]]:
    features = {}
    for path in paths:
        match = re.search(r"(20\d{2})", path.stem)
        inferred_year = match.group(1) if match else ""
        for row in read_tsv(path):
            features[(row.get("year") or inferred_year, row["name"])] = row
    return features


def predict(node: dict, features: dict[str, str]) -> str:
    feature = node.get("feature")
    if not feature:
        return node["action"]
    try:
        value = float(features.get(feature, "") or 0.0)
    except ValueError:
        value = 0.0
    child = node["left"] if value <= float(node["threshold"]) else node["right"]
    return predict(child, features)


def number(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, ""))
    except (TypeError, ValueError):
        return default


def cost(
    row: dict[str, str],
    action: str,
    metric: str,
    penalty: float,
) -> float:
    if row.get(f"{action}_status") not in SOLVED:
        return penalty
    wall = number(row, f"{action}_wall_seconds", penalty)
    pdr = number(row, f"{action}_pdr_runtime", wall)
    transform = (
        number(row, f"{action}_input_order_runtime")
        + number(row, f"{action}_conversion_runtime")
    )
    if metric == "wall":
        return wall
    if metric == "pdr":
        return pdr
    return pdr + transform


def summarize(
    label: str,
    rows: list[dict],
    baseline: str,
    actions: list[str],
) -> dict:
    baseline_cost = sum(row["costs"][baseline] for row in rows)
    selector_cost = sum(row["costs"][row["choice"]] for row in rows)
    oracle_cost = sum(min(row["costs"][action] for action in actions) for row in rows)
    baseline_solved = sum(row["statuses"][baseline] in SOLVED for row in rows)
    selector_solved = sum(row["statuses"][row["choice"]] in SOLVED for row in rows)
    conflicts = sum(
        row["statuses"][baseline] in SOLVED
        and row["statuses"][row["choice"]] in SOLVED
        and row["statuses"][baseline] != row["statuses"][row["choice"]]
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
            Counter(row["choice"] for row in rows),
            ensure_ascii=False,
            sort_keys=True,
        ),
    }


def main() -> int:
    args = parse_args()
    model = json.loads(args.model.read_text(encoding="utf-8"))
    actions = model["actions"]
    baseline = actions[0]
    tree = model["tree"]
    features = load_features(args.features)
    summaries = []
    combined = []

    for path in args.results:
        evaluated = []
        for row in read_tsv(path):
            feature = features.get((row.get("year", ""), row["name"]))
            if feature is None:
                raise SystemExit(f"missing features for {row.get('year')}:{row['name']}")
            choice = predict(tree, feature)
            if f"{choice}_status" not in row:
                raise SystemExit(f"{path}: selected action {choice} is unavailable")
            try:
                row_timeout = float(row.get("timeout_seconds") or args.timeout)
            except ValueError:
                row_timeout = args.timeout
            penalty = row_timeout * args.timeout_multiplier
            evaluated.append({
                "choice": choice,
                "costs": {
                    action: cost(row, action, args.metric, penalty)
                    for action in actions
                    if f"{action}_status" in row
                },
                "statuses": {
                    action: row.get(f"{action}_status", "")
                    for action in actions
                    if f"{action}_status" in row
                },
            })
            available = set(evaluated[-1]["costs"])
            if baseline not in available or choice not in available:
                raise SystemExit(f"{path}: baseline or selected action is unavailable")

        source = path.stem
        any_solved = [
            row for row in evaluated
            if any(status in SOLVED for status in row["statuses"].values())
        ]
        baseline_solved = [
            row for row in evaluated if row["statuses"][baseline] in SOLVED
        ]
        available_actions = [
            action for action in actions
            if evaluated and action in evaluated[0]["costs"]
        ]
        summaries.extend([
            summarize(f"{source}:all", evaluated, baseline, available_actions),
            summarize(f"{source}:any_solved", any_solved, baseline, available_actions),
            summarize(
                f"{source}:baseline_solved",
                baseline_solved,
                baseline,
                available_actions,
            ),
        ])
        combined.extend(evaluated)

    available_actions = [
        action for action in actions if combined and action in combined[0]["costs"]
    ]
    combined_any_solved = [
        row for row in combined
        if any(status in SOLVED for status in row["statuses"].values())
    ]
    combined_baseline_solved = [
        row for row in combined if row["statuses"][baseline] in SOLVED
    ]
    summaries.extend([
        summarize("combined:all", combined, baseline, available_actions),
        summarize(
            "combined:any_solved",
            combined_any_solved,
            baseline,
            available_actions,
        ),
        summarize(
            "combined:baseline_solved",
            combined_baseline_solved,
            baseline,
            available_actions,
        ),
    ])

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=list(summaries[0]), delimiter="\t"
            )
            writer.writeheader()
            writer.writerows(summaries)
        print(f"output\t{args.output}")
    for summary in summaries:
        print(
            f"{summary['scope']}\tcases={summary['cases']}\t"
            f"gain={summary['gain_percent']}%\t"
            f"solved_change={summary['solved_change']}\t"
            f"conflicts={summary['outcome_conflicts']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
