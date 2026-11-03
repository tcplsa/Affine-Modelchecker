#!/usr/bin/env python3
"""Select representative XOR interventions for compact/stable-slot ablation."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-runs", type=int, default=4)
    parser.add_argument("--timeout-penalty", type=float, default=900.0)
    parser.add_argument("--source-shard", choices=("server-a", "server-b"), default="server-a")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    design = json.loads(args.manifest.read_text(encoding="utf-8"))
    if len(design["models"]) != 2:
        raise SystemExit("expected the paired causal manifest")
    source_model = next(model for model in design["models"] if model["shard"] == args.source_shard)
    variants = {variant["id"]: variant for variant in source_model["variants"]}
    gate_by_var = {int(gate["xor_var"]): gate for gate in source_model["affected_gates"]}

    rows_by_variant: dict[str, list[dict[str, str]]] = defaultdict(list)
    with args.results.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["model_id"] == source_model["id"]:
                rows_by_variant[row["variant"]].append(row)

    scored: dict[str, tuple[float, int]] = {}
    for variant_id, rows in rows_by_variant.items():
        if len(rows) != args.expected_runs:
            raise SystemExit(f"{variant_id}: expected {args.expected_runs} rows, got {len(rows)}")
        values = [
            float(row["wall_seconds"])
            if row["status"] not in {"TIMEOUT", "ERROR", "CANCELLED"}
            else args.timeout_penalty
            for row in rows
        ]
        scored[variant_id] = (statistics.median(values), sum(row["status"] == "TIMEOUT" for row in rows))

    selected: dict[str, str] = {
        "baseline_full": "baseline",
        "baseline_retain248": "baseline",
    }
    for kind in ("single_addback", "single_remove"):
        for depth_class in ("shallow", "deep"):
            candidates = []
            for variant_id, variant in variants.items():
                if variant["kind"] != kind:
                    continue
                gate = gate_by_var[int(variant["xor_var"])]
                gate_class = "shallow" if int(gate["depth"]) <= 4 else "deep"
                if gate_class == depth_class:
                    candidates.append((scored[variant_id][0], variant_id))
            candidates.sort()
            if not candidates:
                continue
            resolved = [candidate for candidate in candidates if candidate[0] < args.timeout_penalty]
            representatives = (
                candidates[0],
                resolved[len(resolved) // 2] if resolved else candidates[len(candidates) // 2],
                candidates[-1],
            )
            for role, candidate in zip(("fast", "middle", "slow"), representatives):
                selected[candidate[1]] = f"{kind}:{depth_class}:{role}"

    chosen = []
    for variant_id, role in selected.items():
        variant = dict(variants[variant_id])
        variant["selection_role"] = role
        variant["prior_median_seconds"] = scored[variant_id][0]
        variant["prior_timeouts"] = scored[variant_id][1]
        chosen.append(variant)
    chosen.sort(key=lambda item: (item["kind"], int(item["xor_var"])))

    output_model = dict(source_model)
    output_model["variants"] = chosen
    output = {
        "version": 1,
        "experiment": "xor_stable_slot_ablation",
        "source_manifest": str(args.manifest),
        "source_results": str(args.results),
        "models": [output_model],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "manifest.json"
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for variant in chosen:
        print(
            f"{variant['id']:<24} role={variant['selection_role']:<29} "
            f"prior={variant['prior_median_seconds']:.3f}s timeouts={variant['prior_timeouts']}"
        )
    print(f"variants={len(chosen)} tasks_per_mode={len(chosen) * args.expected_runs} manifest={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
