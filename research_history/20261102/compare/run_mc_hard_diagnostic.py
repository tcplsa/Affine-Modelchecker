#!/usr/bin/env python3
"""Run the fixed four-lane MC-AIG baseline with timeout progress telemetry."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from compare_runner import ExperimentRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--workers", type=int, default=28)
    parser.add_argument("--seed", type=int, default=730001)
    parser.add_argument("--model-id", action="append", default=[])
    parser.add_argument("--progress-seconds", type=int, default=30)
    parser.add_argument(
        "--strategy",
        choices=(
            "baseline",
            "first-phase",
            "persistent-init",
            "source-init",
            "source-zero",
            "source-random",
            "heuristic",
            "hybrid",
            "mic-near",
            "mic-far",
            "mic-feedback",
            "mic-distance-feedback",
            "mic-mixed",
            "mic-structure-auto",
            "obligation-source-near",
            "obligation-source-far",
            "obligation-mixed",
            "certify-early",
            "mic-auto-obligation-near",
            "convergence-auto",
        ),
        default="baseline",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    models = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    if args.model_id:
        selected = set(args.model_id)
        models = [model for model in models if model["id"] in selected]
        missing = selected - {model["id"] for model in models}
        if missing:
            raise ValueError(f"model id(s) missing from manifest: {sorted(missing)}")
    metadata = {
        model["path"]: {
            "year": model["year"],
            "group": "ric3-hard-3600",
            "model_id": model["id"],
            "family": model["family"],
            "tier": "ric3-hard-3600",
        }
        for model in models
    }

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                f"models={event['total']} workers={args.workers} "
                f"logical_cores={4 * args.workers} timeout={args.timeout:g}",
                flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            total = int(event["total"])
            if completed % 10 == 0 or completed == total:
                print(f"completed={completed}/{total}", flush=True)

    strategy_fields: dict[str, object] = {}
    if args.strategy == "first-phase":
        strategy_fields.update(
            first_pre_phase_lanes="default,random,random,random",
            first_pre_phase_seeds="0,6,4,7",
        )
    elif args.strategy == "persistent-init":
        strategy_fields.update(
            predecessor_phase_lanes="default,target,opposite,init",
            predecessor_phase_seeds="730101,730102,730103,730104",
        )
    elif args.strategy == "source-init":
        strategy_fields.update(
            predecessor_phase_lanes="default,default,default,init",
            predecessor_phase_seeds="730101,730102,730103,730104",
        )
    elif args.strategy == "source-zero":
        strategy_fields.update(
            predecessor_phase_lanes="default,default,default,zero",
            predecessor_phase_seeds="730101,730102,730103,730104",
        )
    elif args.strategy == "source-random":
        strategy_fields.update(
            predecessor_phase_lanes="default,default,default,random-query",
            predecessor_phase_seeds="730101,730102,730103,730104",
        )
    elif args.strategy == "heuristic":
        strategy_fields.update(pdr_heuristic=True)
    elif args.strategy == "hybrid":
        strategy_fields.update(
            first_pre_phase_lanes="default,random,random,random",
            first_pre_phase_seeds="0,6,4,7",
            predecessor_phase_lanes="default,init,opposite,target",
            predecessor_phase_seeds="730101,730102,730103,730104",
        )
    elif args.strategy == "mic-near":
        strategy_fields.update(mic_order="distance-near")
    elif args.strategy == "mic-far":
        strategy_fields.update(mic_order="distance-far")
    elif args.strategy == "mic-feedback":
        strategy_fields.update(mic_order="feedback")
    elif args.strategy == "mic-distance-feedback":
        strategy_fields.update(mic_order="distance-feedback")
    elif args.strategy == "mic-mixed":
        strategy_fields.update(
            mic_order_lanes="legacy,distance-near,distance-far,feedback"
        )
    elif args.strategy == "mic-structure-auto":
        strategy_fields.update(mic_order="structure-auto")
    elif args.strategy == "obligation-source-near":
        strategy_fields.update(obligation_order="source-near")
    elif args.strategy == "obligation-source-far":
        strategy_fields.update(obligation_order="source-far")
    elif args.strategy == "obligation-mixed":
        strategy_fields.update(
            obligation_order_lanes="legacy,legacy,source-near,source-far"
        )
    elif args.strategy == "certify-early":
        strategy_fields.update(certify_early=True)
    elif args.strategy == "mic-auto-obligation-near":
        strategy_fields.update(
            mic_order="structure-auto",
            obligation_order="source-near",
        )
    elif args.strategy == "convergence-auto":
        strategy_fields.update(
            mic_order="structure-auto",
            obligation_order="source-near",
            certify_early=True,
        )

    config = {
        "id": f"aig4_{args.strategy.replace('-', '_')}",
        "label": f"MC 4xAIG {args.strategy}",
        "kind": "mc",
        "binary": str(args.binary),
        "ctg_depth": 1,
        "progress_seconds": args.progress_seconds,
        "deterministic_lanes": True,
        "minisat_elim_order": "legacy",
        "forward_aig": 4,
        "forward_xag": 0,
        **strategy_fields,
    }

    runner = ExperimentRunner(
        {
            "year": "mixed",
            "group": "ric3-hard-3600",
            "data_dir": "/home/wudl/test_tools",
            "model_paths": [model["path"] for model in models],
            "model_metadata": metadata,
            "metadata_fields": ["model_id", "family", "tier"],
            "output": str(args.output),
            "timeout": args.timeout,
            "workers": args.workers,
            "skip_existing": True,
            "mc_seed": args.seed,
            "configs": [config],
        },
        progress,
    )
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    result = runner.run()
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
