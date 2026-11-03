#!/usr/bin/env python3
"""Show phase, trace, replay, and disk progress for all three shards."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DESIGN = ROOT / "results" / "cnf_presentation_causal_design_v1"
RESULTS = ROOT / "results" / "cnf_presentation_phase_v1"


def rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def main() -> int:
    for role in ("server-a", "server-b", "server-c"):
        manifest = json.loads((DESIGN / f"manifest_{role}.json").read_text(encoding="utf-8"))
        phase_expected = 195 * 3 * 4
        trace_expected = sum(len(model["trace_runs"]) for model in manifest["models"]) * 2
        root = RESULTS / role
        phase = rows(root / "phase_results.tsv")
        trace = rows(root / "trace_summary.tsv")
        replay = rows(root / "replay_results.tsv")
        trace_files = sum(1 for _ in (root / "traces").rglob("*.mcpdrq")) if (root / "traces").exists() else 0
        replay_expected = trace_files * 4 if trace else 0
        print(
            f"{role}: phase={len(phase)}/{phase_expected} "
            f"trace={len(trace)}/{trace_expected} "
            f"replay={len(replay)}/{replay_expected or '?'} "
            f"disk={size(root) / (1024 ** 3):.2f}GiB"
        )
        if phase:
            print(f"  phase statuses: {dict(Counter(row['status'] for row in phase))}")
        if trace:
            print(f"  trace statuses: {dict(Counter(row['status'] for row in trace))}")
        if replay:
            print(f"  replay statuses: {dict(Counter(row['replay_status'] for row in replay))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
