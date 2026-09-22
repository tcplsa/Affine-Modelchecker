#!/usr/bin/env python3
"""Analyze exact replay fidelity and deterministic order versus random mappings."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


METRICS = ("conflicts", "decisions", "propagations", "restarts")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def reduction(before: float, after: float) -> float:
    return 100.0 * (before - after) / before if before else 0.0


def change_text(before: float, delta: float) -> str:
    return f"{100.0 * delta / before:+.2f}%" if before else "n/a"


def main() -> int:
    args = parse_args()
    rows: list[dict[str, str]] = []
    for path in args.inputs:
        with path.open(encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle, delimiter="\t"))

    ok = [row for row in rows if row["replay_status"] == "OK"]
    recorded = [row for row in ok if row["mode"] == "recorded"]
    lines = [
        "# CNF Random Replay Calibration",
        "",
        f"Rows: {len(rows)}; status counts: {dict(Counter(row['replay_status'] for row in rows))}.",
        "",
        "## Recorded fidelity",
        "",
        "| Role | Traces | Conflicts exact | Decisions exact | Propagations exact | Restarts exact | Observation mismatches |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for role in sorted({row["solver_role"] for row in recorded}):
        group = [row for row in recorded if row["solver_role"] == role]
        exact = {
            metric: sum(
                int(row[f"recorded_{metric}"]) == int(row[f"replay_{metric}"])
                for row in group
            )
            for metric in METRICS
        }
        observation_mismatches = sum(int(row["observation_mismatches"] or 0) for row in group)
        lines.append(
            f"| {role} | {len(group)} | {exact['conflicts']}/{len(group)} | "
            f"{exact['decisions']}/{len(group)} | {exact['propagations']}/{len(group)} | "
            f"{exact['restarts']}/{len(group)} | {observation_mismatches} |"
        )

    lines += [
        "",
        "## Deterministic mapping versus random noise floor",
        "",
        "Positive reductions mean the deterministic candidate is cheaper than the recorded mapping.",
        "The random percentile is the fraction of fixed random mappings whose aggregate conflict count is worse than the candidate.",
        "",
        "| Representation | Origin | Role | Candidate | Traces | Conflict reduction | Time reduction | Random conflict range | Candidate random percentile |",
        "|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    grouped: dict[tuple[str, str, str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    for row in ok:
        key = (row["representation"], row["origin"], row["solver_role"], row["trace_key"] + "/" + row["trace"])
        grouped[key][row["mode"]] = row

    dimensions = sorted({key[:3] for key in grouped})
    for representation, origin, role in dimensions:
        candidate = "numeric" if origin == "first__first" else "first"
        traces = [
            modes for key, modes in grouped.items()
            if key[:3] == (representation, origin, role)
            and "recorded" in modes and candidate in modes
        ]
        if not traces:
            continue
        before_conflicts = sum(int(modes["recorded"]["replay_conflicts"]) for modes in traces)
        after_conflicts = sum(int(modes[candidate]["replay_conflicts"]) for modes in traces)
        before_time = sum(float(modes["recorded"]["replay_seconds"]) for modes in traces)
        after_time = sum(float(modes[candidate]["replay_seconds"]) for modes in traces)
        random_modes = sorted(
            {mode for modes in traces for mode in modes if mode.startswith("random-")},
            key=lambda mode: int(mode.split("-", 1)[1]),
        )
        random_totals = [
            sum(int(modes[mode]["replay_conflicts"]) for modes in traces if mode in modes)
            for mode in random_modes
        ]
        if random_totals:
            random_range = f"{min(random_totals):,}..{max(random_totals):,}"
            percentile = 100.0 * sum(after_conflicts < value for value in random_totals) / len(random_totals)
        else:
            random_range = "n/a"
            percentile = 0.0
        lines.append(
            f"| {representation} | {origin.replace('__', '/')} | {role} | {candidate} | {len(traces)} | "
            f"{reduction(before_conflicts, after_conflicts):+.2f}% | "
            f"{reduction(before_time, after_time):+.2f}% | {random_range} | {percentile:.1f}% |"
        )

    lines += [
        "",
        "## Model-paired robustness",
        "",
        "Frame files are summed within each model/run before computing paired log reductions. Random ranges contain the eight fixed random seeds.",
        "",
        "| Representation | Origin | Role | Candidate | Model/runs | Geometric reduction | Median reduction | Wins/losses/equal | Random geometric range | Random median range | Beats random median/all |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    identity_totals: dict[tuple[str, str, str, str, str, str], int] = defaultdict(int)
    for row in ok:
        identity_totals[(
            row["representation"], row["origin"], row["solver_role"],
            row["model_id"], row["run"], row["mode"],
        )] += int(row["replay_conflicts"] or 0)
    identity_dimensions = sorted({key[:3] for key in identity_totals})
    for representation, origin, role in identity_dimensions:
        candidate = "numeric" if origin == "first__first" else "first"
        identities = sorted({
            (key[3], key[4]) for key in identity_totals
            if key[:3] == (representation, origin, role)
        })
        samples = []
        for model_id, run in identities:
            prefix = (representation, origin, role, model_id, run)
            base_key = prefix + ("recorded",)
            candidate_key = prefix + (candidate,)
            random_keys = [prefix + (f"random-{seed}",) for seed in range(1, 9)]
            if base_key in identity_totals and candidate_key in identity_totals and all(
                key in identity_totals for key in random_keys
            ):
                samples.append((
                    identity_totals[base_key], identity_totals[candidate_key],
                    [identity_totals[key] for key in random_keys],
                ))
        if not samples:
            continue

        def paired_reduction(index):
            logs = []
            for baseline, deterministic, random_values in samples:
                value = deterministic if index is None else random_values[index]
                logs.append(math.log((baseline + 1.0) / (value + 1.0)))
            return (
                100.0 * (1.0 - math.exp(-statistics.mean(logs))),
                100.0 * (1.0 - math.exp(-statistics.median(logs))),
            )

        geometric, median = paired_reduction(None)
        random_scores = [paired_reduction(index) for index in range(8)]
        wins = sum(candidate_value < baseline for baseline, candidate_value, _ in samples)
        losses = sum(candidate_value > baseline for baseline, candidate_value, _ in samples)
        equal = len(samples) - wins - losses
        beats_median = sum(
            candidate_value < statistics.median(random_values)
            for _, candidate_value, random_values in samples
        )
        beats_all = sum(
            all(candidate_value < random_value for random_value in random_values)
            for _, candidate_value, random_values in samples
        )
        lines.append(
            f"| {representation} | {origin.replace('__', '/')} | {role} | {candidate} | {len(samples)} | "
            f"{geometric:+.2f}% | {median:+.2f}% | {wins}/{losses}/{equal} | "
            f"{min(score[0] for score in random_scores):+.2f}%..{max(score[0] for score in random_scores):+.2f}% | "
            f"{min(score[1] for score in random_scores):+.2f}%..{max(score[1] for score in random_scores):+.2f}% | "
            f"{beats_median}/{beats_all} |"
        )

    lines += [
        "",
        "## Cross-origin 2x2 conflict decomposition",
        "",
        "A=first mapping/first-origin workload, B=numeric mapping/first-origin workload,",
        "C=first mapping/numeric-origin workload, D=numeric mapping/numeric-origin workload.",
        "All values aggregate the traced workload prefixes; censored traces remain censored.",
        "",
        "| Representation | Role | Candidate workload | Pairs | A | B | C | D | Internal (B-A)/A | Flow (C-A)/A | Interaction/A | Total (D-A)/A |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    totals: dict[tuple[str, str, str, str, str], int] = defaultdict(int)
    for row in ok:
        totals[(row["representation"], row["model_id"], row["run"], row["solver_role"], row["origin"] + "/" + row["mode"])] += int(row["replay_conflicts"] or 0)
    pair_dimensions = sorted({(key[0], key[3]) for key in totals})
    for representation, role in pair_dimensions:
        identities = sorted({(key[1], key[2]) for key in totals if key[0] == representation and key[3] == role})
        candidate_origins = sorted({
            key[4].split("/", 1)[0] for key in totals
            if key[0] == representation and key[3] == role
            and key[4].split("/", 1)[0] in {"numeric__first", "numeric__numeric"}
        })
        for candidate_origin in candidate_origins:
            values = []
            labels = (
                "first__first/recorded", "first__first/numeric",
                f"{candidate_origin}/first", f"{candidate_origin}/recorded",
            )
            for model_id, run in identities:
                keys = [(representation, model_id, run, role, label) for label in labels]
                if all(key in totals for key in keys):
                    values.append([totals[key] for key in keys])
            if not values:
                continue
            a, b, c, d = [sum(value[index] for value in values) for index in range(4)]
            lines.append(
                f"| {representation} | {role} | {candidate_origin.replace('__', '/')} | "
                f"{len(values)} | {a:,} | {b:,} | {c:,} | {d:,} | "
                f"{change_text(a, b-a)} | {change_text(a, c-a)} | "
                f"{change_text(a, d-b-c+a)} | {change_text(a, d-a)} |"
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
