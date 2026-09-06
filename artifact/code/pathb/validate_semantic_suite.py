#!/usr/bin/env python3
"""Structural and randomized sequential validation for the semantic suite."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pathb.aag_writer import to_aag_text
from pathb.blif_writer import to_blif_text
from pathb.generate import build_benchmark


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--specs", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=8)
    parser.add_argument("--steps", type=int, default=8)
    args = parser.parse_args()

    specs = json.loads(args.specs.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if len(specs) != len(manifest):
        raise SystemExit("spec/manifest size mismatch")

    failures = []
    for model_index, (spec, frozen) in enumerate(zip(specs, manifest)):
        entry = build_benchmark(spec["family"], spec)
        net = entry["net"]
        if entry["expected"] != "SAFE" or frozen["expected"] != "SAFE":
            failures.append((frozen["stem"], "unexpected non-SAFE label"))
            continue
        if digest(to_aag_text(net)) != frozen["aag_sha256"]:
            failures.append((frozen["stem"], "AAG hash mismatch"))
        if digest(to_blif_text(net)) != frozen["blif_sha256"]:
            failures.append((frozen["stem"], "BLIF hash mismatch"))
        if net.stats() != frozen["stats"]:
            failures.append((frozen["stem"], "gate statistics mismatch"))

        for trial in range(args.trials):
            rng = random.Random(0x5EED_1000 + model_index * 1009 + trial)
            stream = [
                {signal: rng.getrandbits(1) for signal in net.inputs}
                for _ in range(args.steps)
            ]
            reached_bad, bad_step = net.evaluate_sequential({}, stream)
            if reached_bad:
                failures.append((frozen["stem"], f"random trace reached bad at {bad_step}"))
                break

    if failures:
        for stem, reason in failures:
            print(f"FAIL {stem}: {reason}")
        raise SystemExit(f"semantic suite validation failed: {len(failures)} errors")

    print(json.dumps({
        "models": len(manifest),
        "random_traces": len(manifest) * args.trials,
        "steps_per_trace": args.steps,
        "categories": dict(sorted(Counter(
            item["classification"]["category"] for item in manifest
        ).items())),
        "status": "PASS",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
