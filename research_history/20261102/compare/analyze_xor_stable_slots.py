#!/usr/bin/env python3
"""Compare compact and stable-slot numbering for matched XOR allowlists."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


def read(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {(row["variant"], row["run"]): row for row in csv.DictReader(handle, delimiter="\t")}


def solved(row: dict[str, str]) -> bool:
    return row["status"] in {"SAFE", "UNSAFE"}


def cost(row: dict[str, str], penalty: float) -> float:
    return float(row["wall_seconds"]) if solved(row) else penalty


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--compact", required=True, type=Path)
    parser.add_argument("--stable", required=True, type=Path)
    parser.add_argument("--penalty", type=float, default=900.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    compact, stable = read(args.compact), read(args.stable)
    keys = sorted(set(compact) & set(stable))
    by_variant: dict[str, list[tuple[dict[str, str], dict[str, str]]]] = defaultdict(list)
    for key in keys:
        by_variant[key[0]].append((compact[key], stable[key]))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    variants = {v["id"]: v for v in manifest["models"][0]["variants"]}

    lines = [
        "# XOR Stable-Slot Ablation",
        "",
        f"Matched runs: {len(keys)} / expected {len(variants) * 4}",
        "",
        "| Variant | Role | Compact solved | Stable solved | Compact median | Stable median | Stable/compact |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    compact_wins = stable_wins = ties = 0
    compact_total = stable_total = 0.0
    for variant_id in sorted(by_variant):
        pairs = by_variant[variant_id]
        compact_values = [cost(pair[0], args.penalty) for pair in pairs]
        stable_values = [cost(pair[1], args.penalty) for pair in pairs]
        compact_median = statistics.median(compact_values)
        stable_median = statistics.median(stable_values)
        compact_total += sum(compact_values)
        stable_total += sum(stable_values)
        if stable_median + 2 < compact_median:
            stable_wins += 1
        elif compact_median + 2 < stable_median:
            compact_wins += 1
        else:
            ties += 1
        role = variants[variant_id].get("selection_role", "")
        lines.append(
            f"| {variant_id} | {role} | {sum(solved(p[0]) for p in pairs)}/{len(pairs)} | "
            f"{sum(solved(p[1]) for p in pairs)}/{len(pairs)} | {compact_median:.2f} | "
            f"{stable_median:.2f} | {stable_median / compact_median:.3f} |"
        )
    lines.extend([
        "",
        f"Variant wins beyond 2 s: compact={compact_wins}, stable={stable_wins}, ties={ties}.",
        f"Penalized aggregate ({args.penalty:.0f} s unresolved): compact={compact_total:.2f}, "
        f"stable={stable_total:.2f}, stable/compact={stable_total / compact_total:.3f}.",
        "",
    ])
    report = "\n".join(lines)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
