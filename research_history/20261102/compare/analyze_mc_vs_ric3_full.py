#!/usr/bin/env python3
"""Compare optimized four-lane MC with stock and optimized four-core rIC3."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from analyze_bve_full_campaign import fmt, pair_stats


PAIRS = (
    ("mc_best", "ric3_stock", "MC XAG sum-high vs rIC3 Native legacy"),
    ("mc_best", "ric3_local", "MC XAG sum-high vs rIC3 Native-local"),
    ("ric3_local", "ric3_stock", "rIC3 Native-local vs Native legacy"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mc", nargs="+", required=True, type=Path)
    parser.add_argument("--ric3", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bootstrap", type=int, default=10000)
    return parser.parse_args()


def load(paths: list[Path]) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = row.get("model_id") or f"{row.get('year', '')}::{row['name']}"
                if key in rows:
                    raise ValueError(f"duplicate model {key} in {path}")
                rows[key] = row
    return rows


def merge_rows(
    mc_rows: dict[str, dict[str, str]], ric3_rows: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    merged = []
    for key in sorted(mc_rows.keys() & ric3_rows.keys()):
        mc = mc_rows[key]
        ric3 = ric3_rows[key]
        merged.append({
            "name": mc["name"],
            "model_id": key,
            "family": mc.get("family", key),
            "year": mc.get("year", ""),
            "group": mc.get("group", ""),
            "timeout_seconds": mc["timeout_seconds"],
            "mc_best_status": mc["xag_best4_status"],
            "mc_best_wall_seconds": mc["xag_best4_wall_seconds"],
            "ric3_stock_status": ric3["native_legacy4_status"],
            "ric3_stock_wall_seconds": ric3["native_legacy4_wall_seconds"],
            "ric3_local_status": ric3["native_local4_status"],
            "ric3_local_wall_seconds": ric3["native_local4_wall_seconds"],
        })
    return merged


def table(lines: list[str], rows: list[dict[str, str]], bootstrap: int) -> None:
    lines += [
        "| Comparison | Solved candidate/reference | Only/lost | Common | "
        "Geo ratio (95% family-cluster CI) | Median | W/L >2s | PAR ratio |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for candidate, reference, label in PAIRS:
        stats = pair_stats(rows, candidate, reference, bootstrap)
        lines.append(
            f"| {label} | {stats['candidate_solved']}/{stats['reference_solved']} | "
            f"{stats['only']}/{stats['lost']} | {stats['common']} | {fmt(stats['geo'])} "
            f"[{fmt(stats['ci_low'])}, {fmt(stats['ci_high'])}] | {fmt(stats['median'])} | "
            f"{stats['wins']}/{stats['losses']} | {fmt(stats['cost_ratio'])} |"
        )


def main() -> int:
    args = parse_args()
    rows = merge_rows(load(args.mc), load(args.ric3))
    lines = [
        "# Four-core MC versus rIC3", "",
        f"Exact matched models: {len(rows)}.", "",
        "Both tools use four logical solver workers and a 1,800-second limit. Ratios below "
        "1.0 favor the first tool named in a comparison. Pairs unsolved by both are omitted "
        "from PAR-1.5.", "",
        "## Overall", "",
    ]
    table(lines, rows, args.bootstrap)
    for field, title in (("year", "Year"), ("group", "Historical tier")):
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            grouped[row.get(field, "unknown")].append(row)
        lines += ["", f"## MC versus stock rIC3 by {title.lower()}", "",
                  f"| {title} | Models | MC/rIC3 solved | MC only/lost | Common | Geo ratio | PAR ratio |",
                  "|---|---:|---:|---:|---:|---:|---:|"]
        for key in sorted(grouped):
            stats = pair_stats(grouped[key], "mc_best", "ric3_stock", 1000)
            lines.append(
                f"| {key} | {stats['models']} | {stats['candidate_solved']}/{stats['reference_solved']} | "
                f"{stats['only']}/{stats['lost']} | {stats['common']} | {fmt(stats['geo'])} | "
                f"{fmt(stats['cost_ratio'])} |"
            )
    lines.append("")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"matched={len(rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
