#!/usr/bin/env python3
"""
Small dependency-free sanity check for input-swap learnability.

The goal is deliberately modest: test whether coarse benchmark/pair features
can predict which PI swap reduces PDR queries on benchmarks not seen during
training.  This is not meant to be a strong model; it is a quick guardrail
against spending time on a direction that has no learnable signal.
"""

import argparse
import csv
import math
import random
import statistics
from collections import defaultdict


FEATURES = [
    "log_inputs",
    "log_pair_count",
    "i_norm",
    "j_norm",
    "gap_norm",
    "pair_index_norm",
    "touch_first",
    "log_base_q",
    "log_base_pdr",
    "base_depth_log",
    "base_cti_log",
    "base_gen_log",
    "base_ind_log",
    "xor_ratio",
    "unsafe",
]


def as_int(row, key):
    return int(row.get(key) or 0)


def as_float(row, key):
    return float(row.get(key) or 0.0)


def load_samples(path, min_base_queries):
    rows = list(csv.DictReader(open(path, newline=""), delimiter="\t"))
    by_run = defaultdict(list)
    for row in rows:
        by_run[(row["name"], row["repeat"])].append(row)

    samples = []
    for (name, _repeat), run_rows in by_run.items():
        baselines = [
            r for r in run_rows
            if r["pair_index"] == "baseline" and r.get("queries") and r.get("pdr_runtime")
        ]
        if not baselines:
            continue
        baseline = min(baselines, key=lambda r: as_float(r, "pdr_runtime"))
        try:
            base_queries = as_int(baseline, "queries")
            base_pdr = as_float(baseline, "pdr_runtime")
            base_depth = as_int(baseline, "depth")
            base_inductive = as_int(baseline, "inductive")
            base_cti = as_int(baseline, "cti")
            base_generalize = as_int(baseline, "generalize")
            ands = as_int(baseline, "ands")
            xors = as_int(baseline, "xors")
            num_inputs = as_int(baseline, "num_inputs")
            pair_count = as_int(baseline, "pair_count")
        except (TypeError, ValueError):
            continue
        if base_queries < min_base_queries or base_pdr <= 0:
            continue

        for row in run_rows:
            if row["pair_index"] == "baseline":
                continue
            if row.get("status") not in ("SAFE", "UNSAFE"):
                continue
            if not row.get("queries") or not row.get("pdr_runtime") or not row.get("pair_i"):
                continue
            try:
                swap_queries = as_int(row, "queries")
                pair_i = as_int(row, "pair_i")
                pair_j = as_int(row, "pair_j")
                pair_index = as_int(row, "pair_index")
            except (TypeError, ValueError):
                continue
            if swap_queries <= 0:
                continue

            x = [
                math.log1p(num_inputs),
                math.log1p(pair_count),
                pair_i / max(1, num_inputs),
                pair_j / max(1, num_inputs),
                (pair_j - pair_i) / max(1, num_inputs),
                pair_index / max(1, pair_count - 1),
                1.0 if pair_i == 1 or pair_j == 1 else 0.0,
                math.log1p(base_queries),
                math.log1p(base_pdr),
                math.log1p(base_depth),
                math.log1p(base_cti),
                math.log1p(base_generalize),
                math.log1p(base_inductive),
                xors / max(1, ands + xors),
                1.0 if baseline["status"] == "UNSAFE" else 0.0,
            ]
            samples.append({
                "name": name,
                "pair_index": pair_index,
                "x": x,
                "y": math.log(base_queries / swap_queries),
            })
    return samples


def train_linear(train, steps, learning_rate, l2):
    m = len(FEATURES)
    mu = [statistics.mean(s["x"][j] for s in train) for j in range(m)]
    sd = [statistics.pstdev([s["x"][j] for s in train]) or 1.0 for j in range(m)]
    weights = [0.0] * (m + 1)

    for step in range(steps):
        grad = [0.0] * (m + 1)
        for sample in train:
            z = [(sample["x"][j] - mu[j]) / sd[j] for j in range(m)]
            pred = weights[0] + sum(weights[j + 1] * z[j] for j in range(m))
            err = pred - sample["y"]
            grad[0] += err
            for j in range(m):
                grad[j + 1] += err * z[j]

        rate = learning_rate / (1.0 + step / max(1, steps / 2))
        n = len(train)
        weights[0] -= rate * grad[0] / n
        for j in range(m):
            weights[j + 1] -= rate * (grad[j + 1] / n + l2 * weights[j + 1])
    return weights, mu, sd


def predict(model, x):
    weights, mu, sd = model
    return weights[0] + sum(weights[j + 1] * ((x[j] - mu[j]) / sd[j]) for j in range(len(FEATURES)))


def auc(predictions):
    pos = [pred for pred, y in predictions if y > 0]
    neg = [pred for pred, y in predictions if y <= 0]
    if not pos or not neg:
        return float("nan")
    wins = ties = 0
    for p in pos:
        for n in neg:
            if p > n:
                wins += 1
            elif p == n:
                ties += 1
    return (wins + 0.5 * ties) / (len(pos) * len(neg))


def main():
    parser = argparse.ArgumentParser(description="Analyze learnability of input-swap choices")
    parser.add_argument("detail_tsv", help="compare_mc_input_swap*.tsv detail file")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--min-base-queries", type=int, default=1)
    parser.add_argument("--steps", type=int, default=500)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--l2", type=float, default=0.02)
    args = parser.parse_args()

    samples = load_samples(args.detail_tsv, args.min_base_queries)
    names = sorted({s["name"] for s in samples})
    random.Random(args.seed).shuffle(names)
    folds = [set(names[i::args.folds]) for i in range(args.folds)]

    all_predictions = []
    top_choices = []
    coef_rows = []
    for test_names in folds:
        train = [s for s in samples if s["name"] not in test_names]
        test = [s for s in samples if s["name"] in test_names]
        if not train or not test:
            continue
        model = train_linear(train, args.steps, args.learning_rate, args.l2)
        coef_rows.append(model[0])

        grouped = defaultdict(list)
        for sample in test:
            pred = predict(model, sample["x"])
            all_predictions.append((pred, sample["y"]))
            grouped[sample["name"]].append((pred, sample))

        for name, rows in grouped.items():
            chosen = max(rows, key=lambda item: item[0])[1]
            oracle = max(rows, key=lambda item: item[1]["y"])[1]
            avg_y = statistics.mean(item[1]["y"] for item in rows)
            top_choices.append((chosen["y"], oracle["y"], avg_y, name, chosen["pair_index"], oracle["pair_index"]))

    ys = [y for _, y in all_predictions]
    mean_y = statistics.mean(ys)
    sse = sum((pred - y) ** 2 for pred, y in all_predictions)
    sst = sum((y - mean_y) ** 2 for y in ys)

    print(f"samples\t{len(samples)}")
    print(f"benchmarks\t{len(names)}")
    print(f"positive_rate\t{sum(y > 0 for y in ys) / len(ys):.6f}")
    print(f"group_fold_auc\t{auc(all_predictions):.6f}")
    print(f"group_fold_r2\t{1.0 - sse / sst:.6f}")
    print(f"top_model_geo_query_ratio\t{math.exp(statistics.mean(t[0] for t in top_choices)):.6f}")
    print(f"top_oracle_geo_query_ratio\t{math.exp(statistics.mean(t[1] for t in top_choices)):.6f}")
    print(f"avg_pair_geo_query_ratio\t{math.exp(statistics.mean(t[2] for t in top_choices)):.6f}")
    print(f"top_model_improves\t{sum(t[0] > 0 for t in top_choices)}/{len(top_choices)}")
    print(f"top_oracle_improves\t{sum(t[1] > 0 for t in top_choices)}/{len(top_choices)}")

    avg_coefs = [statistics.mean(row[j + 1] for row in coef_rows) for j in range(len(FEATURES))]
    print("coefficients")
    for feature, coef in sorted(zip(FEATURES, avg_coefs), key=lambda item: abs(item[1]), reverse=True):
        print(f"{feature}\t{coef:.6f}")

    print("worst_model_choices")
    for chosen_y, oracle_y, avg_y, name, chosen_pair, oracle_pair in sorted(top_choices, key=lambda item: item[0])[:12]:
        print(
            f"{name}\tchosen_pair={chosen_pair}\tchosen_ratio={math.exp(chosen_y):.6f}\t"
            f"oracle_pair={oracle_pair}\toracle_ratio={math.exp(oracle_y):.6f}\tavg_ratio={math.exp(avg_y):.6f}"
        )


if __name__ == "__main__":
    main()
