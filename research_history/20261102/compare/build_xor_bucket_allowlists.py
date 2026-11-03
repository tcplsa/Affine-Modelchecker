#!/usr/bin/env python3
"""Build deterministic XOR-only and XOR-complement interventions."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict


Row = Dict[str, str]
Predicate = Callable[[Row], bool]


def integer(row: Row, key: str) -> int:
    return int(row[key])


def in_fanout_2_3(row: Row) -> bool:
    return integer(row, "in_next") == 1 and 2 <= integer(row, "fanout") < 4


BUCKETS: dict[str, Predicate] = {
    "next_fanout_0_1": lambda row: integer(row, "in_next") == 1 and integer(row, "fanout") < 2,
    "next_fanout_2_3": lambda row: integer(row, "in_next") == 1 and 2 <= integer(row, "fanout") < 4,
    "next_fanout_4_5": lambda row: integer(row, "in_next") == 1 and 4 <= integer(row, "fanout") < 6,
    "next_fanout_ge6": lambda row: integer(row, "in_next") == 1 and integer(row, "fanout") >= 6,
    "next_only": lambda row: row["cone_class"] == "next-only",
    "shared": lambda row: row["cone_class"] == "shared",
    "outside_next": lambda row: integer(row, "in_next") == 0,
    "next_near_root": lambda row: integer(row, "in_next") == 1 and 0 <= integer(row, "distance_to_next") <= 8,
    "next_far_root": lambda row: integer(row, "distance_to_next") > 8,
    "private_impl": lambda row: integer(row, "impl_child_external_fanouts") == 0,
    "reused_impl": lambda row: integer(row, "impl_child_external_fanouts") > 0,
    "support_disjoint": lambda row: integer(row, "support_overlap") == 0 and integer(row, "support_truncated") == 0,
    "support_overlap": lambda row: integer(row, "support_overlap") > 0 and integer(row, "support_truncated") == 0,
    "f23_next_only": lambda row: in_fanout_2_3(row) and row["cone_class"] == "next-only",
    "f23_shared": lambda row: in_fanout_2_3(row) and row["cone_class"] == "shared",
    "f23_near": lambda row: in_fanout_2_3(row) and 0 <= integer(row, "distance_to_next") <= 8,
    "f23_far": lambda row: in_fanout_2_3(row) and integer(row, "distance_to_next") > 8,
    "f23_private_impl": lambda row: in_fanout_2_3(row) and integer(row, "impl_child_external_fanouts") == 0,
    "f23_reused_impl": lambda row: in_fanout_2_3(row) and integer(row, "impl_child_external_fanouts") > 0,
    "f23_shallow": lambda row: in_fanout_2_3(row) and float(row["relative_depth"]) <= 0.5,
    "f23_deep": lambda row: in_fanout_2_3(row) and float(row["relative_depth"]) > 0.5,
    "f23_isolated": lambda row: in_fanout_2_3(row) and integer(row, "fanin_xor_count") + integer(row, "fanout_xor_count") == 0,
    "f23_adjacent": lambda row: in_fanout_2_3(row) and integer(row, "fanin_xor_count") + integer(row, "fanout_xor_count") > 0,
    "f23_support_disjoint": lambda row: in_fanout_2_3(row) and integer(row, "support_overlap") == 0 and integer(row, "support_truncated") == 0,
    "f23_support_overlap": lambda row: in_fanout_2_3(row) and integer(row, "support_overlap") > 0 and integer(row, "support_truncated") == 0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--buckets", nargs="+", choices=sorted(BUCKETS),
        default=[
            "next_fanout_0_1", "next_fanout_2_3",
            "next_fanout_4_5", "next_fanout_ge6",
        ],
    )
    parser.add_argument("--modes", nargs="+", choices=["only", "except"], default=["only", "except"])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    by_model: dict[str, list[Row]] = defaultdict(list)
    with args.features.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            by_model[row["name"]].append(row)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for name, rows in sorted(by_model.items()):
        all_vars = {integer(row, "xor_var") for row in rows}
        for bucket in args.buckets:
            members = {integer(row, "xor_var") for row in rows if BUCKETS[bucket](row)}
            for mode in args.modes:
                selected = members if mode == "only" else all_vars - members
                path = args.output_dir / f"{name}__{mode}_{bucket}.allow"
                path.write_text(
                    "".join(f"{var}\n" for var in sorted(selected)),
                    encoding="ascii",
                )
                records.append({
                    "name": name,
                    "mode": mode,
                    "bucket": bucket,
                    "allowlist": str(path),
                    "selected_xors": len(selected),
                    "bucket_xors": len(members),
                    "total_xors": len(all_vars),
                })
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps({
            "version": 1,
            "features": str(args.features),
            "buckets": args.buckets,
            "modes": args.modes,
            "interventions": records,
        }, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"models={len(by_model)} interventions={len(records)} "
        f"manifest={args.manifest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
