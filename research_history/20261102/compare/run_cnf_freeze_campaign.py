#!/usr/bin/env python3
"""Run paired four-lane experiments for selective MiniSat variable retention."""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path
from typing import Any

from compare_runner import ExperimentRunner


SCREEN_POLICIES = [
    ("aig_none", "AIG baseline", "aig", "none", 4),
    ("aig_all", "AIG freeze all gates", "aig", "all", 4),
    ("aig_high2", "AIG freeze fanout >= 2", "aig", "high-fanout", 2),
    ("aig_high4", "AIG freeze fanout >= 4", "aig", "high-fanout", 4),
    ("aig_high8", "AIG freeze fanout >= 8", "aig", "high-fanout", 8),
    ("aig_shared", "AIG freeze shared cone", "aig", "shared", 4),
    ("aig_bad", "AIG freeze bad cone", "aig", "bad", 4),
    ("aig_hybrid2", "AIG shared or fanout >= 2", "aig", "hybrid", 2),
    ("aig_hybrid4", "AIG shared or fanout >= 4", "aig", "hybrid", 4),
    ("xag_none", "XAG baseline", "xag", "none", 4),
    ("xag_high4", "XAG freeze fanout >= 4", "xag", "high-fanout", 4),
    ("xag_shared", "XAG freeze shared cone", "xag", "shared", 4),
    ("xag_xor", "XAG freeze XOR outputs", "xag", "xor", 4),
    ("xag_hybrid4", "XAG shared or fanout >= 4", "xag", "hybrid", 4),
]

HARD_POLICIES = [
    policy for policy in SCREEN_POLICIES
    if policy[0] in {
        "aig_none", "aig_all", "aig_high2", "aig_high4", "aig_high8",
        "aig_shared", "aig_hybrid2", "aig_hybrid4", "xag_none",
        "xag_high4", "xag_shared", "xag_xor", "xag_hybrid4",
    }
]


def policies_for_suite(suite: str) -> list[tuple[str, str, str, str, int]]:
    return SCREEN_POLICIES if suite == "screen" else HARD_POLICIES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=("screen", "hard"), required=True)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--limit-models", type=int, default=0)
    return parser.parse_args()


def make_config(
    policy: tuple[str, str, str, str, int], binary: Path, seed: int,
) -> dict[str, Any]:
    ident, label, representation, freeze_policy, fanout = policy
    config: dict[str, Any] = {
        "id": ident,
        "label": label,
        "kind": "mc",
        "binary": str(binary),
        "forward_aig": 4 if representation == "aig" else 0,
        "forward_xag": 4 if representation == "xag" else 0,
        "ctg_depth": 1,
        "deterministic_lanes": True,
        "minisat_freeze_policy": freeze_policy,
        "minisat_freeze_fanout": fanout,
    }
    # Each treatment sees the same four seeds; the next campaign changes all four.
    config["predecessor_phase_seeds"] = ",".join(
        str(seed + offset) for offset in (101, 103, 107, 109)
    )
    return config


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    models = manifest["models"]
    if args.suite == "hard":
        models = [model for model in models if model.get("tier") in {"slow", "timeout"}]
    if args.limit_models:
        models = models[: args.limit_models]

    policies = policies_for_suite(args.suite)
    configs = [make_config(policy, args.binary, args.seed) for policy in policies]

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                f"suite={args.suite} models={event['total']} configs={len(configs)} "
                f"workers={args.workers} logical_lanes={len(configs) * 4 * args.workers}",
                flush=True,
            )
        elif event.get("type") == "row":
            done = int(event["completed"])
            if done % 5 == 0 or done == int(event["total"]):
                print(f"completed={done}/{event['total']}", flush=True)

    runner = ExperimentRunner({
        "year": "mixed",
        "group": f"cnf-freeze-{args.suite}",
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
