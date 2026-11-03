#!/usr/bin/env python3
"""Promote discriminative hard-XOR screen cases to long validation runs."""

from __future__ import annotations

import argparse
import csv
import glob
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen-dir", type=Path, required=True)
    parser.add_argument("--year", required=True)
    parser.add_argument("--base-groups", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--large-gap", type=float, default=30.0)
    parser.add_argument("--max-all-timeout", type=int, default=40)
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def main() -> int:
    args = parse_args()
    result_paths = [
        Path(path) for path in sorted(glob.glob(
            str(args.screen_dir / f"hwmcc{args.year}_*_hardxor_s*.tsv")
        ))
    ]
    if not result_paths:
        raise SystemExit("no screen results found")
    by_name: dict[str, list[dict[str, str]]] = defaultdict(list)
    config_ids: set[str] = set()
    for path in result_paths:
        design_path = path.with_name(path.stem + "_design.json")
        design = json.loads(design_path.read_text(encoding="utf-8"))
        ids = {config["id"] for config in design["configs"]}
        config_ids.update(ids)
        for row in read_tsv(path):
            by_name[row["name"]].append(row)

    one_sided: set[str] = set()
    large_gap: set[str] = set()
    all_timeout: set[str] = set()
    for name, rows in by_name.items():
        ever_solved = False
        every_observation_timeout = True
        for row in rows:
            solved_costs: list[float] = []
            statuses = []
            for config_id in config_ids:
                status = row.get(f"{config_id}_status", "")
                statuses.append(status)
                if status in SOLVED:
                    ever_solved = True
                    every_observation_timeout = False
                    solved_costs.append(float(
                        row.get(f"{config_id}_wall_seconds", "0") or 0,
                    ))
                elif status != "TIMEOUT":
                    every_observation_timeout = False
            if any(status in SOLVED for status in statuses) and any(
                status == "TIMEOUT" for status in statuses
            ):
                one_sided.add(name)
            if len(solved_costs) >= 2 and max(solved_costs) - min(solved_costs) >= args.large_gap:
                large_gap.add(name)
        if not ever_solved and every_observation_timeout:
            all_timeout.add(name)

    base = json.loads(args.base_groups.read_text(encoding="utf-8"))
    base_order = (
        base.get("groups", {}).get("historical_hard_unique")
        or base.get("groups", {}).get("timeout_sample_balanced")
        or sorted(by_name)
    )
    timeout_sample = [
        name for name in base_order if name in all_timeout
    ][:args.max_all_timeout]
    promote = sorted(one_sided | large_gap | set(timeout_sample))
    groups = dict(base.get("groups", {}))
    groups.update({
        "screen_one_sided": sorted(one_sided),
        "screen_large_gap": sorted(large_gap),
        "screen_all_timeout": sorted(all_timeout),
        "screen_all_timeout_sample": timeout_sample,
        "screen_promote": promote,
    })
    output = {
        **{key: value for key, value in base.items() if key != "groups"},
        "version": 2,
        "promotion_generated_at": datetime.now(timezone.utc).isoformat(),
        "promotion_screen_dir": str(args.screen_dir),
        "promotion_large_gap": args.large_gap,
        "promotion_max_all_timeout": args.max_all_timeout,
        "counts": {name: len(values) for name, values in groups.items()},
        "groups": groups,
    }
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"year={args.year} one_sided={len(one_sided)} "
        f"large_gap={len(large_gap)} all_timeout={len(all_timeout)} "
        f"promote={len(promote)} output={args.output}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
