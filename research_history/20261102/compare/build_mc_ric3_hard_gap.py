#!/usr/bin/env python3
"""Freeze the MC-AIG explanation set and its rIC3-hard expansion cohort."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Iterable


SOLVED = {"SAFE", "UNSAFE"}
DEFAULT_EXPANSION_FAMILIES = (
    "oski",
    "cal",
    "arbitrated_top_n",
    "picorv",
    "Problem",
    "circular_pointer_top_w",
    "vgasim_imgfifo",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hard-manifest", type=Path, required=True)
    parser.add_argument("--mc-input", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expansion-family", action="append", default=[])
    parser.add_argument("--per-expansion-family", type=int, default=8)
    return parser.parse_args()


def load_mc_rows(paths: Iterable[Path]) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for path in paths:
        with path.open(encoding="utf-8", newline="") as source:
            for row in csv.DictReader(source, delimiter="\t"):
                rows[row["model_id"]] = row
    return rows


def evenly_spaced(models: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    ordered = sorted(models, key=lambda model: (int(model["size_bytes"]), model["id"]))
    if len(ordered) <= count:
        return ordered
    if count == 1:
        return [ordered[len(ordered) // 2]]
    indices = {round(index * (len(ordered) - 1) / (count - 1)) for index in range(count)}
    return [ordered[index] for index in sorted(indices)]


def write_manifest(path: Path, models: list[dict[str, Any]], **metadata: Any) -> None:
    payload = {
        "schema": "mc-hard-gap-v1",
        **metadata,
        "models": sorted(models, key=lambda model: (str(model["year"]), model["id"])),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    hard_payload = json.loads(args.hard_manifest.read_text(encoding="utf-8"))
    hard_models = hard_payload["models"]
    mc_rows = load_mc_rows(args.mc_input)

    covered: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    aig_solved: list[dict[str, Any]] = []
    xag_incremental: list[dict[str, Any]] = []
    aig_unsolved: list[dict[str, Any]] = []

    for source_model in hard_models:
        model = dict(source_model)
        row = mc_rows.get(model["id"])
        if row is None:
            missing.append(model)
            continue
        model["mc_aig_legacy4"] = {
            "status": row["aig_legacy4_status"],
            "wall_seconds": row["aig_legacy4_wall_seconds"],
            "pdr_runtime": row["aig_legacy4_pdr_runtime"],
            "pdr_depth": row["aig_legacy4_pdr_depth"],
        }
        model["mc_xag_legacy4"] = {
            "status": row["xag_legacy4_status"],
            "wall_seconds": row["xag_legacy4_wall_seconds"],
        }
        model["mc_xag_best4"] = {
            "status": row["xag_best4_status"],
            "wall_seconds": row["xag_best4_wall_seconds"],
        }
        covered.append(model)
        aig_ok = row["aig_legacy4_status"] in SOLVED
        xag_ok = row["xag_legacy4_status"] in SOLVED or row["xag_best4_status"] in SOLVED
        if aig_ok:
            aig_solved.append(model)
        else:
            aig_unsolved.append(model)
            if xag_ok:
                xag_incremental.append(model)

    anchor_families = {model["family"] for model in aig_solved}
    anchor_family_models = [model for model in covered if model["family"] in anchor_families]
    expansion_families = tuple(args.expansion_family or DEFAULT_EXPANSION_FAMILIES)
    expansion_models: list[dict[str, Any]] = []
    for family in expansion_families:
        family_models = [model for model in aig_unsolved if model["family"] == family]
        expansion_models.extend(evenly_spaced(family_models, args.per_expansion_family))

    cohort_by_id = {
        model["id"]: model
        for model in anchor_family_models + xag_incremental + expansion_models
    }
    cohort = list(cohort_by_id.values())

    args.output_dir.mkdir(parents=True, exist_ok=True)
    common = {
        "hard_manifest": str(args.hard_manifest),
        "mc_inputs": [str(path) for path in args.mc_input],
    }
    write_manifest(args.output_dir / "mc_aig_breakthroughs.json", aig_solved, **common)
    write_manifest(args.output_dir / "mc_xag_incremental.json", xag_incremental, **common)
    write_manifest(args.output_dir / "mc_aig_unsolved.json", aig_unsolved, **common)
    write_manifest(args.output_dir / "mc_not_previously_run.json", missing, **common)
    write_manifest(
        args.output_dir / "mc_hard_diagnostic_cohort.json",
        cohort,
        **common,
        anchor_families=sorted(anchor_families),
        expansion_families=list(expansion_families),
        per_expansion_family=args.per_expansion_family,
    )

    summary = {
        "ric3_hard_3600": len(hard_models),
        "mc_covered": len(covered),
        "mc_not_previously_run": len(missing),
        "mc_aig_breakthroughs": len(aig_solved),
        "mc_xag_incremental": len(xag_incremental),
        "mc_aig_unsolved": len(aig_unsolved),
        "anchor_family_models": len(anchor_family_models),
        "diagnostic_cohort": len(cohort),
        "anchor_families": sorted(anchor_families),
        "expansion_families": list(expansion_families),
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
