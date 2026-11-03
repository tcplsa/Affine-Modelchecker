#!/usr/bin/env python3
"""Aggregate per-XOR structural distributions without writing a gate table."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import glob
import math
from pathlib import Path

from extract_xor_gate_features import rows_for_model


META = {"name", "aig_path", "year", "family"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-pattern", required=True)
    parser.add_argument("--structure-files", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--support-limit", type=int, default=128)
    parser.add_argument("--require-any-solved", action="store_true")
    return parser.parse_args()


def number(row: dict[str, str], key: str) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return 0.0


def quantile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    left = int(math.floor(position))
    right = int(math.ceil(position))
    if left == right:
        return ordered[left]
    return ordered[left] * (right - position) + ordered[right] * (position - left)


def ratio(rows: list[dict[str, str]], predicate) -> float:
    return sum(bool(predicate(row)) for row in rows) / len(rows) if rows else 0.0


def summarize_values(result: dict[str, float], prefix: str, values: list[float]) -> None:
    result[prefix + "_mean"] = sum(values) / len(values) if values else 0.0
    result[prefix + "_median"] = quantile(values, 0.5)
    result[prefix + "_p90"] = quantile(values, 0.9)
    result[prefix + "_max"] = max(values) if values else 0.0


def aggregate(path_text: str, support_limit: int) -> dict[str, object]:
    path = Path(path_text)
    rows = rows_for_model(path, support_limit)
    if not rows:
        return {"name": path.stem, "aig_path": str(path), "gate_xor_count": 0}
    first = rows[0]
    next_rows = [row for row in rows if row["in_next"] == "1"]
    bad_rows = [row for row in rows if row["in_bad"] == "1"]
    f23 = [row for row in next_rows if 2 <= int(row["fanout"]) < 4]
    valid_support = [row for row in rows if row["support_truncated"] == "0"]
    result: dict[str, object] = {
        "name": path.stem,
        "aig_path": str(path),
        "gate_xor_count": len(rows),
        "gate_xor_to_and": len(rows) / max(int(first["circuit_ands"]), 1),
        "gate_next_ratio": len(next_rows) / len(rows),
        "gate_bad_ratio": len(bad_rows) / len(rows),
        "gate_shared_ratio": ratio(rows, lambda row: row["cone_class"] == "shared"),
        "gate_next_only_ratio": ratio(rows, lambda row: row["cone_class"] == "next-only"),
        "gate_bad_only_ratio": ratio(rows, lambda row: row["cone_class"] == "bad-only"),
        "gate_outside_ratio": ratio(rows, lambda row: row["cone_class"] == "outside"),
        "gate_reused_impl_ratio": ratio(rows, lambda row: int(row["impl_child_external_fanouts"]) > 0),
        "gate_adjacent_xor_ratio": ratio(rows, lambda row: int(row["fanin_xor_count"]) + int(row["fanout_xor_count"]) > 0),
        "gate_support_overlap_ratio": ratio(valid_support, lambda row: int(row["support_overlap"]) > 0),
        "gate_support_truncated_ratio": ratio(rows, lambda row: row["support_truncated"] == "1"),
        "gate_direct_next_ratio": ratio(rows, lambda row: row["direct_next_root"] == "1"),
        "gate_direct_bad_ratio": ratio(rows, lambda row: row["direct_bad_root"] == "1"),
        "gate_sign00_ratio": ratio(rows, lambda row: row["fanin0_sign"] == "0" and row["fanin1_sign"] == "0"),
        "gate_sign11_ratio": ratio(rows, lambda row: row["fanin0_sign"] == "1" and row["fanin1_sign"] == "1"),
        "next_fanout_0_1_ratio": ratio(next_rows, lambda row: int(row["fanout"]) < 2),
        "next_fanout_2_3_ratio": ratio(next_rows, lambda row: 2 <= int(row["fanout"]) < 4),
        "next_fanout_4_5_ratio": ratio(next_rows, lambda row: 4 <= int(row["fanout"]) < 6),
        "next_fanout_ge6_ratio": ratio(next_rows, lambda row: int(row["fanout"]) >= 6),
        "f23_to_all_xor_ratio": len(f23) / len(rows),
        "f23_to_next_xor_ratio": len(f23) / len(next_rows) if next_rows else 0.0,
        "f23_shared_ratio": ratio(f23, lambda row: row["cone_class"] == "shared"),
        "f23_near_ratio": ratio(f23, lambda row: 0 <= int(row["distance_to_next"]) <= 8),
        "f23_reused_impl_ratio": ratio(f23, lambda row: int(row["impl_child_external_fanouts"]) > 0),
        "f23_deep_ratio": ratio(f23, lambda row: float(row["relative_depth"]) > 0.5),
        "f23_adjacent_ratio": ratio(f23, lambda row: int(row["fanin_xor_count"]) + int(row["fanout_xor_count"]) > 0),
        "f23_support_overlap_ratio": ratio(
            [row for row in f23 if row["support_truncated"] == "0"],
            lambda row: int(row["support_overlap"]) > 0,
        ),
    }
    summarize_values(result, "gate_fanout", [number(row, "fanout") for row in rows])
    summarize_values(result, "gate_relative_depth", [number(row, "relative_depth") for row in rows])
    summarize_values(result, "gate_support_jaccard", [number(row, "support_jaccard") for row in valid_support])
    summarize_values(result, "next_distance", [number(row, "distance_to_next") for row in next_rows])
    summarize_values(result, "next_fanout", [number(row, "fanout") for row in next_rows])
    return result


def main() -> int:
    args = parse_args()
    if args.workers <= 0 or args.support_limit <= 0:
        raise SystemExit("workers and support-limit must be positive")
    wanted: set[tuple[str, str]] = set()
    for path in glob.glob(args.results_pattern):
        with open(path, "r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if args.require_any_solved and not any(
                    key.endswith("_status") and value in {"SAFE", "UNSAFE"}
                    for key, value in row.items()
                ):
                    continue
                wanted.add((row.get("year", ""), row["name"]))
    models: dict[tuple[str, str], tuple[str, str]] = {}
    for structure_path in args.structure_files:
        with structure_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = (row.get("year", "") or structure_path.stem[-4:], row["name"])
                if key in wanted:
                    models[key] = (row["aig_path"], row.get("family", row["name"]))
    tasks = [(year, name, path, family) for (year, name), (path, family) in sorted(models.items())]
    output_rows = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(aggregate, path, args.support_limit): (year, name, family)
            for year, name, path, family in tasks
        }
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            year, name, family = futures[future]
            row = future.result()
            row.update({"year": year, "name": name, "family": family})
            output_rows.append(row)
            if index % 20 == 0 or index == len(futures):
                print(f"completed={index}/{len(futures)}", flush=True)
    output_rows.sort(key=lambda row: (str(row["year"]), str(row["name"])))
    fieldnames = ["year", "name", "family", "aig_path"] + sorted(
        set().union(*(set(row) for row in output_rows)) - META
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(output_rows)
    print(f"models={len(output_rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
