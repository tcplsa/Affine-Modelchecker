#!/usr/bin/env python3
"""Freeze a deduplicated corpus for the complete affine-datapath study."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


TARGET_MANIFESTS = (
    "results/pathb_shallow_linear_scope_v1/benchmarks/manifest.json",
    "results/pathb_linear_scope_generalization_v1/benchmarks/manifest.json",
    "results/pathb_affine_summary_margin_v1/benchmarks/manifest.json",
    "results/pathb_guarded_affine_margin_v1/benchmarks/manifest.json",
    "results/pathb_crc_frame_lock_v1/benchmarks/manifest.json",
    "results/pathb_real_xor_apps_v1/benchmarks/manifest.json",
    "results/pathb_crc_gauss_boundary_v1/benchmarks/manifest.json",
    "results/pathb_crc_gauss_boundary_fine_v1/benchmarks/manifest.json",
)

BOUNDARY_MANIFESTS = (
    "results/pathb_crc_frame_residue_v1/benchmarks/manifest.json",
    "results/pathb_affine_phase_sync_v1/benchmarks/manifest.json",
    "results/pathb_affine_phase_sync_frontier_v1/benchmarks/manifest.json",
    "results/pathb_semantic_100_v1/benchmarks/manifest.json",
)

TARGET_FAMILIES = {
    "crc_frame_align",
    "crc_frame_lock",
    "lfsr_jump_equiv",
    "scrambler_equiv",
    "scrambler_recovery",
    "syndrome_equiv",
}


def resolve_model(root: Path, raw: str) -> Path:
    path = Path(raw)
    candidates = (path, root / path, root.parent.parent / path)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(raw)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    selected: dict[str, dict[str, object]] = {}

    for scope, manifests in (
        ("target", TARGET_MANIFESTS),
        ("boundary", BOUNDARY_MANIFESTS),
    ):
        for relative_manifest in manifests:
            manifest = root / relative_manifest
            for model in json.loads(manifest.read_text(encoding="utf-8")):
                family = str(model.get("family", "unknown"))
                model_scope = scope
                if scope == "target" and family not in TARGET_FAMILIES:
                    model_scope = "boundary"
                path = resolve_model(root, str(model["paths"]["aag"]))
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest in selected:
                    sources = selected[digest]["source_manifests"]
                    assert isinstance(sources, list)
                    sources.append(relative_manifest)
                    if model_scope == "target":
                        selected[digest]["scope"] = "target"
                    continue
                selected[digest] = {
                    "name": path.stem,
                    "path": str(path),
                    "paths": {"aag": str(path)},
                    "sha256": digest,
                    "scope": model_scope,
                    "family": family,
                    "category": model.get("category")
                    or model.get("classification", {}).get("category", ""),
                    "expected": model.get("expected", "UNKNOWN"),
                    "source_manifests": [relative_manifest],
                }

    models = sorted(
        selected.values(),
        key=lambda model: (
            str(model["scope"]), str(model["family"]), str(model["name"])
        ),
    )
    payload = {
        "schema": 1,
        "description": "Deduplicated complete affine/guarded-affine application scope",
        "models": models,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for model in models:
        key = f"{model['scope']}:{model['family']}"
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps({"models": len(models), "counts": counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

