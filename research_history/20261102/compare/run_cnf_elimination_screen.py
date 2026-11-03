#!/usr/bin/env python3
"""Screen deterministic CNF elimination policies across years and difficulty tiers."""

from __future__ import annotations

import argparse
import json
import signal
from collections import defaultdict
from pathlib import Path
from typing import Any

from compare_runner import ExperimentRunner


TREATMENTS: list[tuple[str, str, dict[str, Any]]] = [
    ("min_default", "MiniSat default", {}),
    ("min_shrink", "MiniSat grow=-1", {"minisat_grow": -1}),
    ("min_grow1", "MiniSat grow=1", {"minisat_grow": 1}),
    ("min_clause8", "MiniSat clause-limit=8", {"minisat_clause_limit": 8}),
    ("min_clause40", "MiniSat clause-limit=40", {"minisat_clause_limit": 40}),
    ("min_asymm", "MiniSat asymmetric", {"minisat_asymm": True}),
    ("min_rcheck", "MiniSat redundancy-check", {"minisat_rcheck": True}),
    ("cad_r1", "CaDiCaL rounds=1", {"preprocessor": "cadical", "cadical_pre_rounds": 1}),
    ("cad_r2", "CaDiCaL rounds=2", {"preprocessor": "cadical", "cadical_pre_rounds": 2}),
    ("cad_r3", "CaDiCaL rounds=3", {"preprocessor": "cadical", "cadical_pre_rounds": 3}),
    ("cad_prod", "CaDiCaL product score", {
        "preprocessor": "cadical", "cadical_pre_rounds": 2,
        "cadical_elimprod": 1, "cadical_elimsum": 0,
    }),
    ("cad_sum", "CaDiCaL sum score", {
        "preprocessor": "cadical", "cadical_pre_rounds": 2,
        "cadical_elimprod": 0, "cadical_elimsum": 1,
    }),
]

ORDER_TREATMENTS: list[tuple[str, str, dict[str, Any]]] = [
    ("order_legacy", "Legacy product order", {"minisat_elim_order": "legacy"}),
    ("order_low", "Product, low ID tie", {"minisat_elim_order": "low"}),
    ("order_high", "Product, high ID tie", {"minisat_elim_order": "high"}),
    ("order_sum_low", "Product/sum, low ID tie", {"minisat_elim_order": "sum-low"}),
    ("order_sum_high", "Product/sum, high ID tie", {"minisat_elim_order": "sum-high"}),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=48)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--seed", type=int, default=170001)
    parser.add_argument("--models-per-year", type=int, default=8)
    parser.add_argument("--representations", choices=("both", "aig", "xag"), default="both")
    parser.add_argument("--treatment-set", choices=("broad", "order"), default="broad")
    return parser.parse_args()


def evenly_spaced(models: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if len(models) <= count:
        return models
    ordered = sorted(models, key=lambda model: float(model.get("baseline_seconds", 0.0)))
    if count == 1:
        return [ordered[len(ordered) // 2]]
    return [ordered[round(index * (len(ordered) - 1) / (count - 1))] for index in range(count)]


def select_models(manifest: dict[str, Any], per_year: int) -> list[dict[str, Any]]:
    by_year: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for model in manifest["models"]:
        by_year[str(model["year"])].append(model)
    selected: list[dict[str, Any]] = []
    weights = (("medium", 4), ("slow", 2), ("timeout", 2))
    for year in sorted(by_year):
        year_models = by_year[year]
        chosen: list[dict[str, Any]] = []
        for tier, desired in weights:
            count = max(1, round(per_year * desired / 8)) if per_year else 0
            chosen.extend(evenly_spaced(
                [model for model in year_models if model.get("tier") == tier], count
            ))
        chosen_ids = {model["id"] for model in chosen}
        remaining = [model for model in year_models if model["id"] not in chosen_ids]
        chosen.extend(evenly_spaced(remaining, max(0, per_year - len(chosen))))
        selected.extend(chosen[:per_year])
    return selected


def make_config(
    treatment: tuple[str, str, dict[str, Any]], representation: str,
    binary: Path,
) -> dict[str, Any]:
    ident, label, overrides = treatment
    config: dict[str, Any] = {
        "id": f"{representation}_{ident}",
        "label": f"{representation.upper()} {label}",
        "kind": "mc",
        "binary": str(binary),
        "mode": representation,
        "direction": "forward",
        "ctg_depth": 1,
        "deterministic_lanes": True,
        "preprocessor": "minisat",
        "minisat_grow": 0,
        "minisat_clause_limit": 20,
        "minisat_asymm": False,
        "minisat_rcheck": False,
    }
    config.update(overrides)
    return config


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    models = select_models(manifest, args.models_per_year)
    representations = ("aig", "xag") if args.representations == "both" else (args.representations,)
    treatments = TREATMENTS if args.treatment_set == "broad" else ORDER_TREATMENTS
    configs = [
        make_config(treatment, representation, args.binary)
        for representation in representations
        for treatment in treatments
    ]

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                f"models={event['total']} configs={len(configs)} workers={args.workers} "
                f"timeout={args.timeout}", flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            if completed % 4 == 0 or completed == int(event["total"]):
                print(f"completed={completed}/{event['total']}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed",
        "group": "cnf-elimination-screen",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": [model["path"] for model in models],
        "output": str(args.output),
        "timeout": args.timeout,
        "workers": args.workers,
        "skip_existing": True,
        "mc_seed": args.seed,
        "configs": configs,
    }, progress)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    result = runner.run()
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
