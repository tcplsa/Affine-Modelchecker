#!/usr/bin/env python3
"""Analyze complementary XOR-bucket interventions as causal contrasts."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}
BUCKETS = (
    "next_fanout_0_1",
    "next_fanout_2_3",
    "next_fanout_4_5",
    "next_fanout_ge6",
)
COUNTERS = ("queries", "cti", "mic", "push", "pdr_depth", "encoded_gate_clauses")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", nargs="+", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--timeout-multiplier", type=float, default=1.5)
    parser.add_argument("--min-gap", type=float, default=2.0)
    parser.add_argument("--buckets", nargs="+", default=list(BUCKETS))
    return parser.parse_args()


def number(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def measured(row: dict[str, str], config: str, penalty: float) -> tuple[float, bool]:
    status = row.get(f"{config}_status", "")
    solved = status in SOLVED
    return (number(row.get(f"{config}_wall_seconds", ""), penalty) if solved else penalty), solved


def ratio(rows: list[dict], numerator: str, denominator: str, field: str) -> str:
    pairs = []
    for item in rows:
        row = item["row"]
        left = row.get(f"{numerator}_{field}", "")
        right = row.get(f"{denominator}_{field}", "")
        if left != "" and right != "" and number(right) > 0:
            pairs.append(number(left) / number(right))
    return "" if not pairs else f"{sum(pairs) / len(pairs):.6f}"


def summarize(items: list[dict], bucket: str, scope: str) -> dict:
    only = f"xag_only_{bucket}"
    except_id = f"xag_except_{bucket}"
    add_base = sum(item["costs"]["aig"] for item in items)
    add_candidate = sum(item["costs"][only] for item in items)
    retain_base = sum(item["costs"][except_id] for item in items)
    retain_candidate = sum(item["costs"]["xag_all"] for item in items)
    gap = items[0]["min_gap"] if items else 2.0
    add_effects = [item["costs"]["aig"] - item["costs"][only] for item in items]
    retain_effects = [item["costs"][except_id] - item["costs"]["xag_all"] for item in items]
    beneficial = harmful = conflicting = inconclusive = 0
    for add, retain in zip(add_effects, retain_effects):
        if add > gap and retain > gap:
            beneficial += 1
        elif add < -gap and retain < -gap:
            harmful += 1
        elif (add > gap and retain < -gap) or (add < -gap and retain > gap):
            conflicting += 1
        else:
            inconclusive += 1
    result = {
        "scope": scope,
        "bucket": bucket,
        "samples": len(items),
        "add_gain_percent": f"{100.0 * (add_base - add_candidate) / add_base:.6f}" if add_base else "",
        "retain_gain_percent": f"{100.0 * (retain_base - retain_candidate) / retain_base:.6f}" if retain_base else "",
        "add_solved_delta": sum(item["solved"][only] - item["solved"]["aig"] for item in items),
        "retain_solved_delta": sum(item["solved"]["xag_all"] - item["solved"][except_id] for item in items),
        "add_wins": sum(effect > gap for effect in add_effects),
        "add_losses": sum(effect < -gap for effect in add_effects),
        "retain_wins": sum(effect > gap for effect in retain_effects),
        "retain_losses": sum(effect < -gap for effect in retain_effects),
        "both_beneficial": beneficial,
        "both_harmful": harmful,
        "conflicting": conflicting,
        "inconclusive": inconclusive,
    }
    for field in COUNTERS:
        result[f"only_over_aig_{field}"] = ratio(items, only, "aig", field)
        result[f"all_over_except_{field}"] = ratio(items, "xag_all", except_id, field)
    return result


def write_tsv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    configs = ["aig", "xag_all"]
    for bucket in args.buckets:
        configs.extend((f"xag_only_{bucket}", f"xag_except_{bucket}"))
    samples = []
    for path in args.results:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                penalty = number(row.get("timeout_seconds", "120"), 120.0) * args.timeout_multiplier
                costs = {}
                solved = {}
                for config in configs:
                    costs[config], solved[config] = measured(row, config, penalty)
                if max(costs.values()) - min(costs.values()) <= args.min_gap:
                    continue
                samples.append({
                    "year": row.get("year", ""),
                    "name": row["name"],
                    "row": row,
                    "costs": costs,
                    "solved": solved,
                    "min_gap": args.min_gap,
                })
    rows = []
    for scope, items in [("all", samples)]:
        rows.extend(summarize(items, bucket, scope) for bucket in args.buckets)
    by_year = defaultdict(list)
    for item in samples:
        by_year[item["year"]].append(item)
    for year in sorted(by_year):
        rows.extend(summarize(by_year[year], bucket, year) for bucket in args.buckets)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_tsv(args.output_dir / "bucket_causal_summary.tsv", rows)

    details = []
    for item in samples:
        for bucket in args.buckets:
            only = f"xag_only_{bucket}"
            except_id = f"xag_except_{bucket}"
            details.append({
                "year": item["year"],
                "name": item["name"],
                "bucket": bucket,
                "aig_cost": f"{item['costs']['aig']:.6f}",
                "only_cost": f"{item['costs'][only]:.6f}",
                "add_effect_seconds": f"{item['costs']['aig'] - item['costs'][only]:.6f}",
                "except_cost": f"{item['costs'][except_id]:.6f}",
                "all_cost": f"{item['costs']['xag_all']:.6f}",
                "retain_effect_seconds": f"{item['costs'][except_id] - item['costs']['xag_all']:.6f}",
            })
    write_tsv(args.output_dir / "bucket_case_details.tsv", details)

    report = [
        "# XOR Bucket Causal Contrasts",
        "",
        f"- Informative circuits: {len(samples)}",
        f"- Timeout cost: {args.timeout_multiplier:g}x per-run limit",
        f"- Meaningful pairwise gap: {args.min_gap:g}s",
        "",
        "Positive Add means `only(B)` beats AIG. Positive Retain means full XAG beats `except(B)`.",
        "",
        "| Bucket | Add | Retain | Add W/L | Retain W/L | Both good/harm/conflict/neutral |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows[:len(args.buckets)]:
        report.append(
            f"| {row['bucket']} | {row['add_gain_percent']}% | {row['retain_gain_percent']}% | "
            f"{row['add_wins']}/{row['add_losses']} | {row['retain_wins']}/{row['retain_losses']} | "
            f"{row['both_beneficial']}/{row['both_harmful']}/{row['conflicting']}/{row['inconclusive']} |"
        )
    (args.output_dir / "causal_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"samples={len(samples)} buckets={len(args.buckets)} output={args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
