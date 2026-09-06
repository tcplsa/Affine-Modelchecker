#!/usr/bin/env python3
"""Freeze a structure-blind train/holdout split for affine selector validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path


GROUP_FIELDS = (
    "polynomial", "taps", "topology", "left_topology", "right_topology",
    "left_struct", "right_struct", "left_adder", "right_adder",
    "left_multiplier", "right_multiplier", "primitive", "fcs_topology",
)
SCALE_FIELDS = (
    "symbol_bits", "data_bits", "steps", "width", "columns", "lane_width",
    "input_bits", "check_bits", "payload_cycles", "rounds", "delay",
)


def field(name: str, key: str) -> str:
    match = re.search(rf"(?:^|_){re.escape(key)}([^_]+)", name)
    return match.group(1) if match else ""


def structure_group(model: dict[str, object]) -> str:
    name = str(model["name"])
    tokens = [f"{key}={field(name, key)}" for key in GROUP_FIELDS if field(name, key)]
    return str(model["family"]) + "|" + ("|".join(tokens) if tokens else "single-topology")


def scale(model: dict[str, object]) -> int:
    name = str(model["name"])
    values = []
    for key in SCALE_FIELDS:
        raw = field(name, key)
        if raw.isdigit():
            values.append(int(raw))
    return max(values, default=int(model.get("size_bytes", 0) or 0))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--external-manifest", type=Path)
    parser.add_argument("--holdout-fraction", type=float, default=0.25)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    models = list(payload["models"])
    if args.external_manifest:
        external = json.loads(args.external_manifest.read_text(encoding="utf-8"))["models"]
        for source in external:
            model = dict(source)
            model.setdefault("scope", "external")
            model.setdefault("category", "public-rtl")
            model.setdefault("source_manifests", [str(args.external_manifest)])
            model["force_holdout"] = True
            models.append(model)
    by_family: dict[str, list[dict[str, object]]] = defaultdict(list)
    for model in models:
        model = dict(model)
        model["structure_group"] = structure_group(model)
        model["scale"] = scale(model)
        by_family[str(model["family"])].append(model)

    frozen: list[dict[str, object]] = []
    split_summary: dict[str, dict[str, object]] = {}
    for family, rows in sorted(by_family.items()):
        if all(bool(row.get("force_holdout")) for row in rows):
            for row in rows:
                row["split"] = "holdout"
                row["split_basis"] = "external-public-rtl"
            frozen.extend(rows)
            split_summary[family] = {
                "basis": "external-public-rtl",
                "groups": len({str(row["structure_group"]) for row in rows}),
                "train": 0,
                "holdout": len(rows),
                "heldout_groups": sorted({str(row["structure_group"]) for row in rows}),
            }
            continue
        groups = sorted({str(row["structure_group"]) for row in rows}, key=digest)
        holdout: set[str] = set()
        basis = "structure-group"
        if len(groups) > 1:
            count = min(len(groups) - 1, max(1, round(len(groups) * args.holdout_fraction)))
            holdout = set(groups[:count])
            for row in rows:
                row["split"] = "holdout" if row["structure_group"] in holdout else "train"
        else:
            basis = "contiguous-high-scale"
            scales = sorted({int(row["scale"]) for row in rows})
            count = max(1, math.ceil(len(scales) * args.holdout_fraction))
            held_scales = set(scales[-count:])
            for row in rows:
                row["split"] = "holdout" if int(row["scale"]) in held_scales else "train"
        for row in rows:
            row["split_basis"] = basis
        frozen.extend(rows)
        split_summary[family] = {
            "basis": basis,
            "groups": len(groups),
            "train": sum(row["split"] == "train" for row in rows),
            "holdout": sum(row["split"] == "holdout" for row in rows),
            "heldout_groups": sorted(holdout),
        }

    frozen.sort(key=lambda row: (str(row["split"]), str(row["family"]), str(row["name"])))
    result = {
        "schema": 1,
        "description": "Blind structure/topology split for affine selector validation",
        "source_manifest": str(args.input.resolve()),
        "holdout_fraction": args.holdout_fraction,
        "split_summary": split_summary,
        "models": frozen,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "models": len(frozen),
        "train": sum(row["split"] == "train" for row in frozen),
        "holdout": sum(row["split"] == "holdout" for row in frozen),
        "families": len(by_family),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
