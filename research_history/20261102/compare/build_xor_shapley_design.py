#!/usr/bin/env python3
"""Build exact subset allowlists for mutually exclusive XOR structure buckets."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable


Row = Dict[str, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", required=True, type=Path)
    parser.add_argument("--features", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    return parser.parse_args()


def bucket_name(row: Row) -> str:
    next_part = "next" if int(row["in_next"]) else "outside_next"
    fanout_part = "fanout_lt2" if int(row["fanout"]) < 2 else "fanout_ge2"
    private = int(row["impl_child_external_fanouts"]) == 0
    impl_part = "private_impl" if private else "reused_impl"
    return "__".join((next_part, fanout_part, impl_part))


def write_allowlist(path: Path, variables: Iterable[int]) -> None:
    selected = sorted(variables)
    # An empty file means "no allowlist" to MC. Variable zero is never an XOR
    # gate, but keeps the filter active and therefore represents the empty set.
    if not selected:
        selected = [0]
    path.write_text(
        "".join("%d\n" % variable for variable in selected),
        encoding="ascii",
    )


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
    manifest_models = []
    for name in sorted(models, key=lambda item: (models[item]["arm"], models[item]["year"], item)):
        record = dict(models[name])
        path = Path(record["path"])
        if not path.is_file():
            raise SystemExit("missing model: %s" % path)

        buckets: dict[str, set[int]] = defaultdict(set)
        all_vars: set[int] = set()
        for row in rows_by_model[name]:
            variable = int(row["xor_var"])
            all_vars.add(variable)
            buckets[bucket_name(row)].add(variable)
        active = sorted(bucket for bucket, variables in buckets.items() if variables)
        if len(active) > 8:
            raise AssertionError("the primary partition has at most eight buckets")

        model_dir = args.output_dir / record["arm"] / name
        model_dir.mkdir(parents=True, exist_ok=True)
        masks = []
        for mask in range(1 << len(active)):
            selected: set[int] = set()
            for bit, bucket in enumerate(active):
                if mask & (1 << bit):
                    selected.update(buckets[bucket])
            allowlist = model_dir / ("mask_%03d.allow" % mask)
            write_allowlist(allowlist, selected)
            masks.append({
                "mask": mask,
                "allowlist": str(allowlist),
                "selected_xors": len(selected),
            })

        record.update({
            "path": str(path),
            "total_xors": len(all_vars),
            "active_buckets": active,
            "bucket_sizes": {bucket: len(buckets[bucket]) for bucket in active},
            "full_mask": (1 << len(active)) - 1,
            "subset_count": 1 << len(active),
            "masks": masks,
        })
        manifest_models.append(record)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps({
            "version": 1,
            "partition": {
                "in_next": ["outside_next", "next"],
                "fanout": ["fanout_lt2", "fanout_ge2"],
                "implementation": ["private_impl", "reused_impl"],
            },
            "models_file": str(args.models),
            "features_file": str(args.features),
            "models": manifest_models,
        }, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    total = sum(record["subset_count"] + 1 for record in manifest_models)
    print("models=%d tasks_per_seed=%d manifest=%s" % (
        len(manifest_models), total, args.manifest,
    ))
    for arm in ("benefit", "harm"):
        selected = [record for record in manifest_models if record["arm"] == arm]
        print("%s models=%d tasks_per_seed=%d" % (
            arm, len(selected), sum(record["subset_count"] + 1 for record in selected),
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
