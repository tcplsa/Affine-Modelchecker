#!/usr/bin/env python3
"""Analyze per-XOR sufficiency, necessity, and solver-phase effects."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


VALID = {"SAFE", "UNSAFE"}
PHASES = (
    "translation_build", "translation_simplify", "translation_inject",
    "bmc0_solve", "first_pre_solve", "lift_build", "lift_simplify",
    "lift_inject", "first_lift_solve",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--timeout-penalty", type=float, default=1.5)
    parser.add_argument("--neutral-seconds", type=float, default=2.0)
    return parser.parse_args()


def med(values: list[float]) -> float:
    return statistics.median(values) if values else math.nan


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        if fields:
            writer.writeheader()
            writer.writerows(rows)


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    design = json.loads(args.manifest.read_text(encoding="utf-8"))
    models = {model["id"]: model for model in design["models"]}
    gate_meta = {
        (model["id"], int(gate["xor_var"])): gate
        for model in design["models"] for gate in model["affected_gates"]
    }
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for path in args.inputs:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = (row["model_id"], row["run"], row["variant"])
                if key in seen:
                    raise SystemExit(f"duplicate observation: {key}")
                seen.add(key)
                rows.append(row)

    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    outcomes: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        grouped[(row["model_id"], row["variant"])].append(row)
        if row["status"] in VALID:
            outcomes[row["model_id"]].add(row["status"])
    conflicts = {model_id: values for model_id, values in outcomes.items() if len(values) > 1}

    variants: dict[tuple[str, str], dict[str, Any]] = {}
    incomplete: list[str] = []
    for model in design["models"]:
        for variant in model["variants"]:
            observations = grouped.get((model["id"], variant["id"]), [])
            if len(observations) != 4:
                incomplete.append(f"{model['id']}\t{variant['id']}\t{len(observations)}")
            costs = []
            solved_walls = []
            phase_values: dict[str, list[float]] = defaultdict(list)
            timeout_phases = Counter()
            for row in observations:
                if row["status"] in VALID:
                    wall = float(row["wall_seconds"])
                    costs.append(wall)
                    solved_walls.append(wall)
                else:
                    costs.append(args.timeout_penalty * float(row["timeout_seconds"]))
                    timeout_phases[row["timeout_phase"]] += 1
                for phase in PHASES:
                    value = row.get(f"phase_{phase}", "")
                    if value:
                        phase_values[phase].append(float(value))
            summary: dict[str, Any] = {
                "model_id": model["id"], "variant": variant["id"], "kind": variant["kind"],
                "xor_var": variant["xor_var"], "observations": len(observations),
                "solved_runs": len(solved_walls), "median_cost": med(costs),
                "median_solved_wall": med(solved_walls),
                "timeout_phase": timeout_phases.most_common(1)[0][0] if timeout_phases else "",
            }
            for phase in PHASES:
                summary[f"median_{phase}"] = med(phase_values[phase])
            variants[(model["id"], variant["id"])] = summary

    gate_rows: list[dict[str, Any]] = []
    for model in design["models"]:
        full = variants[(model["id"], "baseline_full")]
        retain = variants[(model["id"], "baseline_retain248")]
        for gate in model["affected_gates"]:
            var = int(gate["xor_var"])
            remove = variants[(model["id"], f"remove_{var}")]
            addback = variants[(model["id"], f"addback_{var}")]
            remove_effect = float(full["median_cost"]) - float(remove["median_cost"])
            addback_effect = float(retain["median_cost"]) - float(addback["median_cost"])
            record: dict[str, Any] = {
                "model_id": model["id"], "xor_var": var,
                "full_solved_runs": full["solved_runs"], "full_cost": f"{full['median_cost']:.6f}",
                "remove_solved_runs": remove["solved_runs"], "remove_cost": f"{remove['median_cost']:.6f}",
                "remove_effect_seconds": f"{remove_effect:.6f}",
                "remove_class": "helps" if remove_effect > args.neutral_seconds else (
                    "hurts" if remove_effect < -args.neutral_seconds else "neutral"),
                "retain_solved_runs": retain["solved_runs"], "retain_cost": f"{retain['median_cost']:.6f}",
                "addback_solved_runs": addback["solved_runs"], "addback_cost": f"{addback['median_cost']:.6f}",
                "addback_effect_seconds": f"{addback_effect:.6f}",
                "addback_class": "helps" if addback_effect > args.neutral_seconds else (
                    "hurts" if addback_effect < -args.neutral_seconds else "neutral"),
                "remove_timeout_phase": remove["timeout_phase"],
                "addback_timeout_phase": addback["timeout_phase"],
            }
            for field, value in gate.items():
                if field != "xor_var":
                    record[field] = value
            for phase in PHASES:
                for prefix, summary in (("full", full), ("remove", remove), ("retain", retain), ("addback", addback)):
                    value = summary[f"median_{phase}"]
                    record[f"{prefix}_{phase}"] = "" if math.isnan(value) else f"{value:.6f}"
            gate_rows.append(record)
    write_tsv(args.output_dir / "gate_effects.tsv", gate_rows)
    write_tsv(args.output_dir / "variant_summary.tsv", list(variants.values()))
    (args.output_dir / "incomplete.tsv").write_text(
        "model_id\tvariant\tobservations\n" + "\n".join(incomplete) + ("\n" if incomplete else ""),
        encoding="utf-8",
    )

    sections = []
    for model in design["models"]:
        subset = [row for row in gate_rows if row["model_id"] == model["id"]]
        full = variants[(model["id"], "baseline_full")]
        retain = variants[(model["id"], "baseline_retain248")]
        remove_counts = Counter(row["remove_class"] for row in subset)
        addback_counts = Counter(row["addback_class"] for row in subset)
        strongest_remove = sorted(subset, key=lambda row: float(row["remove_effect_seconds"]), reverse=True)[:5]
        strongest_addback = sorted(subset, key=lambda row: float(row["addback_effect_seconds"]), reverse=True)[:5]
        sections.append(f"""## {model['id']}

- Full-XAG: {full['solved_runs']}/4 solved, median penalized cost {full['median_cost']:.2f} s.
- retain248: {retain['solved_runs']}/4 solved, median penalized cost {retain['median_cost']:.2f} s.
- Single removal helps/hurts/neutral: {remove_counts['helps']}/{remove_counts['hurts']}/{remove_counts['neutral']}.
- Single add-back helps/hurts/neutral: {addback_counts['helps']}/{addback_counts['hurts']}/{addback_counts['neutral']}.
- Strongest removal effects: {', '.join(str(row['xor_var']) + ':' + row['remove_effect_seconds'] for row in strongest_remove)}.
- Strongest add-back effects: {', '.join(str(row['xor_var']) + ':' + row['addback_effect_seconds'] for row in strongest_addback)}.
""")

    report = f"""# AllInterval Per-XOR Causal Analysis

- Task rows: {len(rows)}
- Incomplete variant cells: {len(incomplete)}
- Outcome conflicts: {len(conflicts)}
- Positive removal effect means deleting that XOR improves Full-XAG.
- Positive add-back effect means restoring that XOR improves retain248.

{''.join(sections)}
See `gate_effects.tsv` for structural features and phase-level timings.
"""
    (args.output_dir / "report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
