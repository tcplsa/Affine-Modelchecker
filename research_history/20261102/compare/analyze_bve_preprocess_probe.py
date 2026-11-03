#!/usr/bin/env python3
"""Summarize PDR-free BVE probes and test simple role-selection rules."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path


ORDERS = ("legacy", "low", "high", "sum_low", "sum_high")
PROBE_PREFIX = {order: f"xag_probe_lift_{order}" for order in ORDERS}
REFERENCE = "xag_observe_legacy4"
CANDIDATE = "xag_observe_role4"
VALID = {"SAFE", "UNSAFE"}

METRICS = (
    ("lift_bve_attempted", "BVE attempts"),
    ("lift_bve_eliminated", "variables eliminated"),
    ("lift_bve_rejected_growth", "growth rejections"),
    ("lift_bve_rejected_clause_limit", "clause-limit rejections"),
    ("lift_bve_removed_clauses", "clauses removed"),
    ("lift_bve_resolvents", "resolvents"),
    ("lift_bve_resolvent_literals", "resolvent literals"),
    ("lift_bve_merge_checks", "merge checks"),
    ("lift_simplified_clauses", "output clauses"),
    ("lift_simplified_literals", "output literals"),
    ("lift_binary_clauses", "binary clauses"),
    ("lift_ternary_clauses", "ternary clauses"),
    ("lift_long_clauses", "long clauses"),
    ("lift_max_clause_size", "maximum clause size"),
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--role-results", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--penalty", type=float, default=1.5)
    return parser.parse_args()


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def number(row: dict[str, str], config: str, field: str) -> float | None:
    try:
        return float(row[f"{config}_{field}"])
    except (KeyError, ValueError):
        return None


def geo(values: list[float]) -> float:
    positive = [value for value in values if value > 0 and math.isfinite(value)]
    return math.exp(statistics.mean(map(math.log, positive))) if positive else math.nan


def fmt(value: float) -> str:
    return "-" if math.isnan(value) else f"{value:.3f}"


def solved(row: dict[str, str], config: str) -> bool:
    return row.get(f"{config}_status") in VALID


def cost(row: dict[str, str], config: str, timeout: float, penalty: float) -> float:
    if solved(row, config):
        value = number(row, config, "wall_seconds")
        if value is not None:
            return value
    return penalty * timeout


def probe_table(lines: list[str], rows: list[dict[str, str]]) -> None:
    lines += [
        "", "## Structural effect", "",
        "Ratios are relative to legacy order. `Lower/equal/higher` counts compare each "
        "candidate with legacy on the same model.", "",
        "| Order | Observable | Geo ratio | Lower/equal/higher |",
        "|---|---|---:|---:|",
    ]
    for order in ORDERS[1:]:
        for field, label in METRICS:
            ratios: list[float] = []
            lower = equal = higher = 0
            for row in rows:
                candidate = number(row, PROBE_PREFIX[order], field)
                reference = number(row, PROBE_PREFIX["legacy"], field)
                if candidate is None or reference is None:
                    continue
                if candidate < reference:
                    lower += 1
                elif candidate > reference:
                    higher += 1
                else:
                    equal += 1
                if candidate > 0 and reference > 0:
                    ratios.append(candidate / reference)
            lines.append(
                f"| {order.replace('_', '-')} | {label} | {fmt(geo(ratios))} | "
                f"{lower}/{equal}/{higher} |"
            )


def selection_table(
    lines: list[str], probe_rows: dict[str, dict[str, str]], role_rows: list[dict[str, str]],
    timeout: float, penalty: float,
) -> None:
    usable = [row for row in role_rows if row.get("model_id") in probe_rows]
    legacy_solved = sum(solved(row, REFERENCE) for row in usable)
    candidate_solved = sum(solved(row, CANDIDATE) for row in usable)
    union = sum(solved(row, REFERENCE) or solved(row, CANDIDATE) for row in usable)
    legacy_cost = sum(cost(row, REFERENCE, timeout, penalty) for row in usable)
    candidate_cost = sum(cost(row, CANDIDATE, timeout, penalty) for row in usable)

    lines += [
        "", "## Cheap selector diagnostic", "",
        f"Joined fair PDR observations: {len(usable)}. Solved legacy/sum-high/union: "
        f"{legacy_solved}/{candidate_solved}/{union}.", "",
        "Each rule chooses sum-high only when its PDR-free probe has a smaller value "
        "than legacy; ties fall back to legacy. This is an in-sample diagnostic, not a "
        "validated classifier.", "",
        "| Probe rule: choose sum-high if lower | Sum-high picks | Solved | "
        "Penalty cost vs legacy/sum-high | W/L >2s against unselected |",
        "|---|---:|---:|---:|---:|",
    ]
    ranked = []
    for field, label in METRICS:
        choices = []
        for row in usable:
            probe = probe_rows[row["model_id"]]
            candidate = number(probe, PROBE_PREFIX["sum_high"], field)
            reference = number(probe, PROBE_PREFIX["legacy"], field)
            use_candidate = (
                candidate is not None and reference is not None and candidate < reference
            )
            choices.append(CANDIDATE if use_candidate else REFERENCE)
        selected_cost = sum(
            cost(row, choice, timeout, penalty) for row, choice in zip(usable, choices)
        )
        selected_solved = sum(solved(row, choice) for row, choice in zip(usable, choices))
        wins = losses = 0
        for row, choice in zip(usable, choices):
            other = REFERENCE if choice == CANDIDATE else CANDIDATE
            if not (solved(row, choice) and solved(row, other)):
                continue
            chosen_time = number(row, choice, "wall_seconds")
            other_time = number(row, other, "wall_seconds")
            if chosen_time is None or other_time is None:
                continue
            if chosen_time + 2 < other_time:
                wins += 1
            elif other_time + 2 < chosen_time:
                losses += 1
        ranked.append((
            selected_cost, label, sum(choice == CANDIDATE for choice in choices),
            selected_solved, selected_cost / legacy_cost, selected_cost / candidate_cost,
            wins, losses,
        ))
    for _cost, label, picks, count, vs_legacy, vs_candidate, wins, losses in sorted(ranked):
        lines.append(
            f"| {label} | {picks} | {count} | {vs_legacy:.3f}/{vs_candidate:.3f} | "
            f"{wins}/{losses} |"
        )

    discordant = [
        row for row in usable if solved(row, REFERENCE) != solved(row, CANDIDATE)
    ]
    lines += [
        "", "### Outcome-discordant probe signatures", "",
        "| Model | Solved side | Output clauses legacy/sum-high | "
        "Long clauses legacy/sum-high | Resolvents legacy/sum-high |",
        "|---|---|---:|---:|---:|",
    ]
    for row in discordant:
        probe = probe_rows[row["model_id"]]
        side = "sum-high" if solved(row, CANDIDATE) else "legacy"

        def pair(field: str) -> str:
            left = number(probe, PROBE_PREFIX["legacy"], field)
            right = number(probe, PROBE_PREFIX["sum_high"], field)
            if left is None or right is None:
                return "-"
            return f"{left:.0f}/{right:.0f}"

        lines.append(
            f"| {row['model_id']} | {side} | {pair('lift_simplified_clauses')} | "
            f"{pair('lift_long_clauses')} | {pair('lift_bve_resolvents')} |"
        )


def main() -> int:
    args = arguments()
    raw_probe = read(args.probe)
    valid_probe = [
        row for row in raw_probe
        if all(row.get(f"{PROBE_PREFIX[order]}_status") == "UNKNOWN" for order in ORDERS)
    ]
    error_count = len(raw_probe) - len(valid_probe)
    lines = [
        "# PDR-free BVE preprocessing probe", "",
        f"Rows: {len(raw_probe)}; complete structural probes: {len(valid_probe)}; "
        f"rows with at least one failed configuration: {error_count}.",
    ]
    probe_table(lines, valid_probe)
    if args.role_results:
        selection_table(
            lines, {row["model_id"]: row for row in valid_probe}, read(args.role_results),
            args.timeout, args.penalty,
        )
    lines += [
        "", "## Interpretation", "",
        "High-first and sum-high usually reduce BVE cross-product work (resolvents and "
        "merge checks), but they redistribute the residual CNF toward more binary clauses "
        "and can increase total literals. Therefore no single size counter is a sufficient "
        "objective; the selector must be validated against downstream PDR behavior.",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows={len(raw_probe)} valid={len(valid_probe)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
