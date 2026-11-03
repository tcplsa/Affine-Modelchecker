#!/usr/bin/env python3
"""Plan invariant transfer from solved properties to hard sibling properties."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--groups", type=Path, required=True)
    parser.add_argument("--hard-manifest", type=Path, required=True)
    parser.add_argument(
        "--source-manifest",
        type=Path,
        help=(
            "Select SAFE source candidates from this manifest by family and "
            "AIGER header. Target-side validation remains mandatory."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sources-per-group", type=int, default=3)
    parser.add_argument("--source-time-limit", type=float, default=120.0)
    return parser.parse_args()


def models(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, dict):
        payload = payload["models"]
    if not isinstance(payload, list):
        raise ValueError("expected a model list")
    return payload


def coarse_signature(model: dict[str, object]) -> tuple[str, int, int, int]:
    with Path(str(model["path"])).open("rb") as stream:
        header = stream.readline().decode("ascii").split()
    if len(header) < 6 or header[0] not in {"aig", "aag"}:
        raise ValueError(f"invalid AIGER header: {model['path']}")
    return (
        str(model.get("family", "")),
        int(header[2]),
        int(header[3]),
        int(header[7]) if len(header) > 7 else 0,
    )


def main() -> int:
    args = parse_args()
    groups = json.loads(args.groups.read_text(encoding="utf-8"))["groups"]
    hard = models(json.loads(args.hard_manifest.read_text(encoding="utf-8")))
    hard_ids = {str(model["id"]) for model in hard}
    source_pool: dict[tuple[str, int, int, int], list[dict[str, object]]] = {}
    if args.source_manifest:
        source_models = models(
            json.loads(args.source_manifest.read_text(encoding="utf-8"))
        )
        for model in source_models:
            source_pool.setdefault(coarse_signature(model), []).append(model)

    plan: list[dict[str, object]] = []
    for group in groups:
        members = group["models"]
        targets = [model for model in members if str(model["id"]) in hard_ids]
        candidates = (
            source_pool.get(coarse_signature(targets[0]), [])
            if args.source_manifest
            else members
        )
        sources = [
            model
            for model in candidates
            if str(model["id"]) not in hard_ids
            and str(model.get("baseline_status", "")).upper() == "SAFE"
            and float(model.get("baseline_seconds", float("inf")))
            <= args.source_time_limit
        ]
        if not targets or not sources:
            continue
        sources.sort(key=lambda model: float(model.get("baseline_seconds", float("inf"))))
        plan.append(
            {
                "signature": group["signature"],
                "source_match": "coarse" if args.source_manifest else "exact",
                "family": str(targets[0].get("family", "")),
                "targets": targets,
                "sources": sources[: args.sources_per_group],
                "all_safe_source_count": len(sources),
            }
        )

    plan.sort(key=lambda item: (-len(item["targets"]), str(item["family"])))
    output = {
        "schema": "transition-invariant-transfer-plan-v1",
        "group_count": len(plan),
        "target_count": sum(len(item["targets"]) for item in plan),
        "source_count": sum(len(item["sources"]) for item in plan),
        "groups": plan,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"groups={output['group_count']} targets={output['target_count']} "
        f"sources={output['source_count']}"
    )
    for item in plan:
        source_ids = ",".join(str(model["id"]) for model in item["sources"])
        print(
            f"family={item['family']} targets={len(item['targets'])} "
            f"sources={source_ids}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
