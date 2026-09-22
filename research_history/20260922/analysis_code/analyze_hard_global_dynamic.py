#!/usr/bin/env python3
"""Join the 590-model static atlas with uniform MC progress telemetry."""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--static-atlas", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def numeric(value: Optional[str]) -> float:
    try:
        return float(value) if value not in {None, ""} else 0.0
    except ValueError:
        return 0.0


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = round(fraction * (len(ordered) - 1))
    return ordered[index]


def discover_prefix(fields: list[str]) -> str:
    suffix = "_status"
    candidates = [field[:-len(suffix)] for field in fields if field.endswith(suffix)]
    if len(candidates) != 1:
        raise ValueError(f"expected one config in progress TSV, found {candidates}")
    return candidates[0]


def main() -> int:
    args = parse_args()
    with args.static_atlas.open(encoding="utf-8", newline="") as source:
        static = {row["model_id"]: row for row in csv.DictReader(source, delimiter="\t")}
    with args.progress.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source, delimiter="\t")
        progress = list(reader)
        prefix = discover_prefix(reader.fieldnames or [])

    def stat(row: dict[str, str], name: str) -> float:
        return numeric(row.get(f"{prefix}_{name}"))

    joined: list[dict[str, Any]] = []
    for row in progress:
        base = static[row["model_id"]]
        queries = stat(row, "queries")
        depth = stat(row, "pdr_depth")
        joined.append({
            **base,
            "status": row[f"{prefix}_status"],
            "runtime": stat(row, "pdr_runtime"),
            "depth": depth,
            "active_query": row.get(f"{prefix}_active_query", ""),
            "queries": queries,
            "cti": stat(row, "cti"),
            "mic": stat(row, "mic"),
            "push": stat(row, "push"),
            "lemma_added": stat(row, "lemma_added"),
            "frame_core_literals": stat(row, "frame_core_literals"),
            "frame_core_input_literals": stat(row, "frame_core_input_literals"),
            "frame_conflicts": stat(row, "frame_sat_conflicts"),
            "frame_decisions": stat(row, "frame_sat_decisions"),
            "frame_propagations": stat(row, "frame_sat_propagations"),
            "lift_conflicts": stat(row, "lift_sat_conflicts"),
            "init_conflicts": stat(row, "init_sat_conflicts"),
            "queries_per_second": queries / max(1.0, stat(row, "pdr_runtime")),
            "cti_per_depth": stat(row, "cti") / max(1.0, depth),
            "mic_per_depth": stat(row, "mic") / max(1.0, depth),
            "push_per_depth": stat(row, "push") / max(1.0, depth),
            "frame_conflicts_per_query": stat(row, "frame_sat_conflicts") / max(1.0, queries),
            "frame_propagations_per_query": stat(row, "frame_sat_propagations") / max(1.0, queries),
        })

    unsolved = [row for row in joined if row["status"] not in {"SAFE", "UNSAFE"}]
    thresholds = {
        "depth_low": percentile([row["depth"] for row in unsolved], 0.25),
        "depth_high": percentile([row["depth"] for row in unsolved], 0.75),
        "queries_low": percentile([row["queries"] for row in unsolved], 0.20),
        "queries_high": percentile([row["queries"] for row in unsolved], 0.75),
        "cti_depth_high": percentile([row["cti_per_depth"] for row in unsolved], 0.75),
        "mic_depth_high": percentile([row["mic_per_depth"] for row in unsolved], 0.75),
        "push_depth_high": percentile([row["push_per_depth"] for row in unsolved], 0.75),
        "conflict_query_high": percentile(
            [row["frame_conflicts_per_query"] for row in unsolved], 0.75
        ),
    }

    signature_counts: Counter[str] = Counter()
    signature_families: dict[str, Counter[str]] = defaultdict(Counter)
    for row in joined:
        labels: list[str] = []
        if row["status"] in {"SAFE", "UNSAFE"}:
            labels.append("solved")
        else:
            if row["depth"] <= 0 or row["queries"] <= thresholds["queries_low"]:
                labels.append("front-end-or-few-query")
            if (row["depth"] <= thresholds["depth_low"]
                    and (row["cti_per_depth"] >= thresholds["cti_depth_high"]
                         or row["mic_per_depth"] >= thresholds["mic_depth_high"])):
                labels.append("early-obligation-generalization")
            if row["frame_conflicts_per_query"] >= thresholds["conflict_query_high"]:
                labels.append("sat-heavy-query")
            if (row["depth"] >= thresholds["depth_high"]
                    and row["push_per_depth"] >= thresholds["push_depth_high"]):
                labels.append("push-convergence")
            if row["queries"] >= thresholds["queries_high"]:
                labels.append("high-query-volume")
            if not labels:
                labels.append("mixed-middle")
        row["failure_labels"] = ",".join(labels)
        for label in labels:
            signature_counts[label] += 1
            signature_families[label][row["family"]] += 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    fields = list(joined[0])
    with (args.output_dir / "dynamic_model_atlas.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as target:
        writer = csv.DictWriter(target, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(joined)

    lines = [
        "# Global dynamic atlas of stock-rIC3-3600 hard models",
        "",
        f"Completed progress rows: {len(joined)}/{len(static)}.",
        f"Solved inside the diagnostic budget: {signature_counts['solved']}.",
        "",
        "Labels are overlapping failure signatures derived from global quartiles. They are",
        "used to choose experiments, not presented as semantic ground truth.",
        "",
        "## Thresholds",
        "",
    ]
    for name, value in thresholds.items():
        lines.append(f"- `{name}`: {value:.3f}")
    lines.extend([
        "",
        "## Failure signatures",
        "",
        "| Signature | Models | Largest contributing families |",
        "| --- | ---: | --- |",
    ])
    for label, count in signature_counts.most_common():
        families = ", ".join(
            f"{family}:{number}" for family, number in signature_families[label].most_common(6)
        )
        lines.append(f"| `{label}` | {count} | {families} |")

    lines.extend([
        "",
        "## Research routing",
        "",
        "| Signature | First controlled intervention |",
        "| --- | --- |",
        "| `front-end-or-few-query` | preprocessing, BMC0/first-pre SAT backend, query presentation |",
        "| `early-obligation-generalization` | obligation order, MIC literal order, CTG selection |",
        "| `sat-heavy-query` | selective native XOR/CMSat, abstraction, phase/model control |",
        "| `push-convergence` | lemma strength/priority, push policy, invariant templates |",
        "| `high-query-volume` | lemma reuse/sharing and duplicate-query suppression |",
        "",
        "A candidate is tested first on several families inside one signature and then on",
        "held-out families from that signature. Filename- or family-specific dispatch is not",
        "accepted as the final mechanism.",
    ])
    (args.output_dir / "dynamic_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(f"rows={len(joined)} signatures={dict(signature_counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
