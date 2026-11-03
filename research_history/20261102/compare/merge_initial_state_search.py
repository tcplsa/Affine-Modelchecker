#!/usr/bin/env python3
"""Merge exact initial-state designs while normalizing cross-run timing noise."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}
TIME_SUFFIXES = (
    "_wall_seconds",
    "_pdr_runtime",
    "_input_order_runtime",
    "_conversion_runtime",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge initial-state searches as distinct exact states."
    )
    parser.add_argument("--results", type=Path, nargs="+", required=True)
    parser.add_argument("--designs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--design-output", type=Path)
    parser.add_argument("--baseline", default="state_000")
    parser.add_argument(
        "--no-normalize-baseline",
        action="store_true",
        help="do not scale each run to the first run's per-circuit baseline",
    )
    return parser.parse_args()


def read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader.fieldnames or ()), list(reader)


def number(row: dict[str, str], key: str) -> float | None:
    try:
        return float(row.get(key, ""))
    except (TypeError, ValueError):
        return None


def baseline_scale(
    reference: dict[str, str],
    source: dict[str, str],
    baseline: str,
) -> float:
    if (
        reference.get(f"{baseline}_status") not in SOLVED
        or source.get(f"{baseline}_status") not in SOLVED
    ):
        return 1.0
    ref_time = number(reference, f"{baseline}_pdr_runtime")
    source_time = number(source, f"{baseline}_pdr_runtime")
    if ref_time is None or source_time is None or source_time <= 0.0:
        return 1.0
    return ref_time / source_time


def scaled_value(key: str, value: str, scale: float) -> str:
    if not key.endswith(TIME_SUFFIXES):
        return value
    try:
        return f"{float(value) * scale:.6f}"
    except (TypeError, ValueError):
        return value


def main() -> int:
    args = parse_args()
    if len(args.results) != len(args.designs):
        raise SystemExit("--results and --designs must have the same length")
    if len(args.results) < 2:
        raise SystemExit("at least two result/design pairs are required")

    runs = []
    common_names: set[str] | None = None
    for index, (results_path, design_path) in enumerate(
        zip(args.results, args.designs), start=1
    ):
        fields, rows = read_tsv(results_path)
        by_name = {row["name"]: row for row in rows}
        design = json.loads(design_path.read_text(encoding="utf-8"))
        configs = design.get("configs", [])
        config_ids = [config["id"] for config in configs]
        if args.baseline not in config_ids:
            raise SystemExit(f"{results_path}: missing baseline {args.baseline}")
        common_names = (
            set(by_name) if common_names is None else common_names & set(by_name)
        )
        runs.append({
            "tag": f"d{index}",
            "results": str(results_path),
            "design": str(design_path),
            "fields": fields,
            "rows": rows,
            "by_name": by_name,
            "metadata": design,
            "configs": configs,
        })

    names = common_names or set()
    if not names:
        raise SystemExit("input runs have no common benchmarks")
    first_rows = runs[0]["rows"]
    ordered_names = [row["name"] for row in first_rows if row["name"] in names]
    metadata_fields = [
        field for field in runs[0]["fields"]
        if not any(field.startswith(config["id"] + "_") for config in runs[0]["configs"])
        and field not in {"winner", "winner_seconds", "outcome_conflict"}
    ]

    output_fields = list(metadata_fields)
    merged_configs = []
    mappings: list[tuple[dict, dict[str, str]]] = []
    for run in runs:
        mapping = {}
        for config in run["configs"]:
            old_id = config["id"]
            new_id = f"{run['tag']}_{old_id}"
            mapping[old_id] = new_id
            copied = dict(config)
            copied["id"] = new_id
            copied["label"] = f"{run['tag']} {config.get('label', old_id)}"
            copied["source_results"] = run["results"]
            copied["source_design"] = run["design"]
            copied["source_state_id"] = old_id
            merged_configs.append(copied)
            for field in run["fields"]:
                if field.startswith(old_id + "_"):
                    output_fields.append(new_id + field[len(old_id):])
        mappings.append((run, mapping))

    merged_rows = []
    reference_run = runs[0]
    for name in ordered_names:
        reference = reference_run["by_name"][name]
        merged = {field: reference.get(field, "") for field in metadata_fields}
        for run, mapping in mappings:
            source = run["by_name"][name]
            scale = (
                1.0
                if args.no_normalize_baseline
                else baseline_scale(reference, source, args.baseline)
            )
            for old_id, new_id in mapping.items():
                for field, value in source.items():
                    if not field.startswith(old_id + "_"):
                        continue
                    new_field = new_id + field[len(old_id):]
                    merged[new_field] = scaled_value(new_field, value, scale)
        merged_rows.append(merged)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(merged_rows)

    design_output = args.design_output or args.output.with_name(
        args.output.stem + "_design.json"
    )
    design_output.write_text(
        json.dumps(
            {
                "kind": "merged_exact_initial_states",
                "normalized_to_first_baseline": not args.no_normalize_baseline,
                "baseline": f"d1_{args.baseline}",
                "models": len(merged_rows),
                "sources": [
                    {
                        "tag": run["tag"],
                        "results": run["results"],
                        "design": run["design"],
                    }
                    for run in runs
                ],
                "configs": merged_configs,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"models\t{len(merged_rows)}")
    print(f"states\t{len(merged_configs)}")
    print(f"output\t{args.output}")
    print(f"design_output\t{design_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
