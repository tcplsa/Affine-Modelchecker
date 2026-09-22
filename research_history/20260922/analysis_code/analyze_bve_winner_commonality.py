#!/usr/bin/env python3
"""Compare structural features of models helped or hurt by BVE configurations."""

from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


VALID = {"SAFE", "UNSAFE"}
STATIC_FEATURES = (
    ("size_bytes", "file bytes"),
    ("aig_ands", "AIG ANDs"),
    ("recognized_xors", "recognized XORs"),
    ("and_reduction", "XAG AND reduction"),
    ("next_cone_xors", "next-cone XORs"),
    ("next_xor_density", "next-cone XOR density"),
    ("bad_cone_xors", "bad-cone XORs"),
    ("bad_xor_density", "bad-cone XOR density"),
    ("shared_cone_xors", "shared-cone XORs"),
)
PROBE_FEATURES = (
    ("lift_bve_eliminated", "eliminated variables"),
    ("lift_bve_resolvents", "resolvents"),
    ("lift_bve_resolvent_literals", "resolvent literals"),
    ("lift_bve_merge_checks", "merge checks"),
    ("lift_simplified_clauses", "output clauses"),
    ("lift_simplified_literals", "output literals"),
    ("lift_binary_clauses", "binary clauses"),
    ("lift_ternary_clauses", "ternary clauses"),
    ("lift_long_clauses", "long clauses"),
    ("lift_max_clause_size", "maximum clause size"),
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--ric3-candidate", nargs="+", required=True, type=Path)
    parser.add_argument("--ric3-baseline", nargs="+", required=True, type=Path)
    parser.add_argument("--mc-role", required=True, type=Path)
    parser.add_argument("--mc-baseline", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def read_rows(paths: list[Path]) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                rows[row["model_id"]] = row
    return rows


def solved(row: dict[str, str], config: str) -> bool:
    return row.get(f"{config}_status") in VALID


def classify(
    candidate: dict[str, str], reference: dict[str, str],
    candidate_config: str, reference_config: str,
) -> str:
    candidate_solved = solved(candidate, candidate_config)
    reference_solved = solved(reference, reference_config)
    if candidate_solved and not reference_solved:
        return "candidate_only"
    if reference_solved and not candidate_solved:
        return "reference_only"
    if not candidate_solved:
        return "both_unsolved"
    candidate_time = float(candidate[f"{candidate_config}_wall_seconds"])
    reference_time = float(reference[f"{reference_config}_wall_seconds"])
    if candidate_time + 2 < reference_time:
        return "speed_win"
    if reference_time + 2 < candidate_time:
        return "speed_loss"
    return "close"


def cliff(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return math.nan
    score = sum((a > b) - (a < b) for a in left for b in right)
    return score / (len(left) * len(right))


def fmt(value: float) -> str:
    return "-" if math.isnan(value) else f"{value:.3f}"


def feature_table(
    lines: list[str], title: str, positive: list[str], negative: list[str],
    metadata: dict[str, dict[str, object]],
) -> None:
    lines += [
        "", f"### {title}", "",
        "Cliff delta is positive when the feature tends to be larger in the "
        "candidate-favoured group. Values below about 0.33 are weak effects.", "",
        "| Feature | Candidate-favoured median | Reference-favoured median | Cliff delta |",
        "|---|---:|---:|---:|",
    ]
    for field, label in STATIC_FEATURES:
        left = [float(metadata[model].get(field, 0) or 0) for model in positive]
        right = [float(metadata[model].get(field, 0) or 0) for model in negative]
        lines.append(
            f"| {label} | {statistics.median(left):.3f} | "
            f"{statistics.median(right):.3f} | {fmt(cliff(left, right))} |"
        )


def family_table(
    lines: list[str], title: str, positive: list[str], negative: list[str],
    metadata: dict[str, dict[str, object]],
) -> None:
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for model in positive:
        counts[str(metadata[model]["family"])][0] += 1
    for model in negative:
        counts[str(metadata[model]["family"])][1] += 1
    informative = [
        (sum(value), family, value) for family, value in counts.items()
        if sum(value) >= 2
    ]
    lines += ["", f"### {title}", "", "| Family | Candidate/reference favoured |", "|---|---:|"]
    for _total, family, value in sorted(informative, reverse=True)[:20]:
        lines.append(f"| {family} | {value[0]}/{value[1]} |")
    if not informative:
        lines.append("| No repeated decisive family | - |")


def list_only(
    lines: list[str], title: str, groups: dict[str, list[str]],
    metadata: dict[str, dict[str, object]],
) -> None:
    lines += ["", f"### {title}", ""]
    for group, label in (("candidate_only", "Candidate only"), ("reference_only", "Reference only")):
        lines.append(f"**{label} ({len(groups[group])})**")
        lines.append("")
        if not groups[group]:
            lines.append("none")
        else:
            for model in groups[group]:
                item = metadata[model]
                lines.append(
                    f"- `{model}`: year={item['year']}, family={item['family']}, "
                    f"tier={item['tier']}, ANDs={item['aig_ands']}, "
                    f"XORs={item['recognized_xors']}"
                )
        lines.append("")


def probe_table(
    lines: list[str], positive: list[str], negative: list[str],
    probes: dict[str, dict[str, str]],
) -> None:
    lines += [
        "", "### MC PDR-free preprocessing deltas", "",
        "Values are median `sum-high / legacy` ratios. A Cliff delta near zero means "
        "that the structural change does not distinguish runtime winners.", "",
        "| Probe delta | Candidate-favoured | Reference-favoured | Cliff delta |",
        "|---|---:|---:|---:|",
    ]

    def log_ratio(model: str, field: str) -> float:
        row = probes[model]
        candidate = float(row[f"xag_probe_lift_sum_high_{field}"])
        reference = float(row[f"xag_probe_lift_legacy_{field}"])
        return math.log((candidate + 1) / (reference + 1))

    for field, label in PROBE_FEATURES:
        left = [log_ratio(model, field) for model in positive if model in probes]
        right = [log_ratio(model, field) for model in negative if model in probes]
        lines.append(
            f"| {label} | {math.exp(statistics.median(left)):.3f} | "
            f"{math.exp(statistics.median(right)):.3f} | {fmt(cliff(left, right))} |"
        )


def experiment_section(
    lines: list[str], title: str, candidate: dict[str, dict[str, str]],
    reference: dict[str, dict[str, str]], candidate_config: str,
    reference_config: str, metadata: dict[str, dict[str, object]],
    probes: dict[str, dict[str, str]] | None = None,
) -> None:
    groups: dict[str, list[str]] = defaultdict(list)
    for model, candidate_row in candidate.items():
        if model not in reference or model not in metadata:
            continue
        groups[classify(candidate_row, reference[model], candidate_config, reference_config)].append(model)
    positive = groups["candidate_only"] + groups["speed_win"]
    negative = groups["reference_only"] + groups["speed_loss"]
    lines += [
        "", f"## {title}", "",
        "| Candidate-only | Reference-only | Speed wins | Speed losses | Close | Both unsolved |",
        "|---:|---:|---:|---:|---:|---:|",
        f"| {len(groups['candidate_only'])} | {len(groups['reference_only'])} | "
        f"{len(groups['speed_win'])} | {len(groups['speed_loss'])} | "
        f"{len(groups['close'])} | {len(groups['both_unsolved'])} |",
    ]
    list_only(lines, "Outcome-discordant models", groups, metadata)
    feature_table(lines, "Static structure", positive, negative, metadata)
    family_table(lines, "Repeated decisive families", positive, negative, metadata)
    if probes is not None:
        probe_table(lines, positive, negative, probes)


def main() -> int:
    args = arguments()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    metadata = {model["id"]: model for model in manifest}
    probes = read_rows([args.probe])
    lines = [
        "# BVE winner commonality", "",
        "This report separates outcome coverage from runtime. Runtime groups use a "
        "two-second dead zone. Cross-campaign rIC3 runtime effects remain load-confounded.",
    ]
    experiment_section(
        lines, "rIC3 product-sum-high vs product-high",
        read_rows(args.ric3_candidate), read_rows(args.ric3_baseline),
        "native_product_sum_high4", "native_product_high4", metadata,
    )
    experiment_section(
        lines, "MC translation=legacy/lift=sum-high vs XAG legacy",
        read_rows([args.mc_role]), read_rows(args.mc_baseline),
        "xag_translation_legacy_lift_sum4", "xag_legacy4", metadata, probes,
    )
    lines += [
        "", "## Conclusion", "",
        "No static feature or simple preprocessing delta currently separates winners "
        "with a medium or strong effect. The most visible MC signal is next-cone XOR "
        "density, but it is still weak. The next experiment should therefore strengthen "
        "the causal treatment (width-weighted BVE acceptance) before fitting an "
        "instance selector.",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
