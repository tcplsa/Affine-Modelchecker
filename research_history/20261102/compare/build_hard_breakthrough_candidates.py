#!/usr/bin/env python3
"""Select cross-family hard models whose observed bottleneck is actionable."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--atlas", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def enabled(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def number(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def main() -> int:
    args = parse_args()
    with args.atlas.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))

    models = []
    reason_counts: Counter[str] = Counter()
    for row in rows:
        if row["status"] in {"SAFE", "UNSAFE"} or enabled(row["mc_aig_solved"]):
            continue
        labels = set(filter(None, row["failure_labels"].split(",")))
        depth = number(row["depth"])
        reasons = []
        if depth <= 9 and labels & {"front-end-or-few-query", "sat-heavy-query"}:
            reasons.append("phase-sat-frontier")
        if depth >= 7 and labels & {"push-convergence", "high-query-volume"}:
            reasons.append("induction-convergence-frontier")
        if "early-obligation-generalization" in labels:
            reasons.append("generalization-frontier")
        if not reasons:
            continue
        reason_counts.update(reasons)
        models.append({
            "id": row["model_id"],
            "name": row["name"],
            "year": int(row["year"]),
            "family": row["family"],
            "path": row["path"],
            "size_bytes": int(row["size_bytes"]),
            "diagnostic_depth": depth,
            "failure_labels": sorted(labels),
            "selection_reasons": reasons,
            "structural_class": row["structural_class"],
            "mc_previously_run": enabled(row["mc_previously_run"]),
        })

    models.sort(key=lambda model: (model["year"], model["id"]))
    payload = {
        "schema": "mc-hard-breakthrough-candidates-v1",
        "selection": {
            "excluded": "120-second solves and historical MC-AIG solves",
            "rules": {
                "phase-sat-frontier": "depth <= 9 and front-end/few-query or SAT-heavy",
                "induction-convergence-frontier": "depth >= 7 and push/high-query",
                "generalization-frontier": "early obligation/generalization signature",
            },
            "reason_counts": dict(sorted(reason_counts.items())),
            "families": len({model["family"] for model in models}),
        },
        "models": models,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        f"models={len(models)} families={payload['selection']['families']} "
        f"reasons={dict(reason_counts)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
