#!/usr/bin/env python3
"""Select and cross-check global phase-5 XOR subbucket policies."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable


SOLVED = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--add-manifest", required=True, type=Path)
    parser.add_argument("--retain-manifest", required=True, type=Path)
    parser.add_argument("--add-results", required=True, nargs="+", type=Path)
    parser.add_argument("--retain-results", required=True, nargs="+", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--timeout-multiplier", type=float, default=1.5)
    parser.add_argument("--min-effect", type=float, default=2.0)
    return parser.parse_args()


def write_tsv(path: Path, rows: Iterable[dict], header: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def load_rows(paths: list[Path]) -> Dict[tuple[str, int, str], dict]:
    rows: Dict[tuple[str, int, str], dict] = {}
    for path in paths:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                rows[(row["name"], int(row["seed"]), row["task"])] = row
    return rows


def row_cost(row: dict, multiplier: float) -> float:
    if row["status"] in SOLVED:
        return float(row["wall_seconds"])
    return float(row["timeout_seconds"]) * multiplier


def global_to_local(global_mask: int, active: list[str], canonical: list[str]) -> int:
    local = 0
    canonical_index = {bucket: bit for bit, bucket in enumerate(canonical)}
    for bit, bucket in enumerate(active):
        if global_mask & (1 << canonical_index[bucket]):
            local |= 1 << bit
    return local


def build_observations(
    manifest: dict,
    raw: Dict[tuple[str, int, str], dict],
    multiplier: float,
) -> tuple[list[dict], list[dict]]:
    observations = []
    issues = []
    seeds = sorted({seed for _name, seed, _task in raw})
    for model in manifest["models"]:
        n = len(model["active_buckets"])
        for seed in seeds:
            mask_rows = {
                mask: raw.get((model["name"], seed, "mask_%03d" % mask))
                for mask in range(1 << n)
            }
            baseline = raw.get((model["name"], seed, "baseline_aig"))
            missing = [mask for mask, row in mask_rows.items() if row is None]
            if missing or baseline is None:
                issues.append({
                    "context": manifest["context"],
                    "name": model["name"],
                    "seed": seed,
                    "issue": "missing",
                    "detail": "%d masks%s" % (
                        len(missing), " and AIG" if baseline is None else "",
                    ),
                })
                continue
            outcomes = {
                row["status"] for row in mask_rows.values()
                if row["status"] in SOLVED
            }
            if baseline["status"] in SOLVED:
                outcomes.add(baseline["status"])
            if len(outcomes) > 1:
                issues.append({
                    "context": manifest["context"],
                    "name": model["name"],
                    "seed": seed,
                    "issue": "outcome_conflict",
                    "detail": ",".join(sorted(outcomes)),
                })
                continue
            observations.append({
                "context": manifest["context"],
                "name": model["name"],
                "arm": model["arm"],
                "year": model["year"],
                "seed": seed,
                "active": model["active_buckets"],
                "mask_rows": mask_rows,
                "costs": {
                    mask: row_cost(row, multiplier)
                    for mask, row in mask_rows.items()
                },
                "context_baseline_mask": 0 if manifest["context"] == "add" else (1 << n) - 1,
                "aig_cost": row_cost(baseline, multiplier),
                "aig_status": baseline["status"],
            })
    return observations, issues


def score_policy(
    observations: list[dict],
    global_mask: int,
    canonical: list[str],
    min_effect: float,
) -> dict:
    costs = []
    aig_costs = []
    context_baseline_costs = []
    deltas = []
    context_deltas = []
    solved = 0
    model_deltas: dict[str, list[float]] = defaultdict(list)
    model_context_deltas: dict[str, list[float]] = defaultdict(list)
    model_costs: dict[str, list[float]] = defaultdict(list)
    model_aig_costs: dict[str, list[float]] = defaultdict(list)
    model_context_costs: dict[str, list[float]] = defaultdict(list)
    for obs in observations:
        local = global_to_local(global_mask, obs["active"], canonical)
        cost = obs["costs"][local]
        row = obs["mask_rows"][local]
        delta = obs["aig_cost"] - cost
        context_baseline_cost = obs["costs"][obs["context_baseline_mask"]]
        context_delta = context_baseline_cost - cost
        costs.append(cost)
        aig_costs.append(obs["aig_cost"])
        context_baseline_costs.append(context_baseline_cost)
        deltas.append(delta)
        context_deltas.append(context_delta)
        model_deltas[obs["name"]].append(delta)
        model_context_deltas[obs["name"]].append(context_delta)
        model_costs[obs["name"]].append(cost)
        model_aig_costs[obs["name"]].append(obs["aig_cost"])
        model_context_costs[obs["name"]].append(context_baseline_cost)
        solved += row["status"] in SOLVED
    total = sum(costs)
    aig_total = sum(aig_costs)
    context_total = sum(context_baseline_costs)
    model_robust_deltas = {
        name: statistics.median(model_aig_costs[name]) - statistics.median(values)
        for name, values in model_costs.items()
    }
    model_robust_context_deltas = {
        name: statistics.median(model_context_costs[name]) - statistics.median(values)
        for name, values in model_costs.items()
    }
    robust_total = sum(statistics.median(values) for values in model_costs.values())
    robust_aig_total = sum(statistics.median(values) for values in model_aig_costs.values())
    robust_context_total = sum(
        statistics.median(values) for values in model_context_costs.values()
    )
    return {
        "global_mask": global_mask,
        "buckets": ",".join(
            bucket for bit, bucket in enumerate(canonical)
            if global_mask & (1 << bit)
        ) or "none",
        "selected_bucket_count": bin(global_mask).count("1"),
        "observations": len(observations),
        "models": len(model_deltas),
        "solved": solved,
        "total_cost": total,
        "aig_total_cost": aig_total,
        "context_baseline_total_cost": context_total,
        "gain_vs_aig_percent": 100.0 * (aig_total - total) / aig_total if aig_total else 0.0,
        "gain_vs_context_percent": 100.0 * (context_total - total) / context_total if context_total else 0.0,
        "robust_total_cost": robust_total,
        "robust_aig_total_cost": robust_aig_total,
        "robust_context_baseline_total_cost": robust_context_total,
        "robust_gain_vs_aig_percent": 100.0 * (robust_aig_total - robust_total) / robust_aig_total if robust_aig_total else 0.0,
        "robust_gain_vs_context_percent": 100.0 * (robust_context_total - robust_total) / robust_context_total if robust_context_total else 0.0,
        "median_delta_seconds": statistics.median(deltas) if deltas else 0.0,
        "median_context_delta_seconds": statistics.median(context_deltas) if context_deltas else 0.0,
        "wins": sum(delta > min_effect for delta in deltas),
        "losses": sum(delta < -min_effect for delta in deltas),
        "neutral": sum(abs(delta) <= min_effect for delta in deltas),
        "model_wins": sum(delta > min_effect for delta in model_robust_deltas.values()),
        "model_losses": sum(delta < -min_effect for delta in model_robust_deltas.values()),
        "model_neutral": sum(abs(delta) <= min_effect for delta in model_robust_deltas.values()),
        "context_wins": sum(delta > min_effect for delta in context_deltas),
        "context_losses": sum(delta < -min_effect for delta in context_deltas),
        "context_neutral": sum(abs(delta) <= min_effect for delta in context_deltas),
        "context_model_wins": sum(delta > min_effect for delta in model_robust_context_deltas.values()),
        "context_model_losses": sum(delta < -min_effect for delta in model_robust_context_deltas.values()),
        "context_model_neutral": sum(abs(delta) <= min_effect for delta in model_robust_context_deltas.values()),
    }


def unique_policy_scores(
    observations: list[dict],
    canonical: list[str],
    min_effect: float,
) -> list[dict]:
    signatures = set()
    scores = []
    ordered = sorted(observations, key=lambda row: (row["name"], row["seed"]))
    for global_mask in range(1 << len(canonical)):
        signature = tuple(
            global_to_local(global_mask, obs["active"], canonical)
            for obs in ordered
        )
        if signature in signatures:
            continue
        signatures.add(signature)
        scores.append(score_policy(observations, global_mask, canonical, min_effect))
    return sorted(
        scores,
        key=lambda row: (
            row["robust_total_cost"], row["context_model_losses"], row["selected_bucket_count"],
        ),
    )


def loo_rows(
    context: str,
    observations: list[dict],
    canonical: list[str],
    min_effect: float,
) -> list[dict]:
    output = []
    for holdout in sorted({obs["name"] for obs in observations}):
        train = [obs for obs in observations if obs["name"] != holdout]
        test = [obs for obs in observations if obs["name"] == holdout]
        best = unique_policy_scores(train, canonical, min_effect)[0]
        tested = score_policy(test, int(best["global_mask"]), canonical, min_effect)
        output.append({
            "context": context,
            "holdout": holdout,
            "global_mask": best["global_mask"],
            "buckets": best["buckets"],
            "train_gain_vs_aig_percent": "%.6f" % best["gain_vs_aig_percent"],
            "train_robust_gain_vs_aig_percent": "%.6f" % best["robust_gain_vs_aig_percent"],
            "holdout_gain_vs_aig_percent": "%.6f" % tested["robust_gain_vs_aig_percent"],
            "holdout_total_cost": "%.6f" % tested["robust_total_cost"],
            "holdout_aig_total_cost": "%.6f" % tested["robust_aig_total_cost"],
            "holdout_context_baseline_total_cost": "%.6f" % tested["robust_context_baseline_total_cost"],
            "holdout_gain_vs_context_percent": "%.6f" % tested["robust_gain_vs_context_percent"],
        })
    return output


def main() -> int:
    args = parse_args()
    if args.timeout_multiplier < 1 or args.min_effect < 0:
        raise SystemExit("timeout multiplier must be >=1 and min effect non-negative")
    manifests = {
        "add": json.loads(args.add_manifest.read_text(encoding="utf-8")),
        "retain": json.loads(args.retain_manifest.read_text(encoding="utf-8")),
    }
    canonical = manifests["add"]["canonical_buckets"]
    if manifests["retain"]["canonical_buckets"] != canonical:
        raise SystemExit("add and retain manifests use different canonical buckets")
    raw_by_context = {
        "add": load_rows(args.add_results),
        "retain": load_rows(args.retain_results),
    }

    observations_by_context = {}
    issues = []
    for context in ("add", "retain"):
        observations, current_issues = build_observations(
            manifests[context], raw_by_context[context], args.timeout_multiplier,
        )
        observations_by_context[context] = observations
        issues.extend(current_issues)

    policy_rows = []
    best_records = []
    loo = []
    for context in ("add", "retain"):
        all_observations = observations_by_context[context]
        for scope in ("all", "benefit", "harm"):
            scoped = [
                obs for obs in all_observations
                if scope == "all" or obs["arm"] == scope
            ]
            if not scoped:
                continue
            scores = unique_policy_scores(scoped, canonical, args.min_effect)
            for rank, score in enumerate(scores, 1):
                row = dict(score)
                row.update({"context": context, "scope": scope, "rank": rank})
                for field in (
                    "total_cost", "aig_total_cost", "gain_vs_aig_percent",
                    "context_baseline_total_cost", "gain_vs_context_percent",
                    "robust_total_cost", "robust_aig_total_cost",
                    "robust_context_baseline_total_cost", "robust_gain_vs_aig_percent",
                    "robust_gain_vs_context_percent",
                    "median_delta_seconds", "median_context_delta_seconds",
                ):
                    row[field] = "%.6f" % float(row[field])
                policy_rows.append(row)
            best = dict(scores[0])
            best.update({"context": context, "scope": scope})
            best_records.append(best)
        loo.extend(loo_rows(
            context, all_observations, canonical, args.min_effect,
        ))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    policy_header = [
        "context", "scope", "rank", "global_mask", "buckets",
        "selected_bucket_count", "observations", "models", "solved",
        "total_cost", "aig_total_cost", "gain_vs_aig_percent",
        "context_baseline_total_cost", "gain_vs_context_percent",
        "robust_total_cost", "robust_aig_total_cost",
        "robust_context_baseline_total_cost", "robust_gain_vs_aig_percent",
        "robust_gain_vs_context_percent",
        "median_delta_seconds", "median_context_delta_seconds",
        "wins", "losses", "neutral",
        "model_wins", "model_losses", "model_neutral",
        "context_wins", "context_losses", "context_neutral",
        "context_model_wins", "context_model_losses", "context_model_neutral",
    ]
    write_tsv(args.output_dir / "global_policy_ranking.tsv", policy_rows, policy_header)
    write_tsv(args.output_dir / "leave_one_model_out.tsv", loo, [
        "context", "holdout", "global_mask", "buckets",
        "train_gain_vs_aig_percent", "train_robust_gain_vs_aig_percent",
        "holdout_gain_vs_aig_percent",
        "holdout_total_cost", "holdout_aig_total_cost",
        "holdout_context_baseline_total_cost", "holdout_gain_vs_context_percent",
    ])
    write_tsv(args.output_dir / "issues.tsv", issues, [
        "context", "name", "seed", "issue", "detail",
    ])

    model_breakdown = []
    for best in best_records:
        context = best["context"]
        scope = best["scope"]
        scoped = [
            obs for obs in observations_by_context[context]
            if scope == "all" or obs["arm"] == scope
        ]
        for name in sorted({obs["name"] for obs in scoped}):
            selected = [obs for obs in scoped if obs["name"] == name]
            scored = score_policy(
                selected, int(best["global_mask"]), canonical, args.min_effect,
            )
            model_breakdown.append({
                "context": context,
                "scope": scope,
                "global_mask": best["global_mask"],
                "buckets": best["buckets"],
                "name": name,
                "arm": selected[0]["arm"],
                "runs": len(selected),
                "policy_cost": "%.6f" % scored["robust_total_cost"],
                "aig_cost": "%.6f" % scored["robust_aig_total_cost"],
                "context_baseline_cost": "%.6f" % scored["robust_context_baseline_total_cost"],
                "gain_vs_aig_percent": "%.6f" % scored["robust_gain_vs_aig_percent"],
                "gain_vs_context_percent": "%.6f" % scored["robust_gain_vs_context_percent"],
                "context_wins": scored["context_wins"],
                "context_losses": scored["context_losses"],
                "context_neutral": scored["context_neutral"],
            })
    write_tsv(args.output_dir / "best_policy_model_breakdown.tsv", model_breakdown, [
        "context", "scope", "global_mask", "buckets", "name", "arm", "runs",
        "policy_cost", "aig_cost", "context_baseline_cost",
        "gain_vs_aig_percent", "gain_vs_context_percent",
        "context_wins", "context_losses", "context_neutral",
    ])

    frozen = {
        "version": 1,
        "phase": "xor_refinement_phase5",
        "training_runs": sorted({
            obs["seed"] for obs in observations_by_context["add"]
        }),
        "canonical_buckets": canonical,
        "policies": {
            "%s_%s" % (row["context"], row["scope"]): {
                "context": row["context"],
                "scope": row["scope"],
                "global_mask": row["global_mask"],
                "buckets": row["buckets"].split(",") if row["buckets"] != "none" else [],
                "training_gain_vs_aig_percent": row["gain_vs_aig_percent"],
                "training_gain_vs_context_percent": row["gain_vs_context_percent"],
                "training_robust_gain_vs_aig_percent": row["robust_gain_vs_aig_percent"],
                "training_robust_gain_vs_context_percent": row["robust_gain_vs_context_percent"],
            }
            for row in best_records
        },
    }
    (args.output_dir / "frozen_policies.json").write_text(
        json.dumps(frozen, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# XOR Parent-Bucket Refinement",
        "",
        "- Complete add observations: %d" % len(observations_by_context["add"]),
        "- Complete retain observations: %d" % len(observations_by_context["retain"]),
        "- Issues: %d" % len(issues),
        "- Each run is an independent multi-lane portfolio; policy validation must hold out circuits, not run identifiers.",
        "",
        "| Context | Scope | Buckets | Robust gain vs AIG | Robust gain vs context | Context model W/L/N |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in best_records:
        lines.append(
            "| {context} | {scope} | {buckets} | {robust_gain_vs_aig_percent:.3f}% | "
            "{robust_gain_vs_context_percent:.3f}% | "
            "{context_model_wins}/{context_model_losses}/{context_model_neutral} |".format(**row)
        )
    for context in ("add", "retain"):
        selected = [row for row in loo if row["context"] == context]
        test_cost = sum(float(row["holdout_total_cost"]) for row in selected)
        aig_cost = sum(float(row["holdout_aig_total_cost"]) for row in selected)
        gain = 100.0 * (aig_cost - test_cost) / aig_cost if aig_cost else 0.0
        context_cost = sum(
            float(row["holdout_context_baseline_total_cost"]) for row in selected
        )
        context_gain = 100.0 * (context_cost - test_cost) / context_cost if context_cost else 0.0
        lines.extend((
            "",
            "- `%s` leave-one-model-out aggregate gain vs AIG: %.3f%%." % (context, gain),
            "- `%s` leave-one-model-out aggregate gain vs context baseline: %.3f%%." % (context, context_gain),
        ))
    (args.output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("policies=%d issues=%d report=%s" % (
        len(policy_rows), len(issues), args.output_dir / "report.md",
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
