#!/usr/bin/env python3
"""Analyze complete AIG/XAG pairs from a running full-year campaign."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}
CONFIGS = ("aig_native", "xag_native")


def cost(row: dict[str, str], penalty_factor: float) -> float:
    if row["status"] in SOLVED:
        return float(row["wall_seconds"])
    return penalty_factor * float(row["timeout_seconds"])


def summarize(pairs: list[dict[str, dict[str, str]]], penalty_factor: float) -> dict[str, object]:
    eligible = [pair for pair in pairs if any(pair[c]["status"] in SOLVED for c in CONFIGS)]
    jointly = [pair for pair in pairs if all(pair[c]["status"] in SOLVED for c in CONFIGS)]
    aig_only = sum(pair["aig_native"]["status"] in SOLVED and pair["xag_native"]["status"] not in SOLVED for pair in pairs)
    xag_only = sum(pair["xag_native"]["status"] in SOLVED and pair["aig_native"]["status"] not in SOLVED for pair in pairs)
    totals = {
        config: sum(cost(pair[config], penalty_factor) for pair in eligible)
        for config in CONFIGS
    }
    joint_totals = {
        config: sum(float(pair[config]["wall_seconds"]) for pair in jointly)
        for config in CONFIGS
    }
    wins = Counter()
    meaningful = Counter()
    meaningful_pairs = []
    for pair in eligible:
        values = {config: cost(pair[config], penalty_factor) for config in CONFIGS}
        winner = min(values, key=values.get)
        wins[winner] += 1
        if abs(values["aig_native"] - values["xag_native"]) > 2.0:
            meaningful[winner] += 1
            meaningful_pairs.append(pair)
    meaningful_totals = {
        config: sum(cost(pair[config], penalty_factor) for pair in meaningful_pairs)
        for config in CONFIGS
    }
    ratios = [
        float(pair["aig_native"]["wall_seconds"]) / float(pair["xag_native"]["wall_seconds"])
        for pair in jointly
        if float(pair["aig_native"]["wall_seconds"]) > 0
        and float(pair["xag_native"]["wall_seconds"]) > 0
    ]
    return {
        "pairs": len(pairs), "eligible": len(eligible), "jointly": len(jointly),
        "aig_only": aig_only, "xag_only": xag_only, "totals": totals,
        "joint_totals": joint_totals, "wins": wins, "meaningful": meaningful,
        "meaningful_count": len(meaningful_pairs), "meaningful_totals": meaningful_totals,
        "median_ratio": statistics.median(ratios) if ratios else math.nan,
        "geomean_ratio": math.exp(sum(math.log(ratio) for ratio in ratios) / len(ratios)) if ratios else math.nan,
    }


def reduction(aig: float, xag: float) -> float:
    return 100.0 * (aig - xag) / aig if aig else math.nan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout-penalty", type=float, default=1.5)
    args = parser.parse_args()

    with args.input.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    indexed: dict[tuple[str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    duplicate_cells = 0
    for row in rows:
        key = (row["model_id"], row["run"])
        if row["config"] in indexed[key]:
            duplicate_cells += 1
        indexed[key][row["config"]] = row
    pairs = [case for case in indexed.values() if all(config in case for config in CONFIGS)]
    incomplete = sum(not all(config in case for config in CONFIGS) for case in indexed.values())
    conflicts = sum(
        len({pair[config]["status"] for config in CONFIGS if pair[config]["status"] in SOLVED}) > 1
        for pair in pairs
    )
    overall = summarize(pairs, args.timeout_penalty)

    total_models = None
    manifest_counts: Counter[tuple[str, str]] = Counter()
    if args.manifest:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        total_models = len(manifest["models"])
        manifest_counts.update((str(model["year"]), str(model["tier"])) for model in manifest["models"])

    expected = f"/{total_models}" if total_models is not None else ""
    lines = [
        "# Full AIG / XAG Running Report", "",
        f"Rows read: {len(rows)}; complete pairs: {len(pairs)}{expected}; incomplete pairs: {incomplete}; "
        f"duplicate cells: {duplicate_cells}; solved-outcome conflicts: {conflicts}.",
        f"Timeout penalty: {args.timeout_penalty:.2f}x; meaningful gap threshold: 2 seconds.", "",
        "## Overall Complete Pairs", "",
        "| Measure | AIG | XAG | XAG reduction / note |", "|---|---:|---:|---:|",
        f"| Solved among complete pairs | {overall['jointly'] + overall['aig_only']} | "
        f"{overall['jointly'] + overall['xag_only']} | jointly {overall['jointly']}, "
        f"AIG-only {overall['aig_only']}, XAG-only {overall['xag_only']} |",
        f"| Penalized total over {overall['eligible']} non-both-timeout pairs (s) | "
        f"{overall['totals']['aig_native']:.2f} | {overall['totals']['xag_native']:.2f} | "
        f"{reduction(overall['totals']['aig_native'], overall['totals']['xag_native']):+.2f}% |",
        f"| Jointly solved total (s) | {overall['joint_totals']['aig_native']:.2f} | "
        f"{overall['joint_totals']['xag_native']:.2f} | "
        f"{reduction(overall['joint_totals']['aig_native'], overall['joint_totals']['xag_native']):+.2f}% |",
        f"| Wins | {overall['wins']['aig_native']} | {overall['wins']['xag_native']} | all eligible pairs |",
        f"| Wins with >2s gap | {overall['meaningful']['aig_native']} | "
        f"{overall['meaningful']['xag_native']} | {overall['meaningful_count']} pairs |",
        f"| >2s-gap penalized total (s) | {overall['meaningful_totals']['aig_native']:.2f} | "
        f"{overall['meaningful_totals']['xag_native']:.2f} | "
        f"{reduction(overall['meaningful_totals']['aig_native'], overall['meaningful_totals']['xag_native']):+.2f}% |",
        f"| Jointly solved typical AIG/XAG ratio | {overall['median_ratio']:.3f} median | "
        f"{overall['geomean_ratio']:.3f} geomean | >1 favors XAG |", "",
    ]

    def emit_strata(title: str, field: str, order: list[str]) -> None:
        lines.extend([
            f"## {title}", "",
            "| Group | Complete / manifest | Retained | Joint | AIG/XAG only | AIG/XAG wins >2s | AIG s | XAG s | XAG reduction |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for value in order:
            subset = [pair for pair in pairs if pair["aig_native"][field] == value]
            if not subset:
                continue
            result = summarize(subset, args.timeout_penalty)
            manifest_total = ""
            if field == "year" and total_models is not None:
                manifest_total = str(sum(count for (year, _), count in manifest_counts.items() if year == value))
            elif field == "tier" and total_models is not None:
                manifest_total = str(sum(count for (_, tier), count in manifest_counts.items() if tier == value))
            denominator = f"/{manifest_total}" if manifest_total else ""
            lines.append(
                f"| {value} | {result['pairs']}{denominator} | {result['eligible']} | "
                f"{result['jointly']} | {result['aig_only']}/{result['xag_only']} | "
                f"{result['meaningful']['aig_native']}/{result['meaningful']['xag_native']} | "
                f"{result['totals']['aig_native']:.2f} | {result['totals']['xag_native']:.2f} | "
                f"{reduction(result['totals']['aig_native'], result['totals']['xag_native']):+.2f}% |"
            )
        lines.append("")

    emit_strata("By Year", "year", ["2015", "2017", "2019", "2020", "2024", "2025"])
    emit_strata("By Historical Tier", "tier", ["trivial", "fast", "medium", "slow", "timeout", "error"])

    eligible_pairs = [pair for pair in pairs if any(pair[c]["status"] in SOLVED for c in CONFIGS)]
    contributions = sorted(
        ((
            cost(pair["aig_native"], args.timeout_penalty)
            - cost(pair["xag_native"], args.timeout_penalty),
            pair,
        ) for pair in eligible_pairs),
        key=lambda item: (item[0], item[1]["aig_native"]["model_id"]),
    )
    gains = list(reversed(contributions[-10:]))
    losses = contributions[:10]
    lines.extend([
        "## Largest Pair Contributions", "",
        "Positive seconds favor XAG; timeout/error costs 1.5 times the per-run timeout.", "",
        "| XAG gains | Year | Tier | AIG/XAG status | Seconds | XAG losses | Year | Tier | AIG/XAG status | Seconds |",
        "|---|---:|---|---|---:|---|---:|---|---|---:|",
    ])
    for (gain, gain_pair), (loss, loss_pair) in zip(gains, losses):
        gain_aig = gain_pair["aig_native"]
        gain_xag = gain_pair["xag_native"]
        loss_aig = loss_pair["aig_native"]
        loss_xag = loss_pair["xag_native"]
        lines.append(
            f"| {gain_aig['model_id']} | {gain_aig['year']} | {gain_aig['tier']} | "
            f"{gain_aig['status']}/{gain_xag['status']} | {gain:+.2f} | "
            f"{loss_aig['model_id']} | {loss_aig['year']} | {loss_aig['tier']} | "
            f"{loss_aig['status']}/{loss_xag['status']} | {loss:+.2f} |"
        )

    lines.extend(["", "## One-Sided Solves", ""])
    one_sided = [
        pair for pair in pairs
        if (pair["aig_native"]["status"] in SOLVED) != (pair["xag_native"]["status"] in SOLVED)
    ]
    if not one_sided:
        lines.append("None.")
    else:
        lines.extend([
            "| Model | Year | Tier | AIG status/time | XAG status/time |",
            "|---|---:|---|---|---|",
        ])
        for pair in one_sided:
            aig = pair["aig_native"]
            xag = pair["xag_native"]
            lines.append(
                f"| {aig['model_id']} | {aig['year']} | {aig['tier']} | "
                f"{aig['status']} {float(aig['wall_seconds']):.2f}s | "
                f"{xag['status']} {float(xag['wall_seconds']):.2f}s |"
            )
    lines.append("")

    lines.extend(["## Status Counts", ""])
    for config in CONFIGS:
        lines.append(f"- {config}: {dict(Counter(row['status'] for row in rows if row['config'] == config))}")
    report = "\n".join(lines) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
