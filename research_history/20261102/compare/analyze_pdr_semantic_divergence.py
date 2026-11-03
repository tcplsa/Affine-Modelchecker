#!/usr/bin/env python3
"""Locate the first semantic PDR trajectory divergence in paired traces."""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import Counter, defaultdict
from pathlib import Path


PAIR_FIELDS = [
    "model_id", "name", "year", "tier", "representation", "run",
    "first_status", "numeric_status", "first_seconds", "numeric_seconds",
    "first_events", "numeric_events", "common_prefix", "divergence_class",
    "first_capped", "numeric_capped",
    "first_event", "numeric_event", "query_kind", "frame",
    "first_hash", "numeric_hash", "prefix_first_conflicts",
    "prefix_numeric_conflicts",
]
SIGNATURE_FIELDS = (
    "event", "role", "kind", "frame", "depth", "input_size", "output_size",
    "literal_hash", "result", "queue_size",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--trace-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pairs-output", type=Path)
    return parser.parse_args()


def read_trace(root: Path, trace_key: str) -> list[dict[str, str]]:
    directory = root / trace_key
    paths = sorted(path for path in directory.glob("*.semantic.tsv") if path.stat().st_size > 0)
    if not paths:
        return []
    with paths[0].open(encoding="utf-8", newline="", errors="replace") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def signature(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(row.get(field, "") for field in SIGNATURE_FIELDS)


def classify(left: dict[str, str] | None, right: dict[str, str] | None) -> str:
    if left is None or right is None:
        return "prefix-length"
    if left["event"] != right["event"]:
        return "control-flow"
    event = left["event"]
    if event.startswith("state-"):
        return "sat-model"
    if event == "core":
        return "unsat-core"
    if event == "obligation":
        return "obligation"
    if event.startswith("generalize"):
        return "generalization"
    if event == "lemma":
        return "lemma"
    if event == "query":
        if left["kind"] != right["kind"] or left["frame"] != right["frame"]:
            return "query-kind"
        if left["literal_hash"] != right["literal_hash"]:
            return "query-cube"
        if left["result"] != right["result"]:
            return "query-result"
        return "query-context"
    return event


def previous_query(rows: list[dict[str, str]], index: int) -> tuple[str, str]:
    for row in reversed(rows[:index + 1]):
        if row["event"] == "query":
            return row["kind"], row["frame"]
    return "", ""


def main() -> int:
    args = parse_args()
    with args.summary.open(encoding="utf-8", newline="") as handle:
        summary = list(csv.DictReader(handle, delimiter="\t"))
    cells = {(row["model_id"], row["representation"], row["origin"]): row for row in summary}
    identities = sorted({(row["model_id"], row["representation"]) for row in summary})
    pairs = []
    for model_id, representation in identities:
        first = cells.get((model_id, representation, "first__first"))
        numeric = cells.get((model_id, representation, "numeric__first"))
        if first is None or numeric is None:
            continue
        left = read_trace(args.trace_root, first["trace_key"])
        right = read_trace(args.trace_root, numeric["trace_key"])
        if not left or not right:
            continue
        limit = min(len(left), len(right))
        index = 0
        while index < limit and signature(left[index]) == signature(right[index]):
            index += 1
        left_event = left[index] if index < len(left) else None
        right_event = right[index] if index < len(right) else None
        if index == len(left) == len(right):
            divergence = "censored-exact" if first["semantic_capped"] == "1" or numeric["semantic_capped"] == "1" else "exact"
        else:
            divergence = classify(left_event, right_event)
        kind, frame = previous_query(left, min(index, len(left) - 1))
        prefix_first_conflicts = sum(
            int(row["conflicts"] or 0) for row in left[:index] if row["event"] == "query"
        )
        prefix_numeric_conflicts = sum(
            int(row["conflicts"] or 0) for row in right[:index] if row["event"] == "query"
        )
        pairs.append({
            "model_id": model_id, "name": first["name"], "year": first["year"],
            "tier": first["tier"], "representation": representation,
            "run": first["run"], "first_status": first["status"],
            "numeric_status": numeric["status"], "first_seconds": first["wall_seconds"],
            "numeric_seconds": numeric["wall_seconds"], "first_events": str(len(left)),
            "numeric_events": str(len(right)), "common_prefix": str(index),
            "divergence_class": divergence,
            "first_capped": first["semantic_capped"],
            "numeric_capped": numeric["semantic_capped"],
            "first_event": "" if left_event is None else left_event["event"],
            "numeric_event": "" if right_event is None else right_event["event"],
            "query_kind": kind, "frame": frame,
            "first_hash": "" if left_event is None else left_event["literal_hash"],
            "numeric_hash": "" if right_event is None else right_event["literal_hash"],
            "prefix_first_conflicts": str(prefix_first_conflicts),
            "prefix_numeric_conflicts": str(prefix_numeric_conflicts),
        })

    pairs_output = args.pairs_output or args.output.with_name(args.output.stem + "_pairs.tsv")
    pairs_output.parent.mkdir(parents=True, exist_ok=True)
    with pairs_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PAIR_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(pairs)

    lines = [
        "# PDR Semantic Divergence",
        "",
        f"Summary rows: {len(summary)}; complete trace pairs: {len(pairs)}.",
        "",
        "## First divergence",
        "",
        "| Representation | Pairs | Exact | Censored exact | Median common events | Model | Core | Query cube | Control flow | Prefix length |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for representation in sorted({row["representation"] for row in pairs}):
        group = [row for row in pairs if row["representation"] == representation]
        classes = Counter(row["divergence_class"] for row in group)
        prefixes = [int(row["common_prefix"]) for row in group]
        lines.append(
            f"| {representation} | {len(group)} | {classes['exact']} | {classes['censored-exact']} | "
            f"{statistics.median(prefixes):.1f} | {classes['sat-model']} | "
            f"{classes['unsat-core']} | {classes['query-cube']} | "
            f"{classes['control-flow'] + classes['query-kind']} | {classes['prefix-length']} |"
        )

    lines += [
        "",
        "## Divergence causes",
        "",
        "| Representation | Class | Count | Most common preceding query kinds |",
        "|---|---|---:|---|",
    ]
    for representation in sorted({row["representation"] for row in pairs}):
        group = [row for row in pairs if row["representation"] == representation]
        for divergence, count in Counter(row["divergence_class"] for row in group).most_common():
            kinds = Counter(
                row["query_kind"] for row in group
                if row["divergence_class"] == divergence and row["query_kind"]
            )
            description = ", ".join(f"{kind}:{amount}" for kind, amount in kinds.most_common(3)) or "n/a"
            lines.append(f"| {representation} | {divergence} | {count} | {description} |")

    lines += [
        "",
        "## Paired outcomes",
        "",
        "| Representation | First solved | Numeric solved | Outcome conflicts | First total s | Numeric total s |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    solved = {"SAFE", "UNSAFE"}
    for representation in sorted({row["representation"] for row in pairs}):
        group = [row for row in pairs if row["representation"] == representation]
        first_solved = sum(row["first_status"] in solved for row in group)
        numeric_solved = sum(row["numeric_status"] in solved for row in group)
        conflicts = sum(
            row["first_status"] in solved and row["numeric_status"] in solved
            and row["first_status"] != row["numeric_status"] for row in group
        )
        lines.append(
            f"| {representation} | {first_solved}/{len(group)} | {numeric_solved}/{len(group)} | "
            f"{conflicts} | {sum(float(row['first_seconds']) for row in group):.2f} | "
            f"{sum(float(row['numeric_seconds']) for row in group):.2f} |"
        )

    lines += [
        "",
        "## Earliest examples",
        "",
        "| Representation | Model | Class | Common events | Query kind | Frame |",
        "|---|---|---|---:|---|---:|",
    ]
    for row in sorted(pairs, key=lambda item: int(item["common_prefix"]))[:20]:
        lines.append(
            f"| {row['representation']} | {row['model_id']} | {row['divergence_class']} | "
            f"{row['common_prefix']} | {row['query_kind'] or 'n/a'} | {row['frame'] or '-1'} |"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.output)
    print(pairs_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
