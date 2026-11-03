#!/usr/bin/env python3
"""Run the frozen rIC3 four-worker control with lemma sharing on and off."""

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
    parser.add_argument("--workers", type=int, default=9,
                        help="Concurrent models; each starts two four-worker portfolios")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--limit-models", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    models = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    if args.limit_models:
        models = models[:args.limit_models]
    base = {
        "kind": "ric3", "binary": str(args.binary), "engine": "portfolio",
        "aig_encoding": "native", "replicas": 1, "seed": 610000,
    }
    configs = [
        dict(base, id="ric3_4_noshare", label="rIC3-4 no sharing",
             extra_args="--config bl_4core_control"),
        dict(base, id="ric3_4_share", label="rIC3-4 shared lemmas",
             extra_args="--config bl_4core_control --share-lemma"),
    ]

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(f"models={event['total']} configs=2 workers={args.workers}", flush=True)
        elif event.get("type") == "row":
            done = int(event["completed"])
            if done % 5 == 0 or done == int(event["total"]):
                print(f"completed={done}/{event['total']}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed", "group": "holdout", "data_dir": "/home/wudl/test_tools",
        "model_paths": [m["path"] for m in models], "output": str(args.output),
        "timeout": args.timeout, "workers": args.workers,
        "skip_existing": True, "configs": configs,
    }, progress)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    result = runner.run()
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
