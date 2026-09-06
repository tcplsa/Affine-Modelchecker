#!/usr/bin/env python3
"""Freeze the complete public HWMCC24 ILA_AES AIG target set."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
REPO = ROOT / "test_tools/compare/external_linear_rtl/hwmcc24-benchmark"
SOURCE_DIR = REPO / "aiger_only"
OUTPUT = ROOT / "test_tools/compare/results/pathb_hwmcc24_ila_aes_v1/manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument(
        "--targets",
        nargs="*",
        default=[],
        help="Optional target names such as IntermediateRound FinalRound",
    )
    args = parser.parse_args()
    paths = sorted(SOURCE_DIR.glob("ILA_AES_*.aig"))
    if len(paths) != 17:
        raise RuntimeError(f"expected 17 ILA_AES AIG targets, found {len(paths)}")
    commit = subprocess.check_output(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True
    ).strip()
    models = []
    for path in paths:
        target = path.stem[len("ILA_AES_") : -len("_problem")]
        if args.targets and target not in args.targets:
            continue
        models.append({
            "name": path.stem,
            "path": str(path.resolve()),
            "scope": "public-hwmcc24-aes",
            "family": "hwmcc24_ila_aes",
            "category": "public-rtl-refinement",
            "expected": "SAFE",
            "params": {"target": target},
            "source": "https://github.com/Gy-Hu/HWMCC24-benchmark",
            "source_commit": commit,
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
        })
    payload = {
        "schema": 1,
        "description": "All 17 public ILA_AES refinement AIG targets submitted with HWMCC24",
        "source_commit": commit,
        "models": models,
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"models": len(models), "output": str(output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
