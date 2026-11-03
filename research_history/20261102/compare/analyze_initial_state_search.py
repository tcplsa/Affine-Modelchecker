#!/usr/bin/env python3
"""Summarize and label mixed initial-state search results."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from analyze_transform_cases import STATIC_FEATURES, classify


SOLVED = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze initial-state search results.")
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--features", type=Path)
    parser.add_argument("--baseline", default="state_000")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--timeout-multiplier", type=float, default=1.5)
    parser.add_argument("--metric", choices=["algorithm", "pdr", "wall"], default="algorithm")
    parser.add_argument("--ratio-threshold", type=float, default=1.10)
    parser.add_argument("--min-gap", type=float, default=0.01)
    parser.add_argument("--cases-output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def number(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, ""))
    except (TypeError, ValueError):
        return default


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


def main() -> int:
    args = parse_args()
    rows = read_tsv(args.results)
    design = json.loads(args.design.read_text(encoding="utf-8"))
    configs = design.get("configs", [])
    actions = [config["id"] for config in configs]
    if args.baseline not in actions:
        raise SystemExit(f"baseline {args.baseline!r} is missing from the design")
    config_by_id = {config["id"]: config for config in configs}
    features = (
        {row["name"]: row for row in read_tsv(args.features)}
        if args.features else {}
    )

    cases = []
    totals = {action: 0.0 for action in actions}
    solved_counts = Counter()
    best_counts = Counter()
    label_counts = {action: Counter() for action in actions}
    baseline_total = 0.0
    oracle_total = 0.0

    for row in rows:
        row_timeout = number(row, "timeout_seconds", args.timeout)
        penalty = row_timeout * args.timeout_multiplier
        scores = {
            action: action_cost(row, action, args.metric, penalty)
            for action in actions
        }
        baseline_status, baseline_score = scores[args.baseline]
        best_action = min(actions, key=lambda action: scores[action][1])
        baseline_total += baseline_score
        oracle_total += scores[best_action][1]
        best_counts[best_action] += 1
        static = features.get(row["name"], {})

        for action in actions:
            status, score = scores[action]
            totals[action] += score
            solved_counts[action] += int(status in SOLVED)
            label = classify(
                baseline_status, status, baseline_score, score,
                args.ratio_threshold, args.min_gap,
            )
            label_counts[action][label] += 1
            config = config_by_id[action]
            case = {
                "name": row["name"],
                "config": action,
                "config_label": config.get("label", action),
                "label": label,
                "best": int(action == best_action),
                "status": status,
                "baseline_status": baseline_status,
                "seconds": f"{score:.6f}",
                "baseline_seconds": f"{baseline_score:.6f}",
                "speedup": f"{baseline_score / score:.6f}" if score else "",
                "representation": (
                    "aig" if config.get("forward_aig", 0) else "hybrid-xag"
                ),
                "xag_policy": config.get("xag_policy", "none"),
                "xag_fraction": config.get("xag_fraction", 0.0),
                "xag_seed": config.get("xag_seed", 0),
                "input_order": config.get("input_order", "original"),
                "input_order_seed": config.get("input_order_seed", 0),
                "perturb_modes": config.get("perturb_modes", ""),
                "perturb_seed": config.get("perturb_seed", 0),
                "recognized_xors": row.get(f"{action}_recognized_xors", ""),
                "removed_ands": row.get(f"{action}_removed_ands", ""),
                "pdr_depth": row.get(f"{action}_pdr_depth", ""),
                "queries": row.get(f"{action}_queries", ""),
                "cti": row.get(f"{action}_cti", ""),
                "mic": row.get(f"{action}_mic", ""),
            }
            for feature in STATIC_FEATURES:
                case[feature] = static.get(feature, "")
            cases.append(case)

    if not rows:
        raise SystemExit("result file has no rows")
    cases_output = args.cases_output or args.results.with_name(
        args.results.stem + "_cases.tsv"
    )
    summary_output = args.summary_output or args.results.with_name(
        args.results.stem + "_summary.tsv"
    )
    cases_output.parent.mkdir(parents=True, exist_ok=True)
    with cases_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(cases[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(cases)

    summaries = []
    for action in actions:
        counts = label_counts[action]
        summaries.append({
            "config": action,
            "label": config_by_id[action].get("label", action),
            "solved": solved_counts[action],
            "best_count": best_counts[action],
            "faster": counts["faster"],
            "slower": counts["slower"],
            "neutral": counts["neutral"],
            "unresolved": counts["unresolved"],
            "total_seconds": f"{totals[action]:.6f}",
            "gain_vs_baseline_percent": (
                f"{100.0 * (baseline_total - totals[action]) / baseline_total:.6f}"
                if baseline_total else "0.000000"
            ),
        })
    with summary_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(summaries)

    print(f"models\t{len(rows)}")
    print(f"states\t{len(actions)}")
    print(f"baseline_total\t{baseline_total:.6f}")
    print(f"oracle_total\t{oracle_total:.6f}")
    print(
        f"oracle_gain_percent\t"
        f"{100.0 * (baseline_total - oracle_total) / baseline_total:.6f}"
    )
    for summary in sorted(summaries, key=lambda item: float(item["total_seconds"]))[:10]:
        print(
            f"{summary['config']}\ttotal={summary['total_seconds']}\t"
            f"gain={summary['gain_vs_baseline_percent']}%\t"
            f"solved={summary['solved']}\tbest={summary['best_count']}"
        )
    print(f"cases_output\t{cases_output}")
    print(f"summary_output\t{summary_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
