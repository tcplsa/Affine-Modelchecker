#!/usr/bin/env python3
"""Summarize MC_PDR_SEMANTIC_TRACE_DIR event streams for PDR diagnosis."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


def mean(values: list[int]) -> str:
    return f"{sum(values) / len(values):.2f}" if values else ""


def summarize(path: Path) -> dict[str, str]:
    events: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    result_counts: Counter[str] = Counter()
    sizes: dict[str, list[int]] = defaultdict(list)
    query_costs: dict[str, list[int]] = defaultdict(list)
    hashes: dict[str, Counter[str]] = defaultdict(Counter)

    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            event = row["event"]
            events[event] += 1
            roles[row["role"]] += 1
            kinds[row["kind"]] += 1
            result_counts[f"{event}:{row['result']}"] += 1
            try:
                size = int(row["output_size"])
            except ValueError:
                size = -1
            if size >= 0:
                sizes[event].append(size)
            literal_hash = row["literal_hash"]
            if literal_hash != "0":
                hashes[event][literal_hash] += 1
            if event == "query":
                try:
                    query_costs[row["kind"]].append(int(row["conflicts"]))
                except ValueError:
                    pass

    summary: dict[str, str] = {
        "trace": str(path),
        "events": str(sum(events.values())),
        "queries": str(events["query"]),
        "cores": str(events["core"]),
        "generalizations": str(events["generalize-after"]),
        "lemmas": str(events["lemma"]),
        "obligations": str(events["obligation"]),
        "mean_core_size": mean(sizes["core"]),
        "mean_generalized_cube": mean(sizes["generalize-after"]),
        "mean_lemma_size": mean(sizes["lemma"]),
        "event_kinds": ";".join(f"{name}:{count}" for name, count in sorted(kinds.items())),
        "query_results": ";".join(
            f"{name}:{count}" for name, count in sorted(result_counts.items()) if name.startswith("query:")),
        "mean_conflicts_by_query": ";".join(
            f"{name}:{mean(values)}" for name, values in sorted(query_costs.items())),
        "repeated_core_hashes": str(sum(1 for count in hashes["core"].values() if count > 1)),
        "repeated_lemma_hashes": str(sum(1 for count in hashes["lemma"].values() if count > 1)),
        "unique_core_hashes": str(len(hashes["core"])),
        "unique_lemma_hashes": str(len(hashes["lemma"])),
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    paths = []
    for item in args.paths:
        paths.extend(sorted(item.rglob("*.semantic.tsv")) if item.is_dir() else [item])
    rows = [summarize(path) for path in paths]
    writer = csv.DictWriter(__import__("sys").stdout,
                            fieldnames=list(rows[0]) if rows else [], delimiter="\t")
    if rows:
        writer.writeheader()
        writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
