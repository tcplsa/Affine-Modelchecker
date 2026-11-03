#!/usr/bin/env python3
"""Fit an interpretable AIG/XAG selector from pre-PDR structural features."""

from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import re
import statistics
from dataclasses import dataclass
from pathlib import Path

from fit_input_order_selector import FEATURES as COARSE_FEATURES


SOLVED = {"SAFE", "UNSAFE"}
ACTIONS = ("aig", "xag")
META = {"year", "name", "family", "aig_path"}


@dataclass
class Sample:
    year: str
    name: str
    family: str
    features: dict[str, float]
    costs: dict[str, float]
    solved: dict[str, bool]


@dataclass
class Node:
    action: str
    feature: str = ""
    threshold: float = 0.0
    left: "Node | None" = None
    right: "Node | None" = None

    def predict(self, values: dict[str, float]) -> str:
        if not self.feature:
            return self.action
        child = self.left if values.get(self.feature, 0.0) <= self.threshold else self.right
        return child.predict(values)  # type: ignore[union-attr]

    def as_dict(self) -> dict:
        result = {"action": self.action}
        if self.feature:
            result.update({
                "feature": self.feature,
                "threshold": self.threshold,
                "left": self.left.as_dict(),  # type: ignore[union-attr]
                "right": self.right.as_dict(),  # type: ignore[union-attr]
            })
        return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-pattern", required=True)
    parser.add_argument("--coarse-features", nargs="+", required=True, type=Path)
    parser.add_argument("--distribution-features", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--timeout-multiplier", type=float, default=1.5)
    parser.add_argument("--min-span", type=float, default=1.0)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--min-leaf", type=int, default=20)
    parser.add_argument("--folds", type=int, default=5)
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def number(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def family_fold(family: str, folds: int) -> int:
    return int.from_bytes(hashlib.sha256(family.encode("utf-8")).digest()[:8], "little") % folds


def thresholds(values: list[float], maximum: int = 16) -> list[float]:
    unique = sorted(set(values))
    candidates = [(a + b) / 2.0 for a, b in zip(unique, unique[1:])]
    if len(candidates) <= maximum:
        return candidates
    return sorted({candidates[(len(candidates) - 1) * i // (maximum - 1)] for i in range(maximum)})


def best_action(rows: list[Sample]) -> tuple[str, float]:
    totals = {action: sum(row.costs[action] for row in rows) for action in ACTIONS}
    return min(totals.items(), key=lambda item: item[1])


def fit_tree(rows: list[Sample], features: list[str], depth: int, min_leaf: int) -> Node:
    action, base_cost = best_action(rows)
    node = Node(action)
    if depth <= 0 or len(rows) < 2 * min_leaf:
        return node
    best = None
    for feature in features:
        for threshold in thresholds([row.features.get(feature, 0.0) for row in rows]):
            left = [row for row in rows if row.features.get(feature, 0.0) <= threshold]
            right = [row for row in rows if row.features.get(feature, 0.0) > threshold]
            if len(left) < min_leaf or len(right) < min_leaf:
                continue
            score = best_action(left)[1] + best_action(right)[1]
            candidate = (score, feature, threshold, left, right)
            if best is None or candidate[:3] < best[:3]:
                best = candidate
    if best is None or best[0] >= base_cost:
        return node
    _score, node.feature, node.threshold, left, right = best
    node.left = fit_tree(left, features, depth - 1, min_leaf)
    node.right = fit_tree(right, features, depth - 1, min_leaf)
    return node


def evaluate(tree: Node, rows: list[Sample]) -> dict[str, float]:
    baseline = sum(row.costs["aig"] for row in rows)
    selected = sum(row.costs[tree.predict(row.features)] for row in rows)
    selected_solved = sum(row.solved[tree.predict(row.features)] for row in rows)
    baseline_solved = sum(row.solved["aig"] for row in rows)
    return {
        "samples": len(rows),
        "baseline_cost": baseline,
        "selected_cost": selected,
        "gain_percent": 100.0 * (baseline - selected) / baseline if baseline else 0.0,
        "solved_delta": selected_solved - baseline_solved,
    }


def merge_features(coarse_paths: list[Path], distribution_path: Path) -> tuple[dict, list[str], list[str]]:
    coarse = {}
    for path in coarse_paths:
        inferred_year = re.search(r"(20\d{2})", path.stem)
        for row in read_tsv(path):
            year = row.get("year") or (inferred_year.group(1) if inferred_year else "")
            coarse[(year, row["name"])] = row
    distribution = {(row["year"], row["name"]): row for row in read_tsv(distribution_path)}
    merged = {}
    for key in coarse.keys() & distribution.keys():
        merged[key] = {**coarse[key], **distribution[key]}
    coarse_names = [name for name in COARSE_FEATURES if any(name in row for row in merged.values())]
    distribution_names = sorted(set(distribution[next(iter(distribution))]) - META) if distribution else []
    return merged, coarse_names, coarse_names + distribution_names


def load_samples(args: argparse.Namespace, static: dict) -> tuple[list[Sample], dict[int, list[Sample]]]:
    observations: dict[tuple[str, str, int], dict[str, list[tuple[float, bool]]]] = {}
    for path_text in sorted(glob.glob(args.results_pattern)):
        match = re.search(r"_s(\d+)\.tsv$", path_text)
        if not match:
            continue
        seed = int(match.group(1))
        for row in read_tsv(Path(path_text)):
            key = (row.get("year", ""), row["name"], seed)
            bucket = observations.setdefault(key, {action: [] for action in ACTIONS})
            penalty = number(row.get("timeout_seconds", "60"), 60.0) * args.timeout_multiplier
            for action, config in (("aig", "state_000"), ("xag", "state_001")):
                solved = row.get(f"{config}_status") in SOLVED
                value = number(row.get(f"{config}_wall_seconds", ""), penalty) if solved else penalty
                bucket[action].append((value, solved))
    by_seed: dict[int, list[Sample]] = {}
    indexed: dict[int, dict[tuple[str, str], Sample]] = {}
    for (year, name, seed), actions in observations.items():
        feature = static.get((year, name))
        if feature is None or any(not values for values in actions.values()):
            continue
        sample = Sample(
            year=year,
            name=name,
            family=feature.get("family", name),
            features={key: number(value) for key, value in feature.items() if key not in META},
            costs={action: statistics.median(value for value, _ in values) for action, values in actions.items()},
            solved={action: all(flag for _, flag in values) for action, values in actions.items()},
        )
        indexed.setdefault(seed, {})[(year, name)] = sample
    common = set.intersection(*(set(rows) for rows in indexed.values()))
    robust = []
    for key in sorted(common):
        members = [indexed[seed][key] for seed in sorted(indexed)]
        costs = {action: max(member.costs[action] for member in members) for action in ACTIONS}
        if max(costs.values()) - min(costs.values()) <= args.min_span:
            continue
        robust.append(Sample(
            year=members[0].year,
            name=members[0].name,
            family=members[0].family,
            features=members[0].features,
            costs=costs,
            solved={action: all(member.solved[action] for member in members) for action in ACTIONS},
        ))
    names = {(row.year, row.name) for row in robust}
    for seed, rows in indexed.items():
        by_seed[seed] = [row for key, row in rows.items() if key in names]
    return robust, by_seed


def validate(rows: list[Sample], by_seed: dict[int, list[Sample]], features: list[str], args: argparse.Namespace) -> dict:
    depth_rows = []
    for depth in range(args.max_depth + 1):
        predictions = []
        for fold in range(args.folds):
            train = [row for row in rows if family_fold(row.family, args.folds) != fold]
            test = [row for row in rows if family_fold(row.family, args.folds) == fold]
            if not train or not test:
                continue
            tree = fit_tree(train, features, depth, args.min_leaf)
            predictions.extend((row, tree.predict(row.features)) for row in test)
        baseline = sum(row.costs["aig"] for row, _ in predictions)
        selected = sum(row.costs[action] for row, action in predictions)
        depth_rows.append({
            "depth": depth,
            "gain_percent": 100.0 * (baseline - selected) / baseline if baseline else 0.0,
            "samples": len(predictions),
        })
    chosen = max(depth_rows, key=lambda row: row["gain_percent"])
    depth = int(chosen["depth"])
    year_rows = []
    for year in sorted({row.year for row in rows}):
        train = [row for row in rows if row.year != year]
        test = [row for row in rows if row.year == year]
        year_rows.append({"year": year, **evaluate(fit_tree(train, features, depth, args.min_leaf), test)})
    transfer_rows = []
    seeds = sorted(by_seed)
    for train_seed in seeds:
        for test_seed in seeds:
            if train_seed == test_seed:
                continue
            test_index = {(row.year, row.name): row for row in by_seed[test_seed]}
            train = by_seed[train_seed]
            test = [test_index[(row.year, row.name)] for row in train if (row.year, row.name) in test_index]
            transfer_rows.append({
                "train_seed": train_seed,
                "test_seed": test_seed,
                **evaluate(fit_tree(train, features, depth, args.min_leaf), test),
            })
    tree = fit_tree(rows, features, depth, args.min_leaf)
    return {
        "feature_count": len(features),
        "chosen_depth": depth,
        "family_cv": chosen,
        "depth_search": depth_rows,
        "leave_one_year_out": year_rows,
        "seed_transfer": transfer_rows,
        "training": evaluate(tree, rows),
        "tree": tree.as_dict(),
        "accepted": (
            chosen["gain_percent"] > 0
            and all(row["gain_percent"] >= 0 for row in year_rows)
            and all(row["gain_percent"] >= 0 for row in transfer_rows)
        ),
    }


def main() -> int:
    args = parse_args()
    static, coarse, enriched = merge_features(args.coarse_features, args.distribution_features)
    rows, by_seed = load_samples(args, static)
    if not rows:
        raise SystemExit("no robust AIG/XAG samples")
    reports = {
        "coarse": validate(rows, by_seed, coarse, args),
        "enriched": validate(rows, by_seed, enriched, args),
    }
    payload = {
        "version": 1,
        "samples": len(rows),
        "families": len({row.family for row in rows}),
        "years": sorted({row.year for row in rows}),
        "reports": reports,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "selector.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    lines = [
        "# Static AIG/XAG Selector",
        "",
        f"- Robust samples: {payload['samples']}",
        f"- Circuit families: {payload['families']}",
        "",
        "| Feature set | Features | Depth | Family-CV gain | Worst year | Worst seed transfer | Accepted |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, report in reports.items():
        worst_year = min(row["gain_percent"] for row in report["leave_one_year_out"])
        worst_seed = min(row["gain_percent"] for row in report["seed_transfer"])
        lines.append(
            f"| {label} | {report['feature_count']} | {report['chosen_depth']} | "
            f"{report['family_cv']['gain_percent']:.3f}% | {worst_year:.3f}% | "
            f"{worst_seed:.3f}% | {report['accepted']} |"
        )
    (args.output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"samples={len(rows)} coarse={len(coarse)} enriched={len(enriched)} output={args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

