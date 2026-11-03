#!/usr/bin/env python3
"""Validate frozen first-model policies in real four-lane shared-lemma MC runs."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from compare_runner import ExperimentRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=3,
                        help="Concurrent models; each starts six four-lane portfolios")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--seed", type=int, default=510000)
    parser.add_argument("--limit-models", type=int, default=0)
    return parser.parse_args()


def mc_config(ident: str, label: str, aig: int, xag: int,
              phases: str = "", seeds: str = "") -> dict[str, object]:
    return {
        "id": ident, "label": label, "kind": "mc",
        "forward_aig": aig, "forward_xag": xag,
        "deterministic_lanes": True, "ctg_depth": 1,
        "first_pre_phase_lanes": phases,
        "first_pre_phase_seeds": seeds,
    }


def main() -> int:
    args = parse_args()
    models = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    if args.limit_models:
        models = models[:args.limit_models]
    configs = [
        mc_config("aig4_default", "4 AIG default", 4, 0),
        mc_config("xag4_default", "4 XAG default", 0, 4),
        mc_config("aig4_phase", "4 AIG phase-diverse", 4, 0,
                  "default,random,random,random", "0,6,4,7"),
        mc_config("xag4_phase", "4 XAG phase-diverse", 0, 4,
                  "default,random,random,random", "0,6,2,4"),
        mc_config("mixed4_phase", "3 AIG + 1 XAG phase-diverse", 3, 1,
                  "random,random,random,zero", "8,4,6,0"),
        mc_config("mixed4_struct", "2 AIG + 2 XAG structural", 2, 2,
                  "one,zero,zero,default", "0,0,0,0"),
    ]
    for config in configs:
        config["binary"] = str(args.binary)

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(f"models={event['total']} configs={len(configs)} workers={args.workers}", flush=True)
        elif event.get("type") == "row":
            done = int(event["completed"])
            if done % 5 == 0 or done == int(event["total"]):
                print(f"completed={done}/{event['total']}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed", "group": "holdout", "model_paths": [m["path"] for m in models],
        "output": str(args.output), "timeout": args.timeout,
        "workers": args.workers, "skip_existing": True,
        "mc_seed": args.seed, "configs": configs,
    }, progress)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    result = runner.run()
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
