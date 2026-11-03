#!/usr/bin/env python3
"""Summarize first-get-pre phase interventions against the default policy."""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def solved(row: dict[str, str]) -> bool:
    return row["status"] in {"SAFE", "UNSAFE"}


def portfolio_score(
    rep: str,
    models: list[str],
    selected: list[str],
    cells: dict[tuple[str, str, str], dict[str, str]],
) -> tuple[int, float]:
    solved_count = 0
    penalized = 0.0
    for model in models:
        rows = [cells[(rep, model, strategy)] for strategy in selected]
        winners = [float(row["wall_seconds"]) for row in rows if solved(row)]
        if winners:
            solved_count += 1
            penalized += min(winners)
        else:
            penalized += 1.5 * float(rows[0]["timeout_seconds"])
    return solved_count, penalized


def greedy_portfolio(
    rep: str,
    models: list[str],
    strategies: list[str],
    cells: dict[tuple[str, str, str], dict[str, str]],
    lanes: int,
) -> tuple[list[str], tuple[int, float]]:
    selected = ["default"]
    while len(selected) < lanes:
        candidates = [strategy for strategy in strategies if strategy not in selected]
        selected.append(max(
            candidates,
            key=lambda strategy: (
                portfolio_score(rep, models, selected + [strategy], cells)[0],
                -portfolio_score(rep, models, selected + [strategy], cells)[1],
            ),
        ))
    return selected, portfolio_score(rep, models, selected, cells)


def main() -> int:
    args = parse_args()
    rows = list(csv.DictReader(args.input.open(encoding="utf-8"), delimiter="\t"))
    cells = {(r["representation"], r["model_id"], r["strategy"]): r for r in rows}
    lines = ["# First get-pre model intervention", "", f"Rows: {len(rows)}.", ""]
    for rep in ("aig", "xag"):
        rr = [r for r in rows if r["representation"] == rep]
        models = sorted({r["model_id"] for r in rr})
        strategies = ["default", "zero", "one", "init"] + sorted(
            {r["strategy"] for r in rr if r["strategy"].startswith("random-")},
            key=lambda value: int(value.split("-")[1]),
        )
        lines += [f"## {rep.upper()}", "", "| Strategy | Solved | vs default +solves | Wins >2s | Losses >2s | Target changed | Penalized delta |", "|---|---:|---:|---:|---:|---:|---:|"]
        base_solved = sum(solved(cells[(rep, model, "default")]) for model in models if (rep, model, "default") in cells)
        for strategy in strategies:
            available = [m for m in models if (rep, m, "default") in cells and (rep, m, strategy) in cells]
            wins = losses = changed = compared_hash = 0
            base_cost = treatment_cost = 0.0
            cost_models = 0
            solved_count = sum(solved(cells[(rep, m, strategy)]) for m in available)
            for model in available:
                base = cells[(rep, model, "default")]
                treatment = cells[(rep, model, strategy)]
                bs, ts = solved(base), solved(treatment)
                if bs or ts:
                    timeout = 1.5 * float(base["timeout_seconds"])
                    base_cost += float(base["wall_seconds"]) if bs else timeout
                    treatment_cost += float(treatment["wall_seconds"]) if ts else timeout
                    cost_models += 1
                if bs and ts:
                    delta = float(base["wall_seconds"]) - float(treatment["wall_seconds"])
                    if delta > 2: wins += 1
                    elif delta < -2: losses += 1
                elif ts: wins += 1
                elif bs: losses += 1
                if base["first_target_hash"] and treatment["first_target_hash"]:
                    compared_hash += 1
                    changed += base["first_target_hash"] != treatment["first_target_hash"]
            target = f"{changed}/{compared_hash}" if compared_hash else "-"
            delta = (base_cost - treatment_cost) / base_cost * 100 if base_cost else 0.0
            lines.append(f"| {strategy} | {solved_count}/{len(available)} | {solved_count-base_solved:+d} | {wins} | {losses} | {target} | {delta:+.1f}% |")

        randoms = [s for s in strategies if s.startswith("random-")]
        distinct = []
        for model in models:
            hashes = {cells[(rep, model, s)]["first_target_hash"] for s in randoms if (rep, model, s) in cells and cells[(rep, model, s)]["first_target_hash"]}
            if hashes:
                distinct.append(len(hashes))
        if distinct:
            lines += ["", f"Random phase seeds produced a median of {statistics.median(distinct):.1f} distinct first target models per circuit (max {max(distinct)}).", ""]

        complete = [
            model for model in models
            if all((rep, model, strategy) in cells for strategy in strategies)
        ]
        if complete:
            baseline_solved, baseline_cost = portfolio_score(
                rep, complete, ["default"], cells
            )
            hard_recovered = [
                model for model in complete
                if not solved(cells[(rep, model, "default")])
                and any(solved(cells[(rep, model, strategy)]) for strategy in strategies[1:])
            ]
            lines += [
                "### Coverage objective", "",
                f"Default solved {baseline_solved}/{len(complete)}. Any first-model policy "
                f"solves {baseline_solved + len(hard_recovered)}/{len(complete)}, recovering "
                f"{len(hard_recovered)} default timeouts.", "",
                "| Fixed lanes | Strategies | Solved | Extra solves | Penalized delta |",
                "|---:|---|---:|---:|---:|",
            ]
            for lanes in (2, 4):
                selected, (count, cost) = greedy_portfolio(
                    rep, complete, strategies, cells, lanes
                )
                delta = (baseline_cost - cost) / baseline_cost * 100 if baseline_cost else 0.0
                lines.append(
                    f"| {lanes} | {', '.join(selected)} | {count}/{len(complete)} | "
                    f"{count-baseline_solved:+d} | {delta:+.1f}% |"
                )
            if hard_recovered:
                lines += ["", "Recovered model IDs: " + ", ".join(hard_recovered), ""]

    outcomes = defaultdict(set)
    for row in rows:
        if solved(row):
            outcomes[(row["representation"], row["model_id"])].add(row["status"])
    conflicts = [key for key, values in outcomes.items() if len(values) > 1]
    lines += ["## Correctness", "", f"Outcome conflicts: {len(conflicts)}.", ""]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"rows={len(rows)} conflicts={len(conflicts)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
