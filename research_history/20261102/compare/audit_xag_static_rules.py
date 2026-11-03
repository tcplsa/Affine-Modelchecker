#!/usr/bin/env python3
"""Audit frozen pre-PDR AIG/XAG threshold rules on an unseen year."""

from __future__ import annotations

import argparse
import csv
import glob
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

import fit_xag_distribution_selector as selector


SOLVED = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-results-pattern", required=True)
    parser.add_argument("--train-coarse", nargs="+", required=True, type=Path)
    parser.add_argument("--train-distribution", required=True, type=Path)
    parser.add_argument("--validation-results-pattern", required=True)
    parser.add_argument("--validation-coarse", nargs="+", required=True, type=Path)
    parser.add_argument("--validation-distribution", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--timeout-multiplier", type=float, default=1.5)
    parser.add_argument("--min-span", type=float, default=1.0)
    parser.add_argument("--min-support", type=int, default=10)
    parser.add_argument("--folds", type=int, default=5)
    return parser.parse_args()


def number(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def validation_samples(args: argparse.Namespace, static: dict) -> list[selector.Sample]:
    observations = defaultdict(lambda: defaultdict(list))
    for path_text in sorted(glob.glob(args.validation_results_pattern)):
        match = re.search(r"_s(\d+)\.tsv$", path_text)
        if not match:
            continue
        seed = int(match.group(1))
        for row in read_tsv(Path(path_text)):
            key = (row.get("year", ""), row["name"], seed)
            penalty = number(row.get("timeout_seconds", "300"), 300.0) * args.timeout_multiplier
            for action, config in (("aig", "state_000"), ("xag", "state_001")):
                solved = row.get(f"{config}_status") in SOLVED
                cost = number(row.get(f"{config}_wall_seconds", ""), penalty) if solved else penalty
                observations[key][action].append((cost, solved))
    indexed = defaultdict(dict)
    for (year, name, seed), actions in observations.items():
        feature = static.get((year, name))
        if feature is None or any(action not in actions for action in ("aig", "xag")):
            continue
        indexed[seed][(year, name)] = selector.Sample(
            year=year,
            name=name,
            family=feature.get("family", name),
            features={key: number(value) for key, value in feature.items() if key not in selector.META},
            costs={action: statistics.median(value for value, _ in actions[action]) for action in ("aig", "xag")},
            solved={action: all(flag for _, flag in actions[action]) for action in ("aig", "xag")},
        )
    common = set.intersection(*(set(rows) for rows in indexed.values()))
    result = []
    for key in sorted(common):
        members = [indexed[seed][key] for seed in sorted(indexed)]
        costs = {action: max(member.costs[action] for member in members) for action in ("aig", "xag")}
        if max(costs.values()) - min(costs.values()) <= args.min_span:
            continue
        result.append(selector.Sample(
            year=members[0].year,
            name=members[0].name,
            family=members[0].family,
            features=members[0].features,
            costs=costs,
            solved={action: all(member.solved[action] for member in members) for action in ("aig", "xag")},
        ))
    return result


def selected(rule: dict, row: selector.Sample) -> bool:
    value = row.features.get(rule["feature"], 0.0)
    return value <= rule["threshold"] if rule["direction"] == "le" else value > rule["threshold"]


def evaluate(rule: dict, rows: list[selector.Sample]) -> dict:
    baseline = sum(row.costs["aig"] for row in rows)
    chosen = [("xag" if selected(rule, row) else "aig", row) for row in rows]
    cost = sum(row.costs[action] for action, row in chosen)
    return {
        "samples": len(rows),
        "selected_xag": sum(action == "xag" for action, _ in chosen),
        "gain_percent": 100.0 * (baseline - cost) / baseline if baseline else 0.0,
        "solved_delta": sum(row.solved[action] - row.solved["aig"] for action, row in chosen),
    }


def main() -> int:
    args = parse_args()
    train_static, _coarse, features = selector.merge_features(args.train_coarse, args.train_distribution)
    train_args = argparse.Namespace(
        results_pattern=args.train_results_pattern,
        timeout_multiplier=args.timeout_multiplier,
        min_span=args.min_span,
    )
    train, _by_seed = selector.load_samples(train_args, train_static)
    validation_static, _validation_coarse, validation_features = selector.merge_features(
        args.validation_coarse, args.validation_distribution,
    )
    validation = validation_samples(args, validation_static)
    features = sorted(set(features) & set(validation_features))
    years = sorted({row.year for row in train})
    candidates = []
    for feature in features:
        values = [row.features.get(feature, 0.0) for row in train]
        for threshold in selector.thresholds(values, maximum=32):
            for direction in ("le", "gt"):
                rule = {"feature": feature, "threshold": threshold, "direction": direction}
                overall = evaluate(rule, train)
                if overall["selected_xag"] < args.min_support:
                    continue
                year_metrics = [evaluate(rule, [row for row in train if row.year == year]) for year in years]
                fold_metrics = [
                    evaluate(rule, [row for row in train if selector.family_fold(row.family, args.folds) == fold])
                    for fold in range(args.folds)
                ]
                guarded = (
                    overall["gain_percent"] > 0
                    and overall["solved_delta"] >= 0
                    and all(metric["gain_percent"] >= 0 and metric["solved_delta"] >= 0 for metric in year_metrics)
                    and all(metric["gain_percent"] >= 0 and metric["solved_delta"] >= 0 for metric in fold_metrics)
                )
                validation_metric = evaluate(rule, validation)
                candidates.append({
                    **rule,
                    "train_gain_percent": overall["gain_percent"],
                    "train_selected_xag": overall["selected_xag"],
                    "train_solved_delta": overall["solved_delta"],
                    "worst_year_gain_percent": min(metric["gain_percent"] for metric in year_metrics),
                    "worst_fold_gain_percent": min(metric["gain_percent"] for metric in fold_metrics),
                    "guarded": guarded,
                    "validation_gain_percent": validation_metric["gain_percent"],
                    "validation_selected_xag": validation_metric["selected_xag"],
                    "validation_solved_delta": validation_metric["solved_delta"],
                })
    guarded = [row for row in candidates if row["guarded"]]
    guarded.sort(
        key=lambda row: (
            row["worst_year_gain_percent"], row["worst_fold_gain_percent"],
            row["train_gain_percent"],
        ),
        reverse=True,
    )
    frozen = guarded[0] if guarded else None
    survivors = [
        row for row in guarded
        if row["validation_gain_percent"] >= 0 and row["validation_solved_delta"] >= 0
    ]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_rows = guarded[:100]
    if output_rows:
        with (args.output_dir / "guarded_rules.tsv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]), delimiter="\t")
            writer.writeheader()
            writer.writerows(output_rows)
    payload = {
        "version": 1,
        "training_samples": len(train),
        "validation_samples": len(validation),
        "features": len(features),
        "candidate_rules": len(candidates),
        "training_guarded_rules": len(guarded),
        "validation_survivors": len(survivors),
        "frozen_training_rule": frozen,
    }
    (args.output_dir / "audit.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    lines = [
        "# Frozen Static Rule Audit",
        "",
        f"- Training samples: {len(train)}",
        f"- Unseen-2024 validation samples: {len(validation)}",
        f"- Candidate rules: {len(candidates)}",
        f"- Rules passing all training-year/family-fold guards: {len(guarded)}",
        f"- Guarded rules also non-negative on 2024: {len(survivors)}",
        "",
    ]
    if frozen:
        lines.extend([
            "## Frozen Training Choice",
            "",
            f"`XAG if {frozen['feature']} {frozen['direction']} {frozen['threshold']:.6g}`",
            "",
            f"- training gain: {frozen['train_gain_percent']:.3f}%",
            f"- worst training-year gain: {frozen['worst_year_gain_percent']:.3f}%",
            f"- worst family-fold gain: {frozen['worst_fold_gain_percent']:.3f}%",
            f"- 2024 gain: {frozen['validation_gain_percent']:.3f}%",
            f"- 2024 solved delta: {frozen['validation_solved_delta']:+d}",
        ])
    (args.output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"train={len(train)} validation={len(validation)} guarded={len(guarded)} "
        f"survivors={len(survivors)} output={args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

