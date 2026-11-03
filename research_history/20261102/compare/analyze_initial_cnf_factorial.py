#!/usr/bin/env python3
"""Analyze the deterministic input-order / initial-CNF factorial experiment."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}
ORDERS = ("original", "fanout-asc", "fanout-desc", "bad-last")
REPRESENTATIONS = ("aig", "xag")
REGIMES = ("native", "raw", "precanonical")


def read_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        requested_order = next(
            (order for order in ORDERS if f"results_{order}.tsv" == path.name), None
        )
        if requested_order is None:
            raise ValueError(f"cannot infer requested input order from {path}")
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                row["_design_order"] = requested_order
                rows.append(row)
    return rows


def cost(row: dict[str, str], penalty_factor: float) -> float:
    if row["status"] in SOLVED:
        return float(row["wall_seconds"])
    return penalty_factor * float(row["timeout_seconds"])


def pct_reduction(reference: float, candidate: float) -> float:
    return 100.0 * (reference - candidate) / reference if reference else math.nan


def summarize_orders(
    rows: list[dict[str, str]], representation: str, regime: str, penalty: float
) -> dict[str, object]:
    cases: dict[tuple[str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        if row["representation"] == representation and row["regime"] == regime:
            cases[(row["model_id"], row["run"])][row["_design_order"]] = row
    complete = [case for case in cases.values() if all(order in case for order in ORDERS)]
    eligible = [case for case in complete if any(case[o]["status"] in SOLVED for o in ORDERS)]
    totals = {o: sum(cost(case[o], penalty) for case in eligible) for o in ORDERS}
    solved = {o: sum(case[o]["status"] in SOLVED for case in complete) for o in ORDERS}
    wins = Counter()
    meaningful = Counter()
    for case in eligible:
        values = {o: cost(case[o], penalty) for o in ORDERS}
        best_value = min(values.values())
        winners = [o for o, value in values.items() if value == best_value]
        if len(winners) == 1:
            wins[winners[0]] += 1
            if max(values.values()) - best_value > 2.0:
                meaningful[winners[0]] += 1
    return {
        "complete": len(complete),
        "eligible": len(eligible),
        "totals": totals,
        "solved": solved,
        "wins": wins,
        "meaningful": meaningful,
    }


def summarize_representation(
    rows: list[dict[str, str]], regime: str, order: str, penalty: float
) -> dict[str, object]:
    cases: dict[tuple[str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        if row["regime"] == regime and row["_design_order"] == order:
            cases[(row["model_id"], row["run"])][row["representation"]] = row
    complete = [case for case in cases.values() if all(rep in case for rep in REPRESENTATIONS)]
    eligible = [case for case in complete if any(case[r]["status"] in SOLVED for r in REPRESENTATIONS)]
    totals = {r: sum(cost(case[r], penalty) for case in eligible) for r in REPRESENTATIONS}
    solved = {r: sum(case[r]["status"] in SOLVED for case in complete) for r in REPRESENTATIONS}
    wins = Counter()
    meaningful = Counter()
    for case in eligible:
        values = {r: cost(case[r], penalty) for r in REPRESENTATIONS}
        winner = min(values, key=values.get)
        wins[winner] += 1
        if abs(values["aig"] - values["xag"]) > 2.0:
            meaningful[winner] += 1
    return {
        "complete": len(complete),
        "eligible": len(eligible),
        "totals": totals,
        "solved": solved,
        "wins": wins,
        "meaningful": meaningful,
    }


def stable_against_original(
    rows: list[dict[str, str]], representation: str, regime: str, order: str, penalty: float
) -> tuple[int, int, int, int, int]:
    by_model: dict[str, dict[str, dict[str, dict[str, str]]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for row in rows:
        if row["representation"] == representation and row["regime"] == regime:
            by_model[row["model_id"]][row["run"]][row["_design_order"]] = row
    comparable = informative = better = worse = mixed = 0
    for runs in by_model.values():
        deltas = []
        for run in ("1", "2"):
            if run not in runs or "original" not in runs[run] or order not in runs[run]:
                break
            original = cost(runs[run]["original"], penalty)
            candidate = cost(runs[run][order], penalty)
            deltas.append(original - candidate)
        if len(deltas) != 2:
            continue
        comparable += 1
        comparison_rows = [
            runs[run][candidate_order]
            for run in ("1", "2")
            for candidate_order in ("original", order)
        ]
        if not any(row["status"] in SOLVED for row in comparison_rows):
            continue
        informative += 1
        if all(delta > 2.0 for delta in deltas):
            better += 1
        elif all(delta < -2.0 for delta in deltas):
            worse += 1
        else:
            mixed += 1
    return comparable, informative, better, worse, mixed


def global_config_ranking(rows: list[dict[str, str]], penalty: float) -> tuple[int, list[tuple[str, int, float]]]:
    cases: dict[tuple[str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    configs = [
        f"{representation}_{regime}_{order}"
        for representation in REPRESENTATIONS
        for regime in REGIMES
        for order in ORDERS
    ]
    for row in rows:
        config = f"{row['representation']}_{row['regime']}_{row['_design_order']}"
        cases[(row["model_id"], row["run"])][config] = row
    complete = [case for case in cases.values() if all(config in case for config in configs)]
    eligible = [
        case for case in complete
        if any(case[config]["status"] in SOLVED for config in configs)
    ]
    ranking = []
    for config in configs:
        solved = sum(case[config]["status"] in SOLVED for case in complete)
        total = sum(cost(case[config], penalty) for case in eligible)
        ranking.append((config, solved, total))
    ranking.sort(key=lambda item: item[2])
    return len(eligible), ranking


def cnf_count_invariance(
    rows: list[dict[str, str]], representation: str, regime: str
) -> tuple[int, int, int]:
    raw_fields = (
        "translation_raw_vars", "translation_raw_clauses",
        "structural_gate_vars", "structural_gate_clauses",
    )
    simplified_fields = (
        "translation_simplified_vars", "translation_simplified_clauses",
        "translation_simplified_literals",
    )
    cases: dict[tuple[str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        if row["representation"] == representation and row["regime"] == regime:
            cases[(row["model_id"], row["run"])][row["_design_order"]] = row
    complete = 0
    raw_equal = 0
    simplified_equal = 0
    for case in cases.values():
        if not all(order in case for order in ORDERS):
            continue
        if not all(
            case[order].get(field, "") != ""
            for order in ORDERS for field in raw_fields + simplified_fields
        ):
            continue
        complete += 1
        raw_equal += len({tuple(case[o][f] for f in raw_fields) for o in ORDERS}) == 1
        simplified_equal += len({tuple(case[o][f] for f in simplified_fields) for o in ORDERS}) == 1
    return complete, raw_equal, simplified_equal


def selected_pair_details(
    rows: list[dict[str, str]], reference: str, candidate: str, penalty: float
) -> tuple[int, int, list[tuple[float, str, str, str]], list[tuple[float, str, str, str]]]:
    indexed: dict[tuple[str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    metadata: dict[str, tuple[str, str]] = {}
    for row in rows:
        config = f"{row['representation']}_{row['regime']}_{row['_design_order']}"
        indexed[(row["model_id"], row["run"])][config] = row
        metadata[row["model_id"]] = (row["year"], row["tier"])
    candidate_only = reference_only = 0
    by_model: dict[str, float] = defaultdict(float)
    informative: set[str] = set()
    for (model_id, _run), case in indexed.items():
        if reference not in case or candidate not in case:
            continue
        ref_solved = case[reference]["status"] in SOLVED
        cand_solved = case[candidate]["status"] in SOLVED
        candidate_only += cand_solved and not ref_solved
        reference_only += ref_solved and not cand_solved
        if ref_solved or cand_solved:
            informative.add(model_id)
            by_model[model_id] += cost(case[reference], penalty) - cost(case[candidate], penalty)
    details = [
        (delta, model_id, metadata[model_id][0], metadata[model_id][1])
        for model_id, delta in by_model.items() if model_id in informative
    ]
    gains = sorted(details, reverse=True)[:8]
    losses = sorted(details)[:8]
    return candidate_only, reference_only, gains, losses


def median_number(rows: list[dict[str, str]], field: str) -> float:
    values = [float(row[field]) for row in rows if row.get(field, "") != ""]
    return statistics.median(values) if values else math.nan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout-penalty", type=float, default=1.5)
    args = parser.parse_args()

    rows = read_rows(args.inputs)
    keys = [
        (row["model_id"], row["run"], row["representation"], row["regime"], row["_design_order"])
        for row in rows
    ]
    outcomes: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        if row["status"] in SOLVED:
            outcomes[(row["model_id"], row["run"])].add(row["status"])
    conflicts = sum(len(values) > 1 for values in outcomes.values())
    models = {row["model_id"] for row in rows}

    lines = [
        "# Initial CNF / Input Order Factorial Report",
        "",
        f"Rows: {len(rows)}; models: {len(models)}; duplicate cells: {len(keys) - len(set(keys))}; "
        f"solved-outcome conflicts: {conflicts}; timeout penalty: {args.timeout_penalty:.2f}x.",
        "",
        "All-timeout cases are excluded within each comparison. Wins marked >2s require the "
        "fastest/slowest penalized-cost gap to exceed two seconds.",
        "",
        "## Input Order Within Each Representation / CNF Regime",
        "",
        "| Representation | Regime | Cases | Order | Solved | Penalized s | Reduction vs original | Wins | Wins >2s |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    order_summaries: dict[tuple[str, str], dict[str, object]] = {}
    for representation in REPRESENTATIONS:
        for regime in REGIMES:
            summary = summarize_orders(rows, representation, regime, args.timeout_penalty)
            order_summaries[(representation, regime)] = summary
            original = summary["totals"]["original"]
            for order in ORDERS:
                lines.append(
                    f"| {representation} | {regime} | {summary['eligible']}/{summary['complete']} | "
                    f"{order} | {summary['solved'][order]}/{summary['complete']} | "
                    f"{summary['totals'][order]:.2f} | "
                    f"{pct_reduction(original, summary['totals'][order]):+.2f}% | "
                    f"{summary['wins'][order]} | {summary['meaningful'][order]} |"
                )

    lines.extend([
        "",
        "## Repeat Stability Against Original",
        "",
        "A stable win/loss requires the candidate to beat/lose to original by more than two "
        "seconds in both independent four-lane runs.",
        "",
        "| Representation | Regime | Order | All models | Informative | Stable wins | Stable losses | Mixed/small |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ])
    for representation in REPRESENTATIONS:
        for regime in REGIMES:
            for order in ORDERS[1:]:
                comparable, informative, better, worse, mixed = stable_against_original(
                    rows, representation, regime, order, args.timeout_penalty
                )
                lines.append(
                    f"| {representation} | {regime} | {order} | {comparable} | {informative} | "
                    f"{better} | {worse} | {mixed} |"
                )

    eligible, ranking = global_config_ranking(rows, args.timeout_penalty)
    best_total = ranking[0][2]
    lines.extend([
        "",
        "## Global Configuration Ranking",
        "",
        f"All {eligible} model/run cases solved by at least one of the 24 configurations are "
        "retained, so every row below uses exactly the same case set.",
        "",
        "| Rank | Configuration | Solved / 96 | Penalized s | Gap vs best |",
        "|---:|---|---:|---:|---:|",
    ])
    for rank, (config, solved, total) in enumerate(ranking, 1):
        lines.append(
            f"| {rank} | {config} | {solved}/96 | {total:.2f} | "
            f"{100.0 * (total / best_total - 1.0):+.2f}% |"
        )

    lines.extend([
        "",
        "## Does Input Order Change CNF Counts?",
        "",
        "Exact equality compares raw and simplified CNF count tuples across all four requested "
        "input orders for the same model/run/configuration.",
        "",
        "| Representation | Regime | Complete metric cases | Raw counts equal | Simplified counts equal |",
        "|---|---|---:|---:|---:|",
    ])
    for representation in REPRESENTATIONS:
        for regime in REGIMES:
            complete, raw_equal, simplified_equal = cnf_count_invariance(
                rows, representation, regime
            )
            lines.append(
                f"| {representation} | {regime} | {complete} | "
                f"{raw_equal}/{complete} | {simplified_equal}/{complete} |"
            )

    lines.extend(["", "## Promising Interaction: Case Contributions", ""])
    candidate = "xag_precanonical_fanout-desc"
    for reference in ("xag_precanonical_original", "aig_native_original"):
        candidate_only, reference_only, gains, losses = selected_pair_details(
            rows, reference, candidate, args.timeout_penalty
        )
        lines.extend([
            f"### {candidate} versus {reference}",
            "",
            f"Candidate-only solved runs: {candidate_only}; reference-only solved runs: "
            f"{reference_only}. Positive seconds below favor the candidate, aggregated over "
            "both repeats.",
            "",
            "| Largest gains | Year | Tier | Seconds | Largest losses | Year | Tier | Seconds |",
            "|---|---:|---|---:|---|---:|---|---:|",
        ])
        width = max(len(gains), len(losses))
        for index in range(width):
            gain = gains[index] if index < len(gains) else (math.nan, "", "", "")
            loss = losses[index] if index < len(losses) else (math.nan, "", "", "")
            gain_seconds = "" if math.isnan(gain[0]) else f"{gain[0]:+.2f}"
            loss_seconds = "" if math.isnan(loss[0]) else f"{loss[0]:+.2f}"
            lines.append(
                f"| {gain[1]} | {gain[2]} | {gain[3]} | {gain_seconds} | "
                f"{loss[1]} | {loss[2]} | {loss[3]} | {loss_seconds} |"
            )

    lines.extend([
        "",
        "## XAG Versus AIG By CNF Regime And Input Order",
        "",
        "Positive reduction means XAG has lower penalized cost than AIG.",
        "",
        "| Regime | Order | Cases | AIG solved | XAG solved | AIG s | XAG s | XAG reduction | AIG/XAG wins | Wins >2s |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for regime in REGIMES:
        for order in ORDERS:
            summary = summarize_representation(rows, regime, order, args.timeout_penalty)
            aig_total = summary["totals"]["aig"]
            xag_total = summary["totals"]["xag"]
            lines.append(
                f"| {regime} | {order} | {summary['eligible']}/{summary['complete']} | "
                f"{summary['solved']['aig']}/{summary['complete']} | "
                f"{summary['solved']['xag']}/{summary['complete']} | {aig_total:.2f} | "
                f"{xag_total:.2f} | {pct_reduction(aig_total, xag_total):+.2f}% | "
                f"{summary['wins']['aig']}/{summary['wins']['xag']} | "
                f"{summary['meaningful']['aig']}/{summary['meaningful']['xag']} |"
            )

    lines.extend([
        "",
        "## CNF And PDR Medians For Solved Runs",
        "",
        "| Representation | Regime | Solved rows | Simplified clauses | Simplified literals | Queries | CTI | MIC | Push | PDR s |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for representation in REPRESENTATIONS:
        for regime in REGIMES:
            subset = [
                row for row in rows
                if row["representation"] == representation
                and row["regime"] == regime
                and row["status"] in SOLVED
            ]
            fields = (
                "translation_simplified_clauses", "translation_simplified_literals",
                "queries", "cti", "mic", "push", "pdr_runtime",
            )
            medians = [median_number(subset, field) for field in fields]
            lines.append(
                f"| {representation} | {regime} | {len(subset)} | "
                + " | ".join(f"{value:.1f}" for value in medians)
                + " |"
            )

    lines.extend(["", "## Status Counts", ""])
    for representation in REPRESENTATIONS:
        for regime in REGIMES:
            counts = Counter(
                row["status"] for row in rows
                if row["representation"] == representation and row["regime"] == regime
            )
            lines.append(f"- {representation}_{regime}: {dict(counts)}")

    report = "\n".join(lines) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
