#!/usr/bin/env python3
"""Compare paired legacy/winning MIC traces and their PDR trajectories."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


def number(row: dict[str, str], field: str) -> float:
    try:
        return float(row.get(field, ""))
    except (TypeError, ValueError):
        return 0.0


def trace_metrics(path: Path) -> dict[str, float]:
    attempts = successes = queries = 0
    elapsed = failed_elapsed = 0.0
    files = list(path.glob("*.decision.tsv"))
    for trace in files:
        with trace.open(encoding="utf-8", newline="") as source:
            for row in csv.DictReader(source, delimiter="\t"):
                if row.get("event") != "mic_attempt":
                    continue
                attempts += 1
                success = int(row.get("result", "0")) == 1
                successes += success
                seconds = number(row, "elapsed_seconds")
                elapsed += seconds
                if not success:
                    failed_elapsed += seconds
                queries += int(row.get("query_delta", "0"))
    return {
        "attempts": float(attempts),
        "success_rate": successes / attempts if attempts else math.nan,
        "mean_queries": queries / attempts if attempts else math.nan,
        "failed_seconds": failed_elapsed,
        "mic_seconds": elapsed,
    }


def fmt(value: float, digits: int = 3) -> str:
    return "-" if not math.isfinite(value) else f"{value:.{digits}f}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--screen", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    with (args.results / "summary.tsv").open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    by_model: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_model.setdefault(row["model_id"], []).append(row)

    screen_rows: dict[tuple[str, str], dict[str, str]] = {}
    if args.screen:
        policy_strategy = {
            "legacy": "baseline",
            "distance-near": "mic-near",
            "distance-far": "mic-far",
            "feedback": "mic-feedback",
            "distance-feedback": "mic-distance-feedback",
        }
        for policy, strategy in policy_strategy.items():
            path = args.screen / f"{strategy}.tsv"
            if not path.exists():
                continue
            prefix = "aig4_" + strategy.replace("-", "_") + "_"
            with path.open(encoding="utf-8", newline="") as source:
                for source_row in csv.DictReader(source, delimiter="\t"):
                    normalized = {
                        key[len(prefix):]: value
                        for key, value in source_row.items()
                        if key.startswith(prefix)
                    }
                    screen_rows[(source_row["model_id"], policy)] = normalized

    lines = [
        "# Distance/Feedback MIC Mechanism",
        "",
        "| Model | Policy | Depth | Attempts | Drop success | Mean queries | Failed MIC s | CTI/depth | MIC/depth | Failed-push ratio |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for model_id in sorted(by_model):
        for row in sorted(by_model[model_id], key=lambda item: item["policy"]):
            metrics = trace_metrics(Path(row["trace_dir"]))
            trajectory = screen_rows.get((model_id, row["policy"]), row)
            depth = max(number(trajectory, "pdr_depth"), 1.0)
            cti_per_depth = number(trajectory, "cti") / depth
            mic_per_depth = number(trajectory, "mic") / depth
            failed_push = number(trajectory, "unpush") / max(
                number(trajectory, "push"), 1.0
            )
            lines.append(
                f"| `{model_id}` | `{row['policy']}` | "
                f"{number(trajectory, 'pdr_depth'):g} | "
                f"{metrics['attempts']:g} | {fmt(metrics['success_rate'])} | "
                f"{fmt(metrics['mean_queries'])} | {fmt(metrics['failed_seconds'])} | "
                f"{fmt(cti_per_depth)} | {fmt(mic_per_depth)} | {fmt(failed_push)} |"
            )

    lines.extend(
        [
            "",
            "## Evidence Rule",
            "",
            "A policy has an internal-SAT mechanism only if it improves drop success or "
            "failed-attempt cost.  If those remain neutral while the PDR trajectory "
            "changes, the effect is attributed to changed cores/lemmas and query flow, "
            "not cheaper execution of the same MIC decisions.",
            "",
        ]
    )
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"models={len(by_model)} rows={len(rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
