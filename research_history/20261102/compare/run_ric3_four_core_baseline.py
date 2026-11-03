#!/usr/bin/env python3
"""Screen upstream rIC3 workers and derive a strong four-core baseline."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from compare_runner import ExperimentRunner


CONFIGS = [
    ("ic3", "IC3 default", "ic3", ""),
    ("ic3_no_preproc", "IC3 no preprocessing", "ic3", "--ctg=false --frts=false --scorr=false --drop-po=false"),
    ("ic3_no_parent", "IC3 no parent lemma", "ic3", "--drop-po=false --parent-lemma=false"),
    ("ic3_abs_all", "IC3 local abstraction", "ic3", "--abs-cst --abs-trans"),
    ("ic3_predprop", "IC3 predecessor propagation", "ic3", "--pred-prop"),
    ("ic3_ctg_limit", "IC3 extended CTG", "ic3", "--ctg-max 5 --ctg-limit 15 --drop-po=false"),
    ("ic3_inn", "IC3 internal signals", "ic3", "--inn"),
    ("ic3_inn_ctp", "IC3 internal signals CTP", "ic3", "--inn --ctp"),
    ("ic3_inn_noctg", "IC3 internal signals no CTG", "ic3", "--inn --ctg=false"),
    ("ic3_inn_dynamic", "IC3 internal signals dynamic", "ic3", "--inn --dynamic --drop-po=false"),
    ("bmc_step1", "BMC step 1", "bmc", "--step 1"),
    ("bmc_kissat_dyn", "BMC Kissat dynamic", "bmc", "--kissat --dyn-step"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=6,
                        help="Concurrent models; each starts 12 single-core workers")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--seed", type=int, default=410000)
    parser.add_argument("--limit-models", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    models = json.loads(args.manifest.read_text(encoding="utf-8"))["models"]
    if args.limit_models:
        models = models[:args.limit_models]
    configs = [
        {
            "id": ident, "label": label, "kind": "ric3",
            "binary": str(args.binary), "engine": engine,
            "aig_encoding": "native", "replicas": 1,
            "seed": args.seed, "extra_args": extra,
        }
        for ident, label, engine, extra in CONFIGS
    ]
    last = {"completed": 0}

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(f"models={event['total']} configs={len(configs)} workers={args.workers}", flush=True)
        elif event.get("type") == "row":
            completed = int(event["completed"])
            if completed % 5 == 0 or completed == int(event["total"]):
                print(f"completed={completed}/{event['total']}", flush=True)
            last["completed"] = completed

    runner = ExperimentRunner({
        "year": "mixed", "group": "holdout", "model_paths": [m["path"] for m in models],
        "output": str(args.output), "timeout": args.timeout,
        "workers": args.workers, "skip_existing": True, "configs": configs,
    }, progress)
    signal.signal(signal.SIGINT, lambda *_: runner.cancel())
    signal.signal(signal.SIGTERM, lambda *_: runner.cancel())
    result = runner.run()
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
