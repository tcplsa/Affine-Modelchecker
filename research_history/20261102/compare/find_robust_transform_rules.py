#!/usr/bin/env python3
"""Find conservative static transform rules that improve every dataset."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from analyze_transform_cases import STATIC_FEATURES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rank one-feature transform rules by worst-dataset gain."
    )
    parser.add_argument(
        "--cases", action="append", required=True, metavar="LABEL=PATH",
        help="case TSV and dataset label; repeat for independent datasets",
    )
    parser.add_argument(
        "--actions",
        help="comma-separated transforms; default: all actions in every dataset",
    )
    parser.add_argument("--min-selected", type=int, default=5)
    parser.add_argument("--max-thresholds", type=int, default=64)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--evaluate-rule", action="append", default=[],
        metavar="ACTION,FEATURE,DIRECTION,THRESHOLD",
        help="evaluate a frozen rule; repeat as needed",
    )
    parser.add_argument("--evaluate-only", action="store_true")
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def parse_case_files(values: list[str]) -> dict[str, list[dict[str, str]]]:
    datasets = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"invalid --cases value {value!r}; expected LABEL=PATH")
        label, path = value.split("=", 1)
        if not label or not path:
            raise SystemExit(f"invalid --cases value {value!r}; expected LABEL=PATH")
        datasets[label] = read_tsv(Path(path))
    return datasets


def number(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key, ""))
    except (TypeError, ValueError):
        return 0.0


def thresholds(values: list[float], maximum: int) -> list[float]:
    unique = sorted(set(values))
    candidates = [(left + right) / 2.0 for left, right in zip(unique, unique[1:])]
    if len(candidates) <= maximum:
        return candidates
    return sorted({
        candidates[(len(candidates) - 1) * index // (maximum - 1)]
        for index in range(maximum)
    })


def evaluate_rule(
    action_rows: dict[str, list[dict[str, str]]],
    feature: str,
    direction: str,
    threshold: float,
) -> tuple[dict[str, float], dict[str, int], dict[str, tuple[int, int]], float]:
    choose = (
        (lambda value: value >= threshold)
        if direction == "ge"
        else (lambda value: value <= threshold)
    )
    gains = {}
    selected = {}
    solved = {}
    total_baseline = 0.0
    total_policy = 0.0
    for label, rows in action_rows.items():
        selected[label] = sum(choose(number(row, feature)) for row in rows)
        baseline_solved = sum(
            row.get("baseline_status") in {"SAFE", "UNSAFE"} for row in rows
        )
        policy_solved = sum(
            (
                row.get("action_status") in {"SAFE", "UNSAFE"}
                if choose(number(row, feature))
                else row.get("baseline_status") in {"SAFE", "UNSAFE"}
            )
            for row in rows
        )
        solved[label] = (baseline_solved, policy_solved)
        baseline = sum(number(row, "baseline_seconds") for row in rows)
        policy = sum(
            number(row, "action_seconds")
            if choose(number(row, feature))
            else number(row, "baseline_seconds")
            for row in rows
        )
        gains[label] = 100.0 * (baseline - policy) / baseline if baseline else 0.0
        total_baseline += baseline
        total_policy += policy
    total_gain = (
        100.0 * (total_baseline - total_policy) / total_baseline
        if total_baseline else 0.0
    )
    return gains, selected, solved, total_gain


def main() -> int:
    args = parse_args()
    datasets = parse_case_files(args.cases)
    action_sets = [
        {row["action"] for row in rows}
        for rows in datasets.values()
    ]
    common_actions = set.intersection(*action_sets)
    actions = (
        [item.strip() for item in args.actions.split(",") if item.strip()]
        if args.actions else sorted(common_actions)
    )
    missing = set(actions) - common_actions
    if missing:
        raise SystemExit(f"actions missing from at least one dataset: {sorted(missing)}")

    for specification in args.evaluate_rule:
        fields = [item.strip() for item in specification.split(",")]
        if len(fields) != 4:
            raise SystemExit(
                f"invalid --evaluate-rule {specification!r}; "
                "expected ACTION,FEATURE,DIRECTION,THRESHOLD"
            )
        action, feature, direction, threshold_text = fields
        if action not in common_actions:
            raise SystemExit(f"fixed-rule action missing from a dataset: {action}")
        if feature not in STATIC_FEATURES or direction not in {"ge", "le"}:
            raise SystemExit(f"invalid fixed rule: {specification}")
        threshold = float(threshold_text)
        action_rows = {
            label: [row for row in rows if row["action"] == action]
            for label, rows in datasets.items()
        }
        gains, selected, solved, total_gain = evaluate_rule(
            action_rows, feature, direction, threshold,
        )
        details = " ".join(
            f"{label}={gains[label]:.6f}%/{selected[label]}"
            f"/solved:{solved[label][0]}->{solved[label][1]}"
            for label in datasets
        )
        print(
            f"fixed {action} if {feature} {direction} {threshold:.9g}: "
            f"worst={min(gains.values()):.6f}% total={total_gain:.6f}% {details}"
        )
    if args.evaluate_only:
        return 0

    ranked = []
    for action in actions:
        action_rows = {
            label: [row for row in rows if row["action"] == action]
            for label, rows in datasets.items()
        }
        for feature in STATIC_FEATURES:
            pooled = [
                number(row, feature)
                for rows in action_rows.values()
                for row in rows
            ]
            for threshold in thresholds(pooled, args.max_thresholds):
                for direction in ("ge", "le"):
                    gains, selected, _solved, total_gain = evaluate_rule(
                        action_rows, feature, direction, threshold,
                    )
                    if any(
                        count < args.min_selected for count in selected.values()
                    ):
                        continue
                    ranked.append({
                        "action": action,
                        "feature": feature,
                        "direction": direction,
                        "threshold": threshold,
                        "worst_gain_percent": min(gains.values()),
                        "total_gain_percent": total_gain,
                        "gains": gains,
                        "selected": selected,
                    })

    ranked.sort(
        key=lambda row: (row["worst_gain_percent"], row["total_gain_percent"]),
        reverse=True,
    )
    header = [
        "action", "feature", "direction", "threshold",
        "worst_gain_percent", "total_gain_percent",
    ]
    for label in datasets:
        header.extend((f"{label}_gain_percent", f"{label}_selected"))
    output_rows = []
    for rule in ranked:
        row = {
            "action": rule["action"],
            "feature": rule["feature"],
            "direction": rule["direction"],
            "threshold": f"{rule['threshold']:.9g}",
            "worst_gain_percent": f"{rule['worst_gain_percent']:.6f}",
            "total_gain_percent": f"{rule['total_gain_percent']:.6f}",
        }
        for label in datasets:
            row[f"{label}_gain_percent"] = f"{rule['gains'][label]:.6f}"
            row[f"{label}_selected"] = rule["selected"][label]
        output_rows.append(row)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=header, delimiter="\t")
            writer.writeheader()
            writer.writerows(output_rows)
        print(f"output\t{args.output}")
    for row in output_rows[: args.top]:
        details = " ".join(
            f"{label}={row[f'{label}_gain_percent']}%/{row[f'{label}_selected']}"
            for label in datasets
        )
        print(
            f"{row['action']} if {row['feature']} {row['direction']} "
            f"{row['threshold']}: worst={row['worst_gain_percent']}% "
            f"total={row['total_gain_percent']}% {details}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
