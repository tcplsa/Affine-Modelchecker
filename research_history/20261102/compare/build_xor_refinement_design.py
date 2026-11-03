#!/usr/bin/env python3
"""Build exact phase-5 subsets inside the promising XOR parent bucket."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, Optional


Row = Dict[str, str]
CANONICAL_BUCKETS = [
    "fanout_2_3__near_le8__isolated",
    "fanout_2_3__near_le8__adjacent",
    "fanout_2_3__far_gt8__isolated",
    "fanout_2_3__far_gt8__adjacent",
    "fanout_ge4__near_le8__isolated",
    "fanout_ge4__near_le8__adjacent",
    "fanout_ge4__far_gt8__isolated",
    "fanout_ge4__far_gt8__adjacent",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", required=True, type=Path)
    parser.add_argument("--features", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def subbucket_name(row: Row) -> Optional[str]:
    if int(row["in_next"]) != 1:
        return None
    if int(row["fanout"]) < 2:
        return None
    if int(row["impl_child_external_fanouts"]) != 0:
        return None
    fanout = "fanout_2_3" if int(row["fanout"]) < 4 else "fanout_ge4"
    distance = "near_le8" if int(row["distance_to_next"]) <= 8 else "far_gt8"
    adjacent_count = int(row["fanin_xor_count"]) + int(row["fanout_xor_count"])
    adjacency = "isolated" if adjacent_count == 0 else "adjacent"
    return "__".join((fanout, distance, adjacency))


def write_allowlist(path: Path, variables: Iterable[int]) -> None:
    selected = sorted(variables)
    if not selected:
        # An empty file disables filtering in MC. XOR variable zero is a safe
        # sentinel that keeps the allowlist active while selecting no XORs.
        selected = [0]
    path.write_text(
        "".join("%d\n" % variable for variable in selected),
        encoding="ascii",
    )


def build_context_manifest(
    context: str,
    models: dict[str, dict],
    rows_by_model: dict[str, list[Row]],
    output_dir: Path,
) -> dict:
    manifest_models = []
    for name in sorted(models, key=lambda item: (models[item]["arm"], models[item]["year"], item)):
        record = dict(models[name])
        path = Path(record["path"])
        if not path.is_file():
            raise SystemExit("missing model: %s" % path)

        buckets: dict[str, set[int]] = defaultdict(set)
        all_vars: set[int] = set()
        parent_vars: set[int] = set()
        for row in rows_by_model[name]:
            variable = int(row["xor_var"])
            all_vars.add(variable)
            bucket = subbucket_name(row)
            if bucket is not None:
                buckets[bucket].add(variable)
                parent_vars.add(variable)

        active = [bucket for bucket in CANONICAL_BUCKETS if buckets[bucket]]
        if not active:
            raise SystemExit("no parent-bucket XORs for: %s" % name)
        non_parent_vars = all_vars - parent_vars
        model_dir = output_dir / context / record["arm"] / name
        model_dir.mkdir(parents=True, exist_ok=True)
        masks = []
        for mask in range(1 << len(active)):
            parent_selected: set[int] = set()
            for bit, bucket in enumerate(active):
                if mask & (1 << bit):
                    parent_selected.update(buckets[bucket])
            selected = set(parent_selected)
            if context == "retain":
                selected.update(non_parent_vars)
            allowlist = model_dir / ("mask_%03d.allow" % mask)
            write_allowlist(allowlist, selected)
            masks.append({
                "mask": mask,
                "allowlist": str(allowlist),
                "selected_xors": len(selected),
                "parent_selected_xors": len(parent_selected),
            })

        record.update({
            "path": str(path),
            "context": context,
            "total_xors": len(all_vars),
            "parent_xors": len(parent_vars),
            "non_parent_xors": len(non_parent_vars),
            "active_buckets": active,
            "bucket_sizes": {bucket: len(buckets[bucket]) for bucket in active},
            "full_mask": (1 << len(active)) - 1,
            "subset_count": 1 << len(active),
            "masks": masks,
        })
        manifest_models.append(record)

    return {
        "version": 1,
        "phase": "xor_refinement_phase5",
        "context": context,
        "parent_bucket": "next__fanout_ge2__private_impl",
        "canonical_buckets": CANONICAL_BUCKETS,
        "partition": {
            "fanout": ["fanout_2_3", "fanout_ge4"],
            "distance_to_next": ["near_le8", "far_gt8"],
            "xor_adjacency": ["isolated", "adjacent"],
        },
        "models": manifest_models,
    }


def main() -> int:
    args = parse_args()
    model_spec = json.loads(args.models.read_text(encoding="utf-8"))
    models = {record["name"]: dict(record) for record in model_spec["models"]}
    if len(models) != len(model_spec["models"]):
        raise SystemExit("model names must be unique")

    rows_by_model: dict[str, list[Row]] = defaultdict(list)
    with args.features.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["name"] in models:
                rows_by_model[row["name"]].append(row)
    missing = sorted(set(models) - set(rows_by_model))
    if missing:
        raise SystemExit("missing gate features for: %s" % ", ".join(missing))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for context in ("add", "retain"):
        manifest = build_context_manifest(
            context, models, rows_by_model, args.output_dir / "allowlists",
        )
        path = args.output_dir / ("manifest_%s.json" % context)
        path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print("context=%s manifest=%s" % (context, path))
        for arm in ("benefit", "harm"):
            selected = [model for model in manifest["models"] if model["arm"] == arm]
            tasks = sum(model["subset_count"] + 1 for model in selected)
            print("  arm=%s models=%d tasks_per_seed=%d" % (arm, len(selected), tasks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
