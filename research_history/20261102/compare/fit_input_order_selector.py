#!/usr/bin/env python3
"""Fit an interpretable policy tree for deterministic input ordering."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional


SOLVED = {"SAFE", "UNSAFE"}
FEATURES = (
    "inputs", "latches", "aig_ands", "recognized_xors", "and_reduction",
    "xor_density", "next_cone_gates", "next_cone_xors", "next_xor_density",
    "bad_cone_gates", "bad_cone_xors", "bad_xor_density", "root_cone_gates",
    "root_cone_xors", "root_xor_density", "shared_cone_xors",
    "next_only_xors", "bad_only_xors", "deep_cone_xors",
    "xor_depth_mean", "xor_depth_median", "xor_depth_max",
    "next_depth", "bad_depth",
)


@dataclass
class Sample:
    name: str
    family: str
    features: Dict[str, float]
    costs: Dict[str, float]
    solved: Dict[str, bool]


@dataclass
class Node:
    action: str
    feature: Optional[str] = None
    threshold: float = 0.0
    left: Optional["Node"] = None
    right: Optional["Node"] = None

    def predict(self, values: Dict[str, float]) -> str:
        if self.feature is None:
            return self.action
        child = self.left if values[self.feature] <= self.threshold else self.right
        return child.predict(values)  # type: ignore[union-attr]

    def as_dict(self) -> dict:
        result = {"action": self.action}
        if self.feature is not None:
            result.update({
                "feature": self.feature,
                "threshold": self.threshold,
                "left": self.left.as_dict(),  # type: ignore[union-attr]
                "right": self.right.as_dict(),  # type: ignore[union-attr]
            })
        return result


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def action_cost(rows: Iterable[Sample], actions: list[str]) -> tuple[str, float]:
    totals = {action: sum(row.costs[action] for row in rows) for action in actions}
    return min(totals.items(), key=lambda item: item[1])


def thresholds(values: list[float], maximum: int = 16) -> list[float]:
    unique = sorted(set(values))
    if len(unique) <= 1:
        return []
    candidates = [(a + b) / 2.0 for a, b in zip(unique, unique[1:])]
    if len(candidates) <= maximum:
        return candidates
    return sorted({candidates[(len(candidates) - 1) * i // (maximum - 1)] for i in range(maximum)})


def fit_tree(
    rows: list[Sample],
    actions: list[str],
    depth: int,
    min_leaf: int,
) -> Node:
    action, base_cost = action_cost(rows, actions)
    node = Node(action=action)
    if depth <= 0 or len(rows) < 2 * min_leaf:
        return node

    best = None
    for feature in FEATURES:
        for threshold in thresholds([row.features[feature] for row in rows]):
            left = [row for row in rows if row.features[feature] <= threshold]
            right = [row for row in rows if row.features[feature] > threshold]
            if len(left) < min_leaf or len(right) < min_leaf:
                continue
            _, left_cost = action_cost(left, actions)
            _, right_cost = action_cost(right, actions)
            split_cost = left_cost + right_cost
            if best is None or split_cost < best[0]:
                best = (split_cost, feature, threshold, left, right)
    if best is None or best[0] >= base_cost:
        return node
    _, node.feature, node.threshold, left, right = best
    node.left = fit_tree(left, actions, depth - 1, min_leaf)
    node.right = fit_tree(right, actions, depth - 1, min_leaf)
    return node


def load_samples(
    features_paths: Iterable[Path],
    results_paths: Iterable[Path],
    actions: list[str],
    timeout: float,
    timeout_multiplier: float,
    metric: str,
) -> list[Sample]:
    features = {}
    unscoped_features = {}
    for features_path in features_paths:
        match = re.search(r"(20\d{2})", features_path.stem)
        inferred_year = match.group(1) if match else ""
        for feature_row in read_tsv(features_path):
            year = feature_row.get("year") or inferred_year
            name = feature_row["name"]
            if year:
                features[(year, name)] = feature_row
            else:
                unscoped_features[name] = feature_row
    samples = []
    result_rows = (
        row
        for results_path in results_paths
        for row in read_tsv(results_path)
    )
    for row in result_rows:
        name = row.get("name", "")
        feature = (
            features.get((row.get("year", ""), name))
            or unscoped_features.get(name)
        )
        if feature is None:
            continue
        solved_statuses = {
            row.get(f"{action}_status", "")
            for action in actions
            if row.get(f"{action}_status", "") in SOLVED
        }
        if len(solved_statuses) > 1:
            continue
        costs = {}
        solved = {}
        try:
            row_timeout = float(row.get("timeout_seconds") or timeout)
        except ValueError:
            row_timeout = timeout
        for action in actions:
            status = row.get(f"{action}_status", "")
            try:
                wall = float(row.get(f"{action}_wall_seconds", ""))
            except ValueError:
                wall = row_timeout * timeout_multiplier
            try:
                pdr = float(row.get(f"{action}_pdr_runtime", ""))
            except ValueError:
                pdr = wall
            transform = 0.0
            for suffix in ("input_order_runtime", "conversion_runtime"):
                try:
                    transform += float(row.get(f"{action}_{suffix}", "") or 0.0)
                except ValueError:
                    pass
            solved[action] = status in SOLVED
            if metric == "wall":
                measured = wall
            elif metric == "pdr":
                measured = pdr
            else:
                measured = pdr + transform
            costs[action] = (
                measured if solved[action] else row_timeout * timeout_multiplier
            )
        samples.append(Sample(
            name=row["name"],
            family=feature.get("family", row["name"]),
            features={name: float(feature.get(name) or 0.0) for name in FEATURES},
            costs=costs,
            solved=solved,
        ))
    return samples


def evaluate(rows: list[Sample], tree: Node, actions: list[str]) -> dict:
    totals = {action: sum(row.costs[action] for row in rows) for action in actions}
    selector = sum(row.costs[tree.predict(row.features)] for row in rows)
    oracle = sum(min(row.costs.values()) for row in rows)
    choices = {action: 0 for action in actions}
    selector_solved = 0
    for row in rows:
        choice = tree.predict(row.features)
        choices[choice] += 1
        selector_solved += int(row.solved[choice])
    baseline = totals[actions[0]]
    return {
        "cases": len(rows),
        "totals": totals,
        "selector": selector,
        "oracle": oracle,
        "gain_vs_baseline_percent": 100.0 * (baseline - selector) / baseline if baseline else 0.0,
        "oracle_gain_percent": 100.0 * (baseline - oracle) / baseline if baseline else 0.0,
        "choices": choices,
        "solved": {action: sum(row.solved[action] for row in rows) for action in actions},
        "selector_solved": selector_solved,
    }


def family_fold(family: str, folds: int) -> int:
    digest = hashlib.sha256(family.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "little") % folds


def choose_depth(rows: list[Sample], actions: list[str], max_depth: int, min_leaf: int, folds: int) -> int:
    scores = []
    baseline_cost = sum(row.costs[actions[0]] for row in rows)
    print(f"cv_baseline_cost\t{baseline_cost:.6f}")
    for depth in range(max_depth + 1):
        total = 0.0
        for fold in range(folds):
            train = [row for row in rows if family_fold(row.family, folds) != fold]
            test = [row for row in rows if family_fold(row.family, folds) == fold]
            if not train or not test:
                continue
            tree = fit_tree(train, actions, depth, min_leaf)
            total += sum(row.costs[tree.predict(row.features)] for row in test)
        scores.append((total, depth))
        print(f"cv_depth_{depth}_cost\t{total:.6f}")
    best_cost, best_depth = min(scores)
    return best_depth if best_cost < baseline_cost else -1


def print_tree(node: Node, indent: str = "") -> None:
    if node.feature is None:
        print(f"{indent}use {node.action}")
        return
    print(f"{indent}if {node.feature} <= {node.threshold:.6g}:")
    print_tree(node.left, indent + "  ")  # type: ignore[arg-type]
    print(f"{indent}else:")
    print_tree(node.right, indent + "  ")  # type: ignore[arg-type]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fit a family-grouped input-order policy tree.")
    parser.add_argument("--train-features", type=Path, nargs="+", required=True)
    parser.add_argument("--train-results", type=Path, nargs="+", required=True)
    parser.add_argument("--test-features", type=Path, nargs="+")
    parser.add_argument("--test-results", type=Path, nargs="+")
    parser.add_argument(
        "--actions", default="original,fanout_desc,fanout_asc",
        help="result-column prefixes; first action is the baseline",
    )
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--timeout-multiplier", type=float, default=2.0)
    parser.add_argument(
        "--metric", choices=["algorithm", "pdr", "wall"], default="algorithm",
    )
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--min-leaf", type=int, default=12)
    parser.add_argument("--cv-folds", type=int, default=5)
    parser.add_argument("--model-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    actions = [item.strip() for item in args.actions.split(",") if item.strip()]
    train = load_samples(
        args.train_features, args.train_results, actions,
        args.timeout, args.timeout_multiplier, args.metric,
    )
    if not train:
        raise SystemExit("no training rows matched the feature and result files")
    depth = choose_depth(train, actions, args.max_depth, args.min_leaf, args.cv_folds)
    tree = (
        fit_tree(train, actions, depth, args.min_leaf)
        if depth >= 0 else Node(action=actions[0])
    )
    print(f"selected_depth\t{depth if depth >= 0 else 'baseline'}")
    print("tree")
    print_tree(tree)
    print("train_metrics")
    print(json.dumps(evaluate(train, tree, actions), ensure_ascii=False, sort_keys=True))

    if args.test_features and args.test_results:
        test = load_samples(
            args.test_features, args.test_results, actions,
            args.timeout, args.timeout_multiplier, args.metric,
        )
        print("test_metrics")
        print(json.dumps(evaluate(test, tree, actions), ensure_ascii=False, sort_keys=True))
    if args.model_output:
        args.model_output.parent.mkdir(parents=True, exist_ok=True)
        args.model_output.write_text(
            json.dumps(
                {"actions": actions, "features": FEATURES, "tree": tree.as_dict()},
                ensure_ascii=False, indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        print(f"model_output\t{args.model_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
