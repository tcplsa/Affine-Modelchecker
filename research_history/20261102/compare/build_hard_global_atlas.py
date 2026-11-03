#!/usr/bin/env python3
"""Build a static, family-level atlas for every stock-rIC3-3600 hard model."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Optional


SOLVED = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hard-manifest", type=Path, required=True)
    parser.add_argument("--mc-input", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def aig_header(path: Path) -> dict[str, int]:
    with path.open("rb") as source:
        fields = source.readline().decode("ascii").split()
    if not fields or fields[0] not in {"aig", "aag"} or len(fields) < 6:
        raise ValueError(f"invalid AIGER header in {path}")
    values = [int(value) for value in fields[1:]]
    names = ("maxvar", "inputs", "latches", "outputs", "ands", "bads",
             "constraints", "justice", "fairness")
    return {name: values[index] if index < len(values) else 0
            for index, name in enumerate(names)}


def load_mc(paths: Iterable[Path]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for path in paths:
        with path.open(encoding="utf-8", newline="") as source:
            for row in csv.DictReader(source, delimiter="\t"):
                result[row["model_id"]] = row
    return result


def median(values: Iterable[float]) -> float:
    present = list(values)
    return statistics.median(present) if present else 0.0


def structural_class(row: dict[str, Any]) -> str:
    if row["next_xor_density"] >= 0.08 or row["and_reduction"] >= 0.30:
        return "affine-heavy"
    if row["latch_and_ratio"] >= 0.20:
        return "state-heavy"
    if row["latch_and_ratio"] <= 0.01 and row["input_and_ratio"] >= 0.05:
        return "combinational-heavy"
    if row["aig_ands"] >= 1_000_000:
        return "very-large"
    return "mixed-control-data"


def main() -> int:
    args = parse_args()
    models = json.loads(args.hard_manifest.read_text(encoding="utf-8"))["models"]
    mc = load_mc(args.mc_input)
    rows: list[dict[str, Any]] = []
    for model in models:
        header = aig_header(Path(model["path"]))
        mc_row = mc.get(model["id"])
        row: dict[str, Any] = {
            "model_id": model["id"],
            "name": model["name"],
            "year": model["year"],
            "family": model["family"],
            "path": model["path"],
            "size_bytes": model["size_bytes"],
            "inputs": header["inputs"],
            "latches": header["latches"],
            "outputs": header["outputs"],
            "bads": header["bads"],
            "constraints": header["constraints"],
            "aig_ands": model["aig_ands"],
            "recognized_xors": model["recognized_xors"],
            "and_reduction": model["and_reduction"],
            "next_xor_density": model["next_xor_density"],
            "bad_xor_density": model["bad_xor_density"],
            "latch_and_ratio": header["latches"] / max(1, model["aig_ands"]),
            "input_and_ratio": header["inputs"] / max(1, model["aig_ands"]),
            "mc_previously_run": int(mc_row is not None),
            "mc_aig_solved": int(mc_row is not None and mc_row["aig_legacy4_status"] in SOLVED),
            "mc_xag_incremental": int(
                mc_row is not None
                and mc_row["aig_legacy4_status"] not in SOLVED
                and (mc_row["xag_legacy4_status"] in SOLVED
                     or mc_row["xag_best4_status"] in SOLVED)
            ),
        }
        row["structural_class"] = structural_class(row)
        rows.append(row)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    model_fields = list(rows[0])
    with (args.output_dir / "hard_model_atlas.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as target:
        writer = csv.DictWriter(target, fieldnames=model_fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_family[row["family"]].append(row)
    family_rows: list[dict[str, Any]] = []
    for family, members in by_family.items():
        classes = Counter(member["structural_class"] for member in members)
        family_rows.append({
            "family": family,
            "models": len(members),
            "years": ",".join(map(str, sorted({member["year"] for member in members}))),
            "median_size_bytes": int(median(float(member["size_bytes"]) for member in members)),
            "median_inputs": int(median(float(member["inputs"]) for member in members)),
            "median_latches": int(median(float(member["latches"]) for member in members)),
            "median_ands": int(median(float(member["aig_ands"]) for member in members)),
            "median_and_reduction": median(float(member["and_reduction"]) for member in members),
            "median_next_xor_density": median(float(member["next_xor_density"]) for member in members),
            "dominant_structural_class": classes.most_common(1)[0][0],
            "mc_previously_run": sum(member["mc_previously_run"] for member in members),
            "mc_aig_solved": sum(member["mc_aig_solved"] for member in members),
            "mc_xag_incremental": sum(member["mc_xag_incremental"] for member in members),
        })
    family_rows.sort(key=lambda row: (-row["models"], row["family"]))
    family_fields = list(family_rows[0])
    with (args.output_dir / "hard_family_atlas.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as target:
        writer = csv.DictWriter(target, fieldnames=family_fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(family_rows)

    class_counts = Counter(row["structural_class"] for row in rows)
    lines = [
        "# Global atlas of stock-rIC3-3600 hard models",
        "",
        f"Models: {len(rows)}; families: {len(family_rows)}.",
        "",
        "## Structural coverage",
        "",
        "| Structural class | Models |",
        "| --- | ---: |",
    ]
    for name, count in class_counts.most_common():
        lines.append(f"| `{name}` | {count} |")
    lines.extend([
        "",
        "## Largest families",
        "",
        "| Family | N | Structure | Latches | ANDs | Next-XOR density | MC-AIG | XAG-only increment |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in family_rows[:40]:
        lines.append(
            f"| `{row['family']}` | {row['models']} | `{row['dominant_structural_class']}` | "
            f"{row['median_latches']} | {row['median_ands']} | "
            f"{row['median_next_xor_density']:.3f} | {row['mc_aig_solved']} | "
            f"{row['mc_xag_incremental']} |"
        )
    lines.extend([
        "",
        "These classes are descriptive strata, not solver-policy labels. The 120-second",
        "dynamic screen must determine whether structurally different families share the",
        "same PDR failure signature before any heuristic is promoted.",
    ])
    (args.output_dir / "static_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(f"models={len(rows)} families={len(family_rows)} output={args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
