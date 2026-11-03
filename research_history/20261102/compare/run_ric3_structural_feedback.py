#!/usr/bin/env python3
"""Two-stage rIC3 structural-predicate and scout-feedback experiment."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from compare_runner import ExperimentRunner


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("scout", "specialist"), required=True)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--feedback-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--seed", type=int, default=1700001)
    parser.add_argument("--replicas", type=int, default=4)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--domain", choices=("all", "rich", "poor"), default="all")
    parser.add_argument(
        "--model-list", type=Path,
        help="Optional newline-delimited model IDs/names used for focused studies.",
    )
    return parser.parse_args()


def ric3_config(
    args: argparse.Namespace,
    ident: str,
    label: str,
    extra_args: str,
    replicas: int,
) -> dict[str, object]:
    return {
        "id": ident,
        "label": label,
        "kind": "ric3",
        "binary": str(args.binary),
        "engine": "ic3",
        "aig_encoding": "native",
        "global_args": "--bve-order legacy",
        "bve_width_weight": 0,
        "replicas": replicas,
        "seed": args.seed,
        "extra_args": extra_args,
    }


def main() -> int:
    args = arguments()
    if not 0 <= args.shard_index < args.shard_count:
        raise SystemExit("shard index must be in [0, shard count)")
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    models = selection["models"]
    if args.domain != "all":
        suffix = "xor-rich" if args.domain == "rich" else "xor-poor"
        models = [model for model in models if str(model["domain"]).endswith(suffix)]
    if args.model_list:
        selected = {
            line.strip() for line in args.model_list.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        models = [
            model for model in models
            if model["id"] in selected or model["family"] in selected
            or Path(model["path"]).stem in selected
        ]
    models = [
        model for index, model in enumerate(models)
        if index % args.shard_count == args.shard_index
    ]
    args.feedback_dir.mkdir(parents=True, exist_ok=True)
    feedback = str(args.feedback_dir / "{model_key}.json")

    if args.phase == "scout":
        configs = [ric3_config(
            args, "scout", "IC3 scout", f"--feedback-out {feedback}", 1,
        )]
    else:
        replicas = args.replicas
        configs = [
            ric3_config(args, "baseline", "IC3 baseline", "", replicas),
            ric3_config(
                args, "critical64", "IC3 critical-64",
                "--inn --inn-policy critical --inn-budget 64", replicas,
            ),
            ric3_config(
                args, "xorcritical64", "IC3 XOR-critical-64",
                "--inn --inn-policy xor-critical --inn-budget 64", replicas,
            ),
            ric3_config(
                args, "feedback64", "IC3 feedback-64",
                f"--inn --inn-policy feedback --inn-budget 64 --inn-feedback-in {feedback}",
                replicas,
            ),
            ric3_config(
                args, "feedback128", "IC3 feedback-128",
                f"--inn --inn-policy feedback --inn-budget 128 --inn-feedback-in {feedback}",
                replicas,
            ),
        ]

    metadata = {
        str(model["path"]): {
            "model_id": model["id"],
            "family": model["family"],
            "tier": model["tier"],
            "domain": model["domain"],
            "baseline_status": model["baseline_status"],
            "baseline_seconds": model["baseline_seconds"],
        }
        for model in models
    }

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                f"phase={args.phase} models={event['total']} configs={len(configs)} "
                f"replicas={1 if args.phase == 'scout' else args.replicas} "
                f"workers={args.workers} timeout={args.timeout:g}", flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            total = int(event["total"])
            if completed % 5 == 0 or completed == total:
                print(f"completed={completed}/{total}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed",
        "group": f"structural-feedback-{args.phase}",
        "model_paths": [str(model["path"]) for model in models],
        "model_metadata": metadata,
        "metadata_fields": [
            "model_id", "family", "tier", "domain",
            "baseline_status", "baseline_seconds",
        ],
        "output": str(args.output),
        "timeout": args.timeout,
        "workers": args.workers,
        "skip_existing": True,
        "configs": configs,
    }, progress)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    result = runner.run()
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
