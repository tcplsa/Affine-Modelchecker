#!/usr/bin/env python3
"""Build per-strategy manifests for candidate-only hard-instance solves."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


SOLVED = {"SAFE", "UNSAFE"}
STRATEGIES = ("source-init", "source-zero", "source-random", "first-phase", "heuristic")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def load(path: Path, strategy: str) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return {row["model_id"]: row for row in csv.DictReader(source, delimiter="\t")}


def status(row: dict[str, str], strategy: str) -> str:
    return row.get("aig4_" + strategy.replace("-", "_") + "_status", "")


def write(path: Path, models: list[dict[str, object]], strategy: str) -> None:
    path.write_text(
        json.dumps({
            "schema": "mc-hard-confirmation-v1",
            "strategy": strategy,
            "models": models,
        }, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    models = {
        model["id"]: model
        for model in json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    }
    baseline = load(args.results / "baseline.tsv", "baseline")
    selected: dict[str, list[dict[str, object]]] = {}
    union: dict[str, dict[str, object]] = {}
    for strategy in STRATEGIES:
        path = args.results / f"{strategy}.tsv"
        if not path.exists():
            continue
        rows = load(path, strategy)
        candidates = []
        for model_id, row in rows.items():
            if status(row, strategy) not in SOLVED:
                continue
            if status(baseline[model_id], "baseline") in SOLVED:
                continue
            candidate = dict(models[model_id])
            candidate["confirmation_strategy"] = strategy
            candidates.append(candidate)
            union[model_id] = candidate
        if candidates:
            selected[strategy] = candidates

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write(args.output_dir / "baseline.json", list(union.values()), "baseline")
    for strategy, candidates in selected.items():
        write(args.output_dir / f"{strategy}.json", candidates, strategy)
    print({strategy: len(models) for strategy, models in selected.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
