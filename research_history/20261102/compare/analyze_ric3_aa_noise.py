#!/usr/bin/env python3
"""Report model-clustered wall-clock noise for identical rIC3 portfolios."""

from __future__ import annotations

import argparse
import csv
import glob
import math
import random
from collections import defaultdict
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-glob", required=True)
    parser.add_argument("--treatment-inputs", nargs="*", type=Path, default=[])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bootstrap", type=int, default=20000)
    return parser.parse_args()


def geo_log(values: list[float]) -> float:
    return math.exp(sum(values) / len(values)) if values else math.nan


def percentile(values: list[float], q: float) -> float:
    values = sorted(values)
    position = q * (len(values) - 1)
    low = int(position)
    high = min(low + 1, len(values) - 1)
    fraction = position - low
    return values[low] * (1 - fraction) + values[high] * fraction


def main() -> int:
    args = arguments()
    rows = []
    for path in sorted(glob.glob(args.input_glob)):
        with open(path, encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                row["repeat"] = Path(path).stem
                rows.append(row)

    pairs = []
    conflicts = 0
    for row in rows:
        left = row.get("aa_left_status")
        right = row.get("aa_right_status")
        if left in VALID and right in VALID:
            if left != right:
                conflicts += 1
                continue
            lt = float(row["aa_left_wall_seconds"])
            rt = float(row["aa_right_wall_seconds"])
            pairs.append((row["model_id"], row["tier"], math.log(rt / lt), rt - lt,
                          row["aa_left_replica"] == row["aa_right_replica"]))

    by_model: dict[str, list[float]] = defaultdict(list)
    for model, _tier, ratio, _diff, _same_replica in pairs:
        by_model[model].append(ratio)
    models = sorted(by_model)
    rng = random.Random(20260813)
    bootstrap = []
    for _ in range(args.bootstrap):
        sample = [rng.choice(models) for _ in models]
        logs = [value for model in sample for value in by_model[model]]
        bootstrap.append(geo_log(logs))

    logs = [pair[2] for pair in pairs]
    diffs = [abs(pair[3]) for pair in pairs]
    lines = [
        "# rIC3 same-seed A/A noise control", "",
        f"Rows: {len(rows)}; common solved pairs: {len(pairs)}; models: {len(models)}; "
        f"outcome conflicts: {conflicts}.", "",
        "Both sides use the same binary, Native legacy BVE order, and the same four "
        "deterministic seeds. The only intended difference is concurrent scheduling.", "",
        "| Metric | Value |", "|---|---:|",
        f"| Aggregate geometric right/left ratio | {geo_log(logs):.4f} |",
        f"| Model-clustered bootstrap 95% interval | [{percentile(bootstrap, 0.025):.4f}, {percentile(bootstrap, 0.975):.4f}] |",
        f"| Individual ratio 2.5%--97.5% | [{math.exp(percentile(logs, 0.025)):.3f}, {math.exp(percentile(logs, 0.975)):.3f}] |",
        f"| Median absolute wall difference | {percentile(diffs, 0.5):.3f}s |",
        f"| 95th-percentile absolute wall difference | {percentile(diffs, 0.95):.3f}s |",
        f"| Same winning replica | {sum(pair[4] for pair in pairs)}/{len(pairs)} ({sum(pair[4] for pair in pairs)/len(pairs):.1%}) |",
        "", "## Runtime strata", "",
        "| Tier | Pairs | Geometric ratio | Median absolute difference |",
        "|---|---:|---:|---:|",
    ]
    for tier in ("fast", "medium", "slow"):
        tier_rows = [pair for pair in pairs if pair[1] == tier]
        tier_logs = [pair[2] for pair in tier_rows]
        tier_diffs = [abs(pair[3]) for pair in tier_rows]
        lines.append(
            f"| {tier} | {len(tier_rows)} | {geo_log(tier_logs):.4f} | "
            f"{percentile(tier_diffs, 0.5):.3f}s |"
        )
    lines += [
        "", "The clustered interval is the relevant noise floor for aggregate geometric "
        "effects. The much wider individual interval quantifies why per-instance wall-time "
        "wins cannot be interpreted without pairing and aggregation.",
    ]
    if args.treatment_inputs:
        treatment_by_model: dict[str, list[float]] = defaultdict(list)
        treatment_rows = 0
        for path in args.treatment_inputs:
            with path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle, delimiter="\t"):
                    if (row.get("ric3_product_sum_high_status") in VALID
                            and row.get("ric3_legacy_status") in VALID):
                        treatment_rows += 1
                        treatment_by_model[row["model_id"]].append(math.log(
                            float(row["ric3_product_sum_high_wall_seconds"])
                            / float(row["ric3_legacy_wall_seconds"])
                        ))
        treatment_models = sorted(treatment_by_model)
        treatment_logs = [
            value for model in treatment_models for value in treatment_by_model[model]
        ]
        observed = geo_log(treatment_logs) / geo_log(logs)
        contrast_rng = random.Random(20260814)
        contrasts = []
        for _ in range(args.bootstrap):
            treatment_sample = [contrast_rng.choice(treatment_models) for _ in treatment_models]
            noise_sample = [contrast_rng.choice(models) for _ in models]
            treatment_value = geo_log([
                value for model in treatment_sample for value in treatment_by_model[model]
            ])
            noise_value = geo_log([
                value for model in noise_sample for value in by_model[model]
            ])
            contrasts.append(treatment_value / noise_value)
        lines += [
            "", "## Noise-adjusted treatment contrast", "",
            "This independent cluster bootstrap subtracts the A/A log-ratio from the "
            "product-sum-high/legacy log-ratio. A ratio below one favors the treatment.", "",
            "| Metric | Value |", "|---|---:|",
            f"| Treatment common rows/models | {treatment_rows}/{len(treatment_models)} |",
            f"| Noise-adjusted geometric ratio | {observed:.4f} |",
            f"| Independent model-clustered 95% interval | "
            f"[{percentile(contrasts, 0.025):.4f}, {percentile(contrasts, 0.975):.4f}] |",
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
