#!/usr/bin/env python3
"""Regenerate the UNSAFE cohort and validate its deterministic witnesses."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pathb.aag_writer import to_aag_text  # noqa: E402
from pathb.blif_writer import to_blif_text  # noqa: E402
from pathb.generate import build_benchmark  # noqa: E402


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def witness_stream(net, family: str, depth: int) -> list[dict[int, int]]:
    stream = [{signal: 0 for signal in net.inputs} for _ in range(depth + 1)]
    if family == "crc_frame_align_unsafe":
        # The first two inputs are SOF and valid.  Align before observing the
        # delayed fault, and keep the data path active afterward.
        stream[0][net.inputs[0]] = 1
        for values in stream:
            values[net.inputs[1]] = 1
    return stream


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--specs", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    specs = json.loads(args.specs.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if len(specs) != len(manifest):
        raise SystemExit("spec/manifest size mismatch")

    failures: list[tuple[str, str]] = []
    for spec, frozen in zip(specs, manifest):
        entry = build_benchmark(spec["family"], spec)
        net = entry["net"]
        depth = int(spec["witness_depth"])
        if entry["expected"] != "UNSAFE" or frozen["expected"] != "UNSAFE":
            failures.append((frozen["stem"], "expected label is not UNSAFE"))
        if digest(to_aag_text(net)) != frozen["aag_sha256"]:
            failures.append((frozen["stem"], "AAG hash mismatch"))
        if digest(to_blif_text(net)) != frozen["blif_sha256"]:
            failures.append((frozen["stem"], "BLIF hash mismatch"))
        reached, observed = net.evaluate_sequential(
            {}, witness_stream(net, spec["family"], depth)
        )
        if not reached or observed != depth:
            failures.append((
                frozen["stem"],
                f"expected bad at depth {depth}, observed {observed}",
            ))

    if failures:
        for stem, reason in failures:
            print(f"FAIL {stem}: {reason}")
        raise SystemExit(f"UNSAFE suite validation failed: {len(failures)} errors")
    print(json.dumps({"models": len(manifest), "status": "PASS"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
