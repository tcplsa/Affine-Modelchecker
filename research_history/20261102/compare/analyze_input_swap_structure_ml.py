#!/usr/bin/env python3
"""Test whether static per-input topology predicts useful PI pair swaps."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import statistics
from collections import defaultdict
from pathlib import Path

from xag_structural_features import family_name, lit_sign, lit_var, read_aig


INPUT_METRICS = (
    "fanout",
    "positive_uses",
    "negative_uses",
    "first_use_depth",
    "mean_use_depth",
    "next_influence",
    "bad_influence",
)
GLOBAL_FEATURES = ("log_inputs", "log_latches", "log_ands", "unsafe")


def circuit_input_features(path: Path) -> tuple[list[dict[str, float]], dict[str, float]]:
    aig = read_aig(path)
    count = len(aig.inputs)
    fanout = [0.0] * (count + 1)
    positive = [0.0] * (count + 1)
    negative = [0.0] * (count + 1)
    first_depth = [float("inf")] * (count + 1)
    depth_sum = [0.0] * (count + 1)
    depths = [0] * (aig.max_var + 1)

    for gate in aig.ands:
        out = lit_var(gate.out)
        depths[out] = 1 + max(depths[lit_var(gate.i0)], depths[lit_var(gate.i1)])
        for lit in (gate.i0, gate.i1):
            var = lit_var(lit)
            if 1 <= var <= count:
                fanout[var] += 1.0
                positive[var] += float(not lit_sign(lit))
                negative[var] += float(lit_sign(lit))
                first_depth[var] = min(first_depth[var], depths[out])
                depth_sum[var] += depths[out]

    def backward_influence(roots: list[int]) -> list[float]:
        influence = [0.0] * (aig.max_var + 1)
        for root in roots:
            influence[lit_var(root)] += 1.0
        for gate in reversed(aig.ands):
            out = lit_var(gate.out)
            mass = min(influence[out], 1e100)
            if mass == 0.0:
                continue
            influence[lit_var(gate.i0)] = min(1e100, influence[lit_var(gate.i0)] + 0.5 * mass)
            influence[lit_var(gate.i1)] = min(1e100, influence[lit_var(gate.i1)] + 0.5 * mass)
        return influence

    next_influence = backward_influence([latch.next for latch in aig.latches])
    bad_roots = list(aig.bads or aig.outputs) + list(aig.constraints)
    bad_influence = backward_influence(bad_roots)
    rows = [{} for _ in range(count + 1)]
    for var in range(1, count + 1):
        rows[var] = {
            "fanout": fanout[var],
            "positive_uses": positive[var],
            "negative_uses": negative[var],
            "first_use_depth": 0.0 if first_depth[var] == float("inf") else first_depth[var],
            "mean_use_depth": depth_sum[var] / fanout[var] if fanout[var] else 0.0,
            "next_influence": next_influence[var],
            "bad_influence": bad_influence[var],
        }
    return rows, {
        "log_inputs": math.log1p(count),
        "log_latches": math.log1p(len(aig.latches)),
        "log_ands": math.log1p(len(aig.ands)),
    }


def feature_names() -> list[str]:
    names = ["i_norm", "j_norm", "gap_norm"]
    for metric in INPUT_METRICS:
        names.extend((f"{metric}_i", f"{metric}_j", f"{metric}_diff", f"{metric}_alignment"))
    return names + list(GLOBAL_FEATURES)


FEATURES = feature_names()


def pair_features(
    per_input: list[dict[str, float]],
    global_features: dict[str, float],
    i: int,
    j: int,
    unsafe: bool,
) -> list[float]:
    count = max(1, len(per_input) - 1)
    values = [i / count, j / count, (j - i) / count]
    for metric in INPUT_METRICS:
        left = math.log1p(per_input[i][metric])
        right = math.log1p(per_input[j][metric])
        values.extend((left, right, left - right, (left - right) * (j - i) / count))
    values.extend(global_features[name] for name in GLOBAL_FEATURES[:-1])
    values.append(float(unsafe))
    return values


def load_samples(path: Path, min_base_queries: int) -> list[dict]:
    by_run: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in csv.DictReader(path.open(newline=""), delimiter="\t"):
        by_run[(row["name"], row["repeat"])].append(row)

    circuit_cache = {}
    samples = []
    for (name, _repeat), rows in by_run.items():
        baselines = [
            row for row in rows
            if row["pair_index"] == "baseline" and row.get("queries")
            and row.get("status") in ("SAFE", "UNSAFE")
        ]
        if not baselines:
            continue
        baseline = min(baselines, key=lambda row: float(row.get("pdr_runtime") or "inf"))
        base_queries = int(baseline["queries"])
        if base_queries < min_base_queries:
            continue
        aig_path = Path(baseline["aig_path"])
        if aig_path not in circuit_cache:
            circuit_cache[aig_path] = circuit_input_features(aig_path)
        per_input, global_features = circuit_cache[aig_path]

        for row in rows:
            if row["pair_index"] == "baseline" or row.get("status") not in ("SAFE", "UNSAFE"):
                continue
            if not row.get("queries") or not row.get("pair_i") or not row.get("pair_j"):
                continue
            swap_queries = int(row["queries"])
            i, j = int(row["pair_i"]), int(row["pair_j"])
            if swap_queries <= 0 or i >= len(per_input) or j >= len(per_input):
                continue
            samples.append({
                "name": name,
                "family": family_name(name),
                "pair_index": int(row["pair_index"]),
                "x": pair_features(
                    per_input, global_features, i, j, baseline["status"] == "UNSAFE"
                ),
                "y": math.log(base_queries / swap_queries),
            })
    return samples


def train_linear(samples: list[dict], steps: int, rate: float, l2: float):
    width = len(FEATURES)
    means = [statistics.mean(row["x"][j] for row in samples) for j in range(width)]
    scales = [statistics.pstdev(row["x"][j] for row in samples) or 1.0 for j in range(width)]
    standardized = [
        (
            [(row["x"][j] - means[j]) / scales[j] for j in range(width)],
            row["y"],
        )
        for row in samples
    ]
    weights = [0.0] * (width + 1)
    for step in range(steps):
        gradient = [0.0] * (width + 1)
        for z, target in standardized:
            error = weights[0] + sum(weights[j + 1] * z[j] for j in range(width)) - target
            gradient[0] += error
            for j, value in enumerate(z):
                gradient[j + 1] += error * value
        current_rate = rate / (1.0 + step / max(1.0, steps / 2.0))
        weights[0] -= current_rate * gradient[0] / len(standardized)
        for j in range(width):
            weights[j + 1] -= current_rate * (
                gradient[j + 1] / len(standardized) + l2 * weights[j + 1]
            )
    return weights, means, scales


def predict(model, values: list[float]) -> float:
    weights, means, scales = model
    return weights[0] + sum(
        weights[j + 1] * ((values[j] - means[j]) / scales[j])
        for j in range(len(values))
    )


def auc(rows: list[tuple[float, float]]) -> float:
    positive = [score for score, target in rows if target > 0]
    negative = [score for score, target in rows if target <= 0]
    if not positive or not negative:
        return float("nan")
    wins = sum(p > n for p in positive for n in negative)
    ties = sum(p == n for p in positive for n in negative)
    return (wins + 0.5 * ties) / (len(positive) * len(negative))


def fold_for_family(family: str, folds: int, seed: int) -> int:
    digest = hashlib.sha256(f"{seed}:{family}".encode()).digest()
    return int.from_bytes(digest[:8], "little") % folds


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate static per-input features on existing swap labels."
    )
    parser.add_argument("detail_tsv", type=Path)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--min-base-queries", type=int, default=1000)
    parser.add_argument("--steps", type=int, default=500)
    parser.add_argument("--learning-rate", type=float, default=0.04)
    parser.add_argument("--l2", type=float, default=0.03)
    args = parser.parse_args()

    samples = load_samples(args.detail_tsv, args.min_base_queries)
    predictions = []
    choices = []
    coefficients = []
    for fold in range(args.folds):
        train = [
            row for row in samples
            if fold_for_family(row["family"], args.folds, args.seed) != fold
        ]
        test = [
            row for row in samples
            if fold_for_family(row["family"], args.folds, args.seed) == fold
        ]
        if not train or not test:
            continue
        model = train_linear(train, args.steps, args.learning_rate, args.l2)
        coefficients.append(model[0])
        grouped = defaultdict(list)
        for row in test:
            score = predict(model, row["x"])
            predictions.append((score, row["y"]))
            grouped[row["name"]].append((score, row))
        for name, rows in grouped.items():
            chosen = max(rows, key=lambda item: item[0])[1]
            oracle = max(rows, key=lambda item: item[1]["y"])[1]
            choices.append((chosen["y"], oracle["y"], name, chosen["pair_index"], oracle["pair_index"]))

    targets = [target for _, target in predictions]
    mean_target = statistics.mean(targets)
    sse = sum((score - target) ** 2 for score, target in predictions)
    sst = sum((target - mean_target) ** 2 for target in targets)
    print(f"samples\t{len(samples)}")
    print(f"benchmarks\t{len({row['name'] for row in samples})}")
    print(f"families\t{len({row['family'] for row in samples})}")
    print(f"positive_rate\t{sum(target > 0 for target in targets) / len(targets):.6f}")
    print(f"family_fold_auc\t{auc(predictions):.6f}")
    print(f"family_fold_r2\t{1.0 - sse / sst:.6f}")
    print(
        "top_model_geo_query_ratio\t"
        f"{math.exp(statistics.mean(row[0] for row in choices)):.6f}"
    )
    print(
        "top_oracle_geo_query_ratio\t"
        f"{math.exp(statistics.mean(row[1] for row in choices)):.6f}"
    )
    print(f"top_model_improves\t{sum(row[0] > 0 for row in choices)}/{len(choices)}")
    print(f"top_oracle_improves\t{sum(row[1] > 0 for row in choices)}/{len(choices)}")
    mean_coefficients = [
        statistics.mean(weights[j + 1] for weights in coefficients)
        for j in range(len(FEATURES))
    ]
    print("coefficients")
    for feature, weight in sorted(
        zip(FEATURES, mean_coefficients), key=lambda item: abs(item[1]), reverse=True
    )[:20]:
        print(f"{feature}\t{weight:.6f}")
    print("worst_model_choices")
    for chosen, oracle, name, chosen_pair, oracle_pair in sorted(choices)[:12]:
        print(
            f"{name}\tchosen_pair={chosen_pair}\tchosen_ratio={math.exp(chosen):.6f}\t"
            f"oracle_pair={oracle_pair}\toracle_ratio={math.exp(oracle):.6f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
