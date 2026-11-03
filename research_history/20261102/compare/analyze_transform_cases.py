#!/usr/bin/env python3
"""Classify transform wins/losses and contrast their static circuit features."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}
STATIC_FEATURES = (
    "size_bytes", "inputs", "latches", "outputs", "bads", "constraints",
    "reset_functions",
    "aig_ands", "recognized_xors", "and_reduction", "xor_density",
    "next_cone_gates", "next_cone_xors", "next_xor_density",
    "reset_cone_gates", "reset_cone_xors", "reset_xor_density",
    "bad_cone_gates", "bad_cone_xors", "bad_xor_density",
    "root_cone_gates", "root_cone_xors", "root_xor_density",
    "shared_cone_xors", "next_only_xors", "bad_only_xors", "deep_cone_xors",
    "xor_depth_mean", "xor_depth_median", "xor_depth_max",
    "next_depth", "reset_depth", "bad_depth",
)
TRANSFORM_FEATURES = (
    "xor_coverage", "removed_and_ratio", "query_ratio", "cti_ratio",
    "mic_ratio", "inductive_ratio", "pdr_depth_delta", "transform_runtime",
)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def number(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, ""))
    except (TypeError, ValueError):
        return default


def ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0 else 0.0


def median(values: list[float]) -> float:
    return statistics.median(values) if values else float("nan")


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def time_bin(seconds: float) -> str:
    if seconds < 1:
        return "lt1"
    if seconds < 5:
        return "1to5"
    if seconds < 30:
        return "5to30"
    if seconds < 300:
        return "30to300"
    return "ge300"


def classify(
    baseline_status: str,
    action_status: str,
    baseline_seconds: float,
    action_seconds: float,
    ratio_threshold: float,
    min_gap: float,
) -> str:
    if baseline_status not in SOLVED and action_status in SOLVED:
        return "faster"
    if baseline_status in SOLVED and action_status not in SOLVED:
        return "slower"
    if baseline_status not in SOLVED and action_status not in SOLVED:
        return "unresolved"
    difference = baseline_seconds - action_seconds
    speedup = ratio(baseline_seconds, action_seconds)
    if difference >= min_gap and speedup >= ratio_threshold:
        return "faster"
    if difference <= -min_gap and speedup <= 1.0 / ratio_threshold:
        return "slower"
    return "neutral"


def infer_actions(header: list[str], baseline: str) -> list[str]:
    actions = []
    for column in header:
        if not column.endswith("_status"):
            continue
        action = column[:-7]
        if action != baseline:
            actions.append(action)
    return actions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze progressive transform labels.")
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--results", type=Path, nargs="+", required=True)
    parser.add_argument("--baseline", default="aig_original")
    parser.add_argument("--actions", help="comma-separated result prefixes; default: infer")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--timeout-multiplier", type=float, default=2.0)
    parser.add_argument(
        "--metric", choices=["algorithm", "pdr", "wall"], default="algorithm",
        help="algorithm=input ordering + representation conversion + PDR",
    )
    parser.add_argument("--ratio-threshold", type=float, default=1.10)
    parser.add_argument("--min-gap", type=float, default=0.05)
    parser.add_argument("--cases-output", type=Path)
    parser.add_argument("--features-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    feature_rows = {row["name"]: row for row in read_tsv(args.features)}
    first_rows = read_tsv(args.results[0])
    if not first_rows:
        raise SystemExit("first result file has no rows")
    actions = (
        [item.strip() for item in args.actions.split(",") if item.strip()]
        if args.actions else infer_actions(list(first_rows[0]), args.baseline)
    )
    cases = []

    for result_path in args.results:
        for row in read_tsv(result_path):
            static = feature_rows.get(row.get("name", ""))
            if static is None:
                continue
            row_timeout = number(row, "timeout_seconds", args.timeout)
            penalty = row_timeout * args.timeout_multiplier
            baseline_status = row.get(f"{args.baseline}_status", "")
            baseline_wall = number(row, f"{args.baseline}_wall_seconds", penalty)
            baseline_pdr = number(row, f"{args.baseline}_pdr_runtime", baseline_wall)
            baseline_transform = (
                number(row, f"{args.baseline}_input_order_runtime")
                + number(row, f"{args.baseline}_conversion_runtime")
            )
            if args.metric == "wall":
                baseline_metric = baseline_wall
            elif args.metric == "pdr":
                baseline_metric = baseline_pdr
            else:
                baseline_metric = baseline_pdr + baseline_transform
            baseline_score = baseline_metric if baseline_status in SOLVED else penalty
            baseline_queries = number(row, f"{args.baseline}_queries")
            baseline_cti = number(row, f"{args.baseline}_cti")
            baseline_mic = number(row, f"{args.baseline}_mic")
            baseline_inductive = number(row, f"{args.baseline}_inductive")
            baseline_depth = number(row, f"{args.baseline}_pdr_depth")

            for action in actions:
                action_status = row.get(f"{action}_status", "")
                action_wall = number(row, f"{action}_wall_seconds", penalty)
                action_pdr = number(row, f"{action}_pdr_runtime", action_wall)
                action_transform = (
                    number(row, f"{action}_input_order_runtime")
                    + number(row, f"{action}_conversion_runtime")
                )
                if args.metric == "wall":
                    action_metric = action_wall
                elif args.metric == "pdr":
                    action_metric = action_pdr
                else:
                    action_metric = action_pdr + action_transform
                action_score = action_metric if action_status in SOLVED else penalty
                label = classify(
                    baseline_status, action_status, baseline_score, action_score,
                    args.ratio_threshold, args.min_gap,
                )
                candidate_xors = number(row, f"{action}_candidate_xors")
                selected_xors = number(row, f"{action}_recognized_xors")
                original_ands = number(row, f"{action}_original_ands")
                case = {
                    "source": result_path.name,
                    "name": row["name"],
                    "family": static.get("family", ""),
                    "action": action,
                    "label": label,
                    "time_bin": time_bin(baseline_score),
                    "baseline_status": baseline_status,
                    "action_status": action_status,
                    "baseline_seconds": f"{baseline_score:.6f}",
                    "action_seconds": f"{action_score:.6f}",
                    "baseline_wall_seconds": f"{baseline_wall:.6f}",
                    "action_wall_seconds": f"{action_wall:.6f}",
                    "baseline_pdr_seconds": f"{baseline_pdr:.6f}",
                    "action_pdr_seconds": f"{action_pdr:.6f}",
                    "speedup": f"{ratio(baseline_score, action_score):.6f}",
                    "candidate_xors": f"{candidate_xors:.0f}",
                    "selected_xors": f"{selected_xors:.0f}",
                    "xor_coverage": f"{ratio(selected_xors, candidate_xors):.6f}",
                    "removed_and_ratio": f"{ratio(number(row, f'{action}_removed_ands'), original_ands):.6f}",
                    "query_ratio": f"{ratio(baseline_queries, number(row, f'{action}_queries')):.6f}",
                    "cti_ratio": f"{ratio(baseline_cti, number(row, f'{action}_cti')):.6f}",
                    "mic_ratio": f"{ratio(baseline_mic, number(row, f'{action}_mic')):.6f}",
                    "inductive_ratio": f"{ratio(baseline_inductive, number(row, f'{action}_inductive')):.6f}",
                    "pdr_depth_delta": f"{number(row, f'{action}_pdr_depth') - baseline_depth:.0f}",
                    "transform_runtime": f"{action_transform:.6f}",
                }
                for feature in STATIC_FEATURES:
                    case[feature] = static.get(feature, "")
                cases.append(case)

    if not cases:
        raise SystemExit("no result rows matched the structural feature file")
    cases_output = args.cases_output or args.results[0].with_name(
        args.results[0].stem + "_cases.tsv"
    )
    features_output = args.features_output or args.results[0].with_name(
        args.results[0].stem + "_feature_contrast.tsv"
    )
    cases_output.parent.mkdir(parents=True, exist_ok=True)
    case_header = list(cases[0])
    with cases_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=case_header, delimiter="\t")
        writer.writeheader()
        writer.writerows(cases)

    contrasts = []
    for action in actions:
        action_cases = [case for case in cases if case["action"] == action]
        for feature in STATIC_FEATURES + TRANSFORM_FEATURES:
            fast = [number(case, feature) for case in action_cases if case["label"] == "faster"]
            slow = [number(case, feature) for case in action_cases if case["label"] == "slower"]
            all_values = fast + slow
            spread = percentile(all_values, 0.75) - percentile(all_values, 0.25)
            fast_median = median(fast)
            slow_median = median(slow)
            contrasts.append({
                "action": action,
                "feature": feature,
                "faster_count": len(fast),
                "slower_count": len(slow),
                "faster_median": f"{fast_median:.6f}",
                "slower_median": f"{slow_median:.6f}",
                "median_difference": f"{fast_median - slow_median:.6f}",
                "robust_effect": f"{(fast_median - slow_median) / spread:.6f}"
                if spread > 0 else "",
            })
    with features_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(contrasts[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(contrasts)

    print(f"cases\t{len(cases)}")
    print(f"case_output\t{cases_output}")
    print(f"feature_output\t{features_output}")
    for action in actions:
        selected = [case for case in cases if case["action"] == action]
        counts = Counter(case["label"] for case in selected)
        speedups = [number(case, "speedup") for case in selected if case["label"] != "unresolved"]
        print(
            f"{action}\tfaster={counts['faster']}\tslower={counts['slower']}\t"
            f"neutral={counts['neutral']}\tunresolved={counts['unresolved']}\t"
            f"median_speedup={median(speedups):.6f}"
        )
        by_bin = defaultdict(Counter)
        for case in selected:
            by_bin[case["time_bin"]][case["label"]] += 1
        for bucket in ("lt1", "1to5", "5to30", "30to300", "ge300"):
            count = by_bin[bucket]
            if sum(count.values()):
                print(
                    f"  {bucket}\tfaster={count['faster']}\tslower={count['slower']}\t"
                    f"neutral={count['neutral']}\tunresolved={count['unresolved']}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
