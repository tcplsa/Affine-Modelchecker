#!/usr/bin/env python3
"""Test retaining three default lanes plus one source-directed lane."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from compare_runner import ExperimentRunner


POLICIES = [
    ("aig4_default", "4AIG default", ""),
    ("aig3_init1", "3AIG default + 1 init", "default,default,default,init"),
    ("aig3_zero1", "3AIG default + 1 zero", "default,default,default,zero"),
    (
        "aig3_random1",
        "3AIG default + 1 random-query",
        "default,default,default,random-query",
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--limit-models", type=int, default=0)
    parser.add_argument("--seed", type=int, default=730001)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    models = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    if args.limit_models:
        models = models[:args.limit_models]
    configs = [{
        "id": ident,
        "label": label,
        "kind": "mc",
        "binary": str(args.binary),
        "forward_aig": 4,
        "ctg_depth": 1,
        "deterministic_lanes": True,
        "predecessor_phase_lanes": lanes,
        "predecessor_phase_seeds": "730101,730102,730103,730104",
    } for ident, label, lanes in POLICIES]

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                f"models={event['total']} configs={len(configs)} workers={args.workers}",
                flush=True,
            )
        elif event.get("type") == "row":
            done = int(event["completed"])
            if done % 5 == 0 or done == int(event["total"]):
                print(f"completed={done}/{event['total']}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed",
        "group": "holdout",
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
