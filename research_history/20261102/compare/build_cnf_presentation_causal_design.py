#!/usr/bin/env python3
"""Select stable and seed-sensitive models for SAT query replay."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from xag_structural_features import family_name


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "results" / "initial_cnf_final_holdout_design_v1" / "manifest.json"
INPUTS = (
    ROOT / "results" / "variable_order_overnight_server-a_v1" / "results.tsv",
    ROOT / "results" / "variable_order_overnight_server-c_v1" / "results.tsv",
    ROOT / "results" / "variable_order_numeric_validation_v1" / "results.tsv",
)
OUTPUT = ROOT / "results" / "cnf_presentation_causal_design_v1"
SOLVED = {"SAFE", "UNSAFE"}


def cost(row: dict[str, str]) -> float:
    if row["status"] in SOLVED:
        return float(row["wall_seconds"])
    return 1.5 * float(row["timeout_seconds"])


def choose(records: list[dict[str, object]], count: int) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    family_counts: defaultdict[str, int] = defaultdict(int)
    ordered = sorted(records, key=lambda row: (-float(row["score"]), str(row["id"])))
    for row in ordered:
        family = str(row["family"])
        if family_counts[family] >= 2:
            continue
        selected.append(row)
        family_counts[family] += 1
        if len(selected) == count:
            return selected
    for row in ordered:
        if row not in selected:
            selected.append(row)
            if len(selected) == count:
                break
    return selected


def main() -> int:
    source = json.loads(MANIFEST.read_text(encoding="utf-8"))["models"]
    models = {str(model["id"]): model for model in source}
    cells: dict[tuple[str, str, str], dict[str, str]] = {}
    for path in INPUTS:
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if row["config"] != "xag_canonical-cnf":
                    continue
                if row["variable_order"] not in {"first", "numeric"}:
                    continue
                cells[(row["model_id"], row["run"], row["variable_order"])] = row

    buckets: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for model_id, model in models.items():
        deltas = []
        delta_by_run: dict[str, float] = {}
        for run in map(str, range(1, 7)):
            baseline = cells.get((model_id, run, "first"))
            numeric = cells.get((model_id, run, "numeric"))
            if baseline is None or numeric is None:
                continue
            if baseline["status"] not in SOLVED and numeric["status"] not in SOLVED:
                continue
            delta = cost(baseline) - cost(numeric)
            deltas.append(delta)
            delta_by_run[run] = delta
        positive = sum(delta > 2.0 for delta in deltas)
        negative = sum(delta < -2.0 for delta in deltas)
        if positive >= 3 and negative == 0:
            category = "stable-win"
            score = sum(deltas)
        elif negative >= 3 and positive == 0:
            category = "stable-loss"
            score = -sum(deltas)
        elif positive and negative:
            category = "seed-reversal"
            score = max(deltas) - min(deltas)
        else:
            continue
        if category == "seed-reversal":
            trace_runs = [
                max(delta_by_run, key=delta_by_run.get),
                min(delta_by_run, key=delta_by_run.get),
            ]
        else:
            trace_runs = [max(delta_by_run, key=lambda run: abs(delta_by_run[run]))]
        record = dict(model)
        record.update({
            "category": category,
            "family": family_name(str(model["name"])),
            "score": score,
            "numeric_positive_runs": positive,
            "numeric_negative_runs": negative,
            "numeric_deltas": deltas,
            "numeric_delta_by_run": delta_by_run,
            "trace_runs": trace_runs,
        })
        buckets[category].append(record)

    selected = (
        choose(buckets["stable-win"], 6)
        + choose(buckets["stable-loss"], 9)
        + choose(buckets["seed-reversal"], 15)
    )
    shards: dict[str, list[dict[str, object]]] = {
        "server-a": [], "server-b": [], "server-c": [],
    }
    shard_names = tuple(shards)
    category_offsets = {"stable-win": 0, "stable-loss": 0, "seed-reversal": 0}
    for row in selected:
        category = str(row["category"])
        shard = shard_names[category_offsets[category] % len(shard_names)]
        category_offsets[category] += 1
        item = dict(row)
        item["shard"] = shard
        shards[shard].append(item)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    for shard, shard_models in shards.items():
        payload = {
            "experiment": "cnf_presentation_causal_v1",
            "source_manifest": str(MANIFEST),
            "selection": {
                "models": len(shard_models),
                "stable_win": sum(row["category"] == "stable-win" for row in shard_models),
                "stable_loss": sum(row["category"] == "stable-loss" for row in shard_models),
                "seed_reversal": sum(row["category"] == "seed-reversal" for row in shard_models),
            },
            "models": sorted(shard_models, key=lambda row: (str(row["category"]), str(row["id"]))),
        }
        output = OUTPUT / f"manifest_{shard}.json"
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"{shard}: models={len(shard_models)} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
