#!/usr/bin/env python3
"""Fit a guarded, cost-sensitive selector from the large campaign."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from fit_input_order_selector import (
    FEATURES,
    Node,
    Sample,
    evaluate,
    family_fold,
    fit_tree,
    print_tree,
)


SOLVED = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, nargs="+", required=True)
    parser.add_argument("--features", type=Path, nargs="+", required=True)
    parser.add_argument("--baseline", default="state_000")
    parser.add_argument("--top-states", type=int, default=12)
    parser.add_argument("--max-per-family", type=int, default=2)
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--min-leaf", type=int, default=20)
    parser.add_argument("--cv-folds", type=int, default=5)
    parser.add_argument("--timeout-multiplier", type=float, default=1.5)
    parser.add_argument("--switch-penalty-percent", type=float, default=1.0)
    parser.add_argument("--minimum-cv-gain-percent", type=float, default=1.0)
    parser.add_argument("--min-action-span", type=float, default=1.0)
    parser.add_argument("--minimum-year-gain-percent", type=float, default=0.0)
    parser.add_argument(
        "--minimum-seed-transfer-gain-percent", type=float, default=0.0,
    )
    parser.add_argument(
        "--seed-aggregation", choices=["mean", "max"], default="max",
    )
    parser.add_argument(
        "--metric", choices=["algorithm", "pdr", "wall"], default="algorithm",
    )
    parser.add_argument("--model-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path)
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def number(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, ""))
    except (TypeError, ValueError):
        return default


def measured_cost(
    row: dict[str, str],
    action: str,
    metric: str,
    penalty: float,
) -> tuple[float, bool]:
    solved = row.get(f"{action}_status", "") in SOLVED
    wall = number(row, f"{action}_wall_seconds", penalty)
    pdr = number(row, f"{action}_pdr_runtime", wall)
    transform = (
        number(row, f"{action}_input_order_runtime")
        + number(row, f"{action}_conversion_runtime")
    )
    value = wall if metric == "wall" else pdr if metric == "pdr" else pdr + transform
    return (value if solved else penalty), solved


def load_features(paths: list[Path]) -> dict[tuple[str, str], dict[str, str]]:
    result = {}
    for path in paths:
        match = re.search(r"(20\d{2})", path.stem)
        inferred_year = match.group(1) if match else ""
        for row in read_tsv(path):
            result[(row.get("year") or inferred_year, row["name"])] = row
    return result


def choose_shortlist(
    samples: list[Sample],
    action_configs: dict[str, dict],
    baseline: str,
    limit: int,
    max_per_family: int,
) -> list[str]:
    totals = {
        action: sum(sample.costs[action] for sample in samples)
        for action in action_configs
        if all(action in sample.costs for sample in samples)
    }
    if baseline not in totals:
        raise SystemExit("baseline is unavailable on at least one sample")
    ranked = sorted(
        (action for action in totals if action != baseline),
        key=lambda action: totals[action],
    )
    selected = [baseline]
    family_counts: dict[str, int] = defaultdict(int)
    for action in ranked:
        family = str(action_configs[action].get("design_family", "unknown"))
        if family_counts[family] >= max_per_family:
            continue
        selected.append(action)
        family_counts[family] += 1
        if len(selected) >= limit:
            break
    return selected


def penalized(samples: list[Sample], baseline: str, percent: float) -> list[Sample]:
    factor = 1.0 + percent / 100.0
    return [
        Sample(
            name=sample.name,
            family=sample.family,
            features=sample.features,
            costs={
                action: cost if action == baseline else cost * factor
                for action, cost in sample.costs.items()
            },
            solved=sample.solved,
        )
        for sample in samples
    ]


def build_samples(
    observations: dict[
        tuple[str, str], dict[str, list[tuple[float, bool]]]
    ],
    static: dict[tuple[str, str], dict[str, str]],
) -> list[Sample]:
    samples = []
    for (year, name), action_values in observations.items():
        feature = static.get((year, name))
        if feature is None:
            continue
        costs = {
            action: sum(value for value, _solved in values) / len(values)
            for action, values in action_values.items()
        }
        solved = {
            action: all(flag for _value, flag in values)
            for action, values in action_values.items()
        }
        samples.append(Sample(
            name=f"{year}:{name}",
            family=feature.get("family", name),
            features={
                feature_name: float(feature.get(feature_name) or 0.0)
                for feature_name in FEATURES
            },
            costs=costs,
            solved=solved,
        ))
    return samples


def select_samples(
    samples: list[Sample],
    names: set[str],
    actions: list[str],
) -> list[Sample]:
    return [
        Sample(
            name=sample.name,
            family=sample.family,
            features=sample.features,
            costs={action: sample.costs[action] for action in actions},
            solved={action: sample.solved[action] for action in actions},
        )
        for sample in samples
        if sample.name in names and all(action in sample.costs for action in actions)
    ]


def combine_seed_samples(
    samples_by_seed: dict[int, list[Sample]],
    aggregation: str,
) -> list[Sample]:
    indexed = {
        seed: {sample.name: sample for sample in samples}
        for seed, samples in samples_by_seed.items()
    }
    names = set.intersection(
        *(set(samples) for samples in indexed.values())
    )
    combined = []
    for name in sorted(names):
        members = [indexed[seed][name] for seed in sorted(indexed)]
        actions = set.intersection(*(set(member.costs) for member in members))
        costs = {}
        for action in actions:
            values = [member.costs[action] for member in members]
            costs[action] = (
                max(values) if aggregation == "max"
                else sum(values) / len(values)
            )
        combined.append(Sample(
            name=name,
            family=members[0].family,
            features=members[0].features,
            costs=costs,
            solved={
                action: all(member.solved[action] for member in members)
                for action in actions
            },
        ))
    return combined


def seed_transfer_oracle(
    train: list[Sample],
    test: list[Sample],
    actions: list[str],
) -> dict:
    test_by_name = {sample.name: sample for sample in test}
    baseline_cost = 0.0
    selected_cost = 0.0
    baseline_solved = 0
    selected_solved = 0
    switches = 0
    cases = 0
    for train_sample in train:
        test_sample = test_by_name.get(train_sample.name)
        if test_sample is None:
            continue
        action = min(actions, key=lambda item: train_sample.costs[item])
        baseline_cost += test_sample.costs["aig"]
        selected_cost += test_sample.costs[action]
        baseline_solved += int(test_sample.solved["aig"])
        selected_solved += int(test_sample.solved[action])
        switches += int(action != "aig")
        cases += 1
    return {
        "cases": cases,
        "switches": switches,
        "baseline_cost": baseline_cost,
        "selected_cost": selected_cost,
        "gain_vs_baseline_percent": (
            100.0 * (baseline_cost - selected_cost) / baseline_cost
            if baseline_cost else 0.0
        ),
        "selector_solved": selected_solved,
        "baseline_solved": baseline_solved,
    }


def main() -> int:
    args = parse_args()
    static = load_features(args.features)
    seed_observations: dict[
        int,
        dict[tuple[str, str], dict[str, list[tuple[float, bool]]]],
    ] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    sample_context: dict[tuple[str, str], str] = {}
    action_configs: dict[str, dict] = {
        "aig": {
            "id": "aig",
            "label": "AIG original",
            "design_family": "aig",
            "forward_aig": 1,
        }
    }

    for result_path in args.results:
        design_path = result_path.with_name(result_path.stem + "_design.json")
        if not result_path.exists() or not design_path.exists():
            continue
        design = json.loads(design_path.read_text(encoding="utf-8"))
        year = str(design.get("year", ""))
        tier = str(design.get("group", ""))
        design_seed = int(design.get("design_seed", 0))
        solver_seed = int(design.get("solver_seed", 0))
        configs = design.get("configs", [])
        for config in configs:
            if config["id"] == args.baseline:
                continue
            action = f"d{design_seed}_{config['id']}"
            stored = dict(config)
            stored["id"] = action
            stored["source_id"] = config["id"]
            stored["design_seed"] = design_seed
            action_configs[action] = stored
        for row in read_tsv(result_path):
            key = (year or row.get("year", ""), row["name"])
            sample_context[key] = tier
            penalty = (
                number(row, "timeout_seconds", design.get("timeout", 30.0))
                * args.timeout_multiplier
            )
            base_value = measured_cost(
                row, args.baseline, args.metric, penalty,
            )
            seed_observations[solver_seed][key]["aig"].append(base_value)
            for config in configs:
                if config["id"] == args.baseline:
                    continue
                action = f"d{design_seed}_{config['id']}"
                value = measured_cost(
                    row, config["id"], args.metric, penalty,
                )
                seed_observations[solver_seed][key][action].append(value)

    raw_seed_samples = {
        seed: build_samples(seed_values, static)
        for seed, seed_values in seed_observations.items()
    }
    samples = combine_seed_samples(
        raw_seed_samples, args.seed_aggregation,
    )
    if not samples:
        raise SystemExit("no campaign rows matched structural features")

    common_actions = set.intersection(
        *(set(sample.costs) for sample in samples)
    )
    action_configs = {
        action: config for action, config in action_configs.items()
        if action in common_actions
    }
    samples_before_filter = len(samples)
    samples = [
        sample for sample in samples
        if (
            max(sample.costs[action] for action in common_actions)
            - min(sample.costs[action] for action in common_actions)
        ) > args.min_action_span
    ]
    if not samples:
        raise SystemExit("no samples remain after the action-span filter")
    included_names = {sample.name for sample in samples}
    sample_distribution = Counter(
        (
            sample.name.split(":", 1)[0],
            sample_context.get(tuple(sample.name.split(":", 1)), ""),
        )
        for sample in samples
    )
    seed_samples_all = {
        seed: select_samples(
            values,
            included_names,
            sorted(common_actions),
        )
        for seed, values in raw_seed_samples.items()
    }
    seed_transfer_oracles = []
    seeds = sorted(seed_samples_all)
    for train_seed in seeds:
        for test_seed in seeds:
            if train_seed == test_seed:
                continue
            row = seed_transfer_oracle(
                seed_samples_all[train_seed],
                seed_samples_all[test_seed],
                sorted(common_actions),
            )
            row.update({
                "train_seed": train_seed,
                "test_seed": test_seed,
                "actions": len(common_actions),
            })
            seed_transfer_oracles.append(row)

    actions = choose_shortlist(
        samples, action_configs, "aig",
        args.top_states, args.max_per_family,
    )
    samples = select_samples(samples, included_names, actions)
    seed_samples = {
        seed: select_samples(values, included_names, actions)
        for seed, values in seed_samples_all.items()
    }
    fit_samples = penalized(
        samples, "aig", args.switch_penalty_percent,
    )

    baseline_cv = sum(sample.costs["aig"] for sample in samples)
    depth_rows = []
    best_depth = 0
    best_cost = baseline_cv
    for depth in range(args.max_depth + 1):
        cv_cost = 0.0
        covered = 0
        for fold in range(args.cv_folds):
            train = [
                sample for sample in fit_samples
                if family_fold(sample.family, args.cv_folds) != fold
            ]
            test = [
                sample for sample in samples
                if family_fold(sample.family, args.cv_folds) == fold
            ]
            if not train or not test:
                continue
            tree = fit_tree(train, actions, depth, args.min_leaf)
            cv_cost += sum(
                sample.costs[tree.predict(sample.features)]
                for sample in test
            )
            covered += len(test)
        gain = (
            100.0 * (baseline_cv - cv_cost) / baseline_cv
            if baseline_cv else 0.0
        )
        depth_rows.append({
            "depth": depth,
            "cv_cost": cv_cost,
            "cv_gain_percent": gain,
            "covered": covered,
        })
        if cv_cost < best_cost:
            best_cost = cv_cost
            best_depth = depth
    cv_gain = (
        100.0 * (baseline_cv - best_cost) / baseline_cv
        if baseline_cv else 0.0
    )
    candidate_tree = fit_tree(
        fit_samples, actions, best_depth, args.min_leaf,
    )
    candidate_train_metrics = evaluate(samples, candidate_tree, actions)
    year_rows = []
    years = sorted({sample.name.split(":", 1)[0] for sample in samples})
    for year in years:
        train = [
            sample for sample in fit_samples
            if not sample.name.startswith(year + ":")
        ]
        test = [
            sample for sample in samples
            if sample.name.startswith(year + ":")
        ]
        if not train or not test:
            continue
        fold_tree = fit_tree(
            train, actions, best_depth, args.min_leaf,
        )
        metrics = evaluate(test, fold_tree, actions)
        year_rows.append({
            "held_out_year": year,
            "cases": metrics["cases"],
            "selector": metrics["selector"],
            "gain_vs_baseline_percent": metrics["gain_vs_baseline_percent"],
            "oracle_gain_percent": metrics["oracle_gain_percent"],
            "selector_solved": metrics["selector_solved"],
            "baseline_solved": metrics["solved"]["aig"],
        })

    seed_transfer_rows = []
    for train_seed in seeds:
        for test_seed in seeds:
            if train_seed == test_seed:
                continue
            train = penalized(
                seed_samples[train_seed], "aig",
                args.switch_penalty_percent,
            )
            seed_tree = fit_tree(
                train, actions, best_depth, args.min_leaf,
            )
            metrics = evaluate(
                seed_samples[test_seed], seed_tree, actions,
            )
            seed_transfer_rows.append({
                "train_seed": train_seed,
                "test_seed": test_seed,
                "cases": metrics["cases"],
                "gain_vs_baseline_percent": metrics[
                    "gain_vs_baseline_percent"
                ],
                "selector_solved": metrics["selector_solved"],
                "baseline_solved": metrics["solved"]["aig"],
            })

    guard_rejections = []
    if cv_gain < args.minimum_cv_gain_percent:
        guard_rejections.append(
            f"CV gain {cv_gain:.6f}% < {args.minimum_cv_gain_percent:.6f}%"
        )
    if year_rows:
        minimum_year_gain = min(
            row["gain_vs_baseline_percent"] for row in year_rows
        )
        if minimum_year_gain < args.minimum_year_gain_percent:
            guard_rejections.append(
                f"year gain {minimum_year_gain:.6f}% < "
                f"{args.minimum_year_gain_percent:.6f}%"
            )
    if seed_transfer_rows:
        minimum_seed_gain = min(
            row["gain_vs_baseline_percent"] for row in seed_transfer_rows
        )
        if minimum_seed_gain < args.minimum_seed_transfer_gain_percent:
            guard_rejections.append(
                f"seed-transfer gain {minimum_seed_gain:.6f}% < "
                f"{args.minimum_seed_transfer_gain_percent:.6f}%"
            )
    guarded = not guard_rejections
    tree = candidate_tree if guarded else Node(action="aig")
    train_metrics = evaluate(samples, tree, actions)

    args.model_output.parent.mkdir(parents=True, exist_ok=True)
    model = {
        "version": 2,
        "baseline": "aig",
        "actions": actions,
        "action_configs": {
            action: action_configs[action] for action in actions
        },
        "features": FEATURES,
        "tree": tree.as_dict(),
        "candidate_tree": candidate_tree.as_dict(),
        "selection": {
            "guarded": guarded,
            "selected_depth": best_depth if guarded else "baseline",
            "candidate_depth": best_depth,
            "cv_gain_percent": cv_gain,
            "switch_penalty_percent": args.switch_penalty_percent,
            "minimum_cv_gain_percent": args.minimum_cv_gain_percent,
            "minimum_year_gain_percent": args.minimum_year_gain_percent,
            "minimum_seed_transfer_gain_percent": (
                args.minimum_seed_transfer_gain_percent
            ),
            "seed_aggregation": args.seed_aggregation,
            "min_action_span": args.min_action_span,
            "samples_before_filter": samples_before_filter,
            "samples_after_filter": len(samples),
            "guard_rejections": guard_rejections,
            "top_states": args.top_states,
            "max_per_family": args.max_per_family,
        },
        "train_metrics": train_metrics,
        "candidate_train_metrics": candidate_train_metrics,
        "leave_one_year_out": year_rows,
        "model_seed_transfer": seed_transfer_rows,
        "offline_state_seed_transfer": seed_transfer_oracles,
        "sample_distribution": [
            {"year": year, "tier": tier, "cases": cases}
            for (year, tier), cases in sorted(sample_distribution.items())
        ],
    }
    args.model_output.write_text(
        json.dumps(model, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path = args.report_output or args.model_output.with_suffix(".md")
    report = [
        "# Large Initial-State Selector",
        "",
        f"- Samples before span filter: {samples_before_filter}",
        f"- Samples after >{args.min_action_span:g}s span filter: {len(samples)}",
        f"- Cross-seed training aggregation: {args.seed_aggregation}",
        f"- Shortlisted actions: {len(actions)}",
        f"- Family-fold CV gain: {cv_gain:.3f}%",
        f"- Baseline guard active: {not guarded}",
        f"- Guard rejections: {'; '.join(guard_rejections) if guard_rejections else 'none'}",
        f"- Selected depth: {best_depth if guarded else 'baseline'}",
        f"- Candidate training gain: "
        f"{candidate_train_metrics['gain_vs_baseline_percent']:.3f}%",
        f"- Deployed training gain: "
        f"{train_metrics['gain_vs_baseline_percent']:.3f}%",
        f"- Training solved: {train_metrics['selector_solved']} "
        f"(AIG {train_metrics['solved']['aig']})",
        "",
        "## Shortlist",
        "",
    ]
    for action in actions:
        config = action_configs[action]
        report.append(
            f"- `{action}`: {config.get('label', action)} "
            f"({config.get('design_family', 'unknown')})"
        )
    report.extend([
        "",
        "## Sample Distribution",
        "",
        "| Year | Tier | Cases |",
        "|---:|---|---:|",
    ])
    for (year, tier), cases in sorted(sample_distribution.items()):
        report.append(f"| {year} | {tier} | {cases} |")
    report.extend([
        "",
        "## Cross Validation",
        "",
        "| Depth | Cost | Gain | Covered |",
        "|---:|---:|---:|---:|",
    ])
    for row in depth_rows:
        report.append(
            f"| {row['depth']} | {row['cv_cost']:.3f} | "
            f"{row['cv_gain_percent']:.3f}% | {row['covered']} |"
        )
    report.extend([
        "",
        "## Leave One Year Out",
        "",
        "| Year | Cases | Gain | Selector solved | AIG solved |",
        "|---|---:|---:|---:|---:|",
    ])
    for row in year_rows:
        report.append(
            f"| {row['held_out_year']} | {row['cases']} | "
            f"{row['gain_vs_baseline_percent']:.3f}% | "
            f"{row['selector_solved']} | {row['baseline_solved']} |"
        )
    report.extend([
        "",
        "## Solver-Seed Transfer",
        "",
        "The model rows train a tree on one solver seed and evaluate it on the other. "
        "The offline rows choose the best exact state for each circuit on one seed; "
        "they measure representation opportunity, not deployable selection.",
        "",
        "| Kind | Train seed | Test seed | Actions | Cases | Gain | Selector solved | AIG solved |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in seed_transfer_rows:
        report.append(
            f"| model | {row['train_seed']} | {row['test_seed']} | "
            f"{len(actions)} | {row['cases']} | "
            f"{row['gain_vs_baseline_percent']:.3f}% | "
            f"{row['selector_solved']} | {row['baseline_solved']} |"
        )
    for row in seed_transfer_oracles:
        report.append(
            f"| offline exact-state choice | {row['train_seed']} | "
            f"{row['test_seed']} | {row['actions']} | {row['cases']} | "
            f"{row['gain_vs_baseline_percent']:.3f}% | "
            f"{row['selector_solved']} | {row['baseline_solved']} |"
        )
    report.extend(["", "## Tree", "", "See the JSON model for the exact tree.", ""])
    report_path.write_text("\n".join(report), encoding="utf-8")

    print(f"samples_before_filter\t{samples_before_filter}")
    print(f"samples_after_filter\t{len(samples)}")
    print(f"actions\t{','.join(actions)}")
    print(f"cv_gain_percent\t{cv_gain:.6f}")
    print(f"guarded\t{int(guarded)}")
    print(f"guard_rejections\t{' | '.join(guard_rejections)}")
    print("tree")
    print_tree(tree)
    print(f"model_output\t{args.model_output}")
    print(f"report_output\t{report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
