#!/usr/bin/env python3
"""Build a preregistered, family-disjoint AIG-hard BVE validation cohort."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--exclude-selection", action="append", default=[], type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bad-xor-density", type=float, default=0.01)
    parser.add_argument("--per-year", type=int, default=10)
    parser.add_argument("--max-and-ratio", type=float, default=8.0)
    parser.add_argument("--minimum-baseline-seconds", type=float, default=55.0)
    return parser.parse_args()


def family_representatives(models: list[dict[str, object]]) -> list[dict[str, object]]:
    by_family: dict[str, list[dict[str, object]]] = {}
    for model in models:
        by_family.setdefault(str(model["family"]), []).append(model)
    representatives = []
    for family, members in sorted(by_family.items()):
        ordered = sorted(members, key=lambda model: (int(model["aig_ands"]), str(model["id"])))
        representatives.append(ordered[(len(ordered) - 1) // 2])
    return representatives


def spaced(models: list[dict[str, object]], count: int) -> list[dict[str, object]]:
    ordered = sorted(models, key=lambda model: (int(model["aig_ands"]), str(model["id"])))
    if count >= len(ordered):
        return ordered
    if count == 1:
        return [ordered[len(ordered) // 2]]
    indices = sorted({round(index * (len(ordered) - 1) / (count - 1)) for index in range(count)})
    return [ordered[index] for index in indices]


def match_controls(
    rich: list[dict[str, object]], poor: list[dict[str, object]], max_ratio: float,
) -> list[tuple[dict[str, object], dict[str, object]]]:
    candidates = []
    limit = math.log(max_ratio)
    for candidate in rich:
        for control in poor:
            gap = abs(
                math.log1p(int(candidate["aig_ands"]))
                - math.log1p(int(control["aig_ands"]))
            )
            if gap <= limit:
                candidates.append((gap, str(candidate["id"]), str(control["id"]), candidate, control))
    used_rich: set[str] = set()
    used_poor: set[str] = set()
    pairs = []
    for _gap, rich_id, poor_id, candidate, control in sorted(candidates):
        if rich_id in used_rich or poor_id in used_poor:
            continue
        used_rich.add(rich_id)
        used_poor.add(poor_id)
        pairs.append((candidate, control))
    return pairs


def main() -> int:
    args = arguments()
    if args.per_year <= 0:
        raise SystemExit("--per-year must be positive")
    if not 0.0 <= args.bad_xor_density <= 1.0:
        raise SystemExit("--bad-xor-density must be in [0, 1]")
    if args.max_and_ratio < 1.0:
        raise SystemExit("--max-and-ratio must be at least 1")
    if args.minimum_baseline_seconds <= 0.0:
        raise SystemExit("--minimum-baseline-seconds must be positive")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    excluded_families: set[str] = set()
    for path in args.exclude_selection:
        selection = json.loads(path.read_text(encoding="utf-8"))
        excluded_families.update(str(model["family"]) for model in selection["models"])

    eligible = [
        model for model in manifest
        if model.get("baseline_status") == "TIMEOUT"
        and float(model.get("baseline_seconds", 0.0) or 0.0) >= args.minimum_baseline_seconds
        and str(model["family"]) not in excluded_families
    ]
    years = sorted({int(model["year"]) for model in eligible})
    selected = []
    selected_families: set[str] = set()
    counts: Counter[str] = Counter()
    for year in years:
        current = family_representatives([
            model for model in eligible
            if int(model["year"]) == year
            and str(model["family"]) not in selected_families
        ])
        # Primary sampling is deliberately blind to XOR features and candidate results.
        # The structural labels and matched controls are assigned only after selection.
        current = spaced(current, args.per_year)
        rich_pool = [
            model for model in current
            if float(model.get("bad_xor_density", 0.0) or 0.0) >= args.bad_xor_density
        ]
        poor_pool = [
            model for model in current
            if float(model.get("bad_xor_density", 0.0) or 0.0) < args.bad_xor_density
        ]
        match_by_id: dict[str, tuple[str, str]] = {}
        for index, (candidate, control) in enumerate(
            match_controls(rich_pool, poor_pool, args.max_and_ratio), start=1,
        ):
            match_id = f"{year}-pair-{index:02d}"
            match_by_id[str(candidate["id"])] = (match_id, str(control["id"]))
            match_by_id[str(control["id"])] = (match_id, str(candidate["id"]))
        for model in current:
            domain = (
                "aig-hard-xor-rich"
                if float(model.get("bad_xor_density", 0.0) or 0.0) >= args.bad_xor_density
                else "aig-hard-xor-poor"
            )
            match_id, matched_id = match_by_id.get(str(model["id"]), ("", ""))
            item = dict(model)
            item.update({
                "domain": domain,
                "match_id": match_id,
                "matched_model_id": matched_id,
                "selection_baseline": "fixed-AIG MC, 60-second timeout",
            })
            selected.append(item)
            selected_families.add(str(model["family"]))
            counts[f"{year}:{domain}"] += 1

    selected.sort(key=lambda model: (int(model["year"]), int(model["aig_ands"]), str(model["id"])))
    payload = {
        "version": 1,
        "description": "Preregistered family-disjoint cross-year AIG-hard BVE cohort",
        "selection_rule": {
            "hardness": (
                "baseline_status == TIMEOUT and baseline_seconds >= "
                f"{args.minimum_baseline_seconds:g} in the traditional-AIG screen"
            ),
            "primary_sampling": "within each year, size-spaced family representatives selected without reading XOR features",
            "rich_domain": f"bad_xor_density >= {args.bad_xor_density:g}",
            "control_domain": f"bad_xor_density < {args.bad_xor_density:g}",
            "matching": "post-selection only; same year; nearest log(1 + AIG AND count)",
            "maximum_aig_and_ratio": args.max_and_ratio,
            "exclusion": "all families in the supplied development selections",
            "candidate_results_read": False,
        },
        "source_manifest": str(args.manifest.resolve()),
        "excluded_selections": [str(path.resolve()) for path in args.exclude_selection],
        "per_year_limit": args.per_year,
        "counts": dict(sorted(counts.items())),
        "ids": [str(model["id"]) for model in selected],
        "models": selected,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    matched = len({model["match_id"] for model in selected if model["match_id"]})
    print(
        f"models={len(selected)} matched_pairs={matched} "
        f"families={len({model['family'] for model in selected})} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
