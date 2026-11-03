#!/usr/bin/env python3
"""Find cross-build multi-property systems using AIGER signal identities.

This is a permissive candidate screen.  Matching signal layouts do not by
themselves prove transition equivalence; every transferred invariant must
still be revalidated on the target transition relation.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from analyze_invariant_semantics import read_symbols
from remap_pdr_invariant_symbols import read_input_symbols


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--hard-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=64)
    return parser.parse_args()


def models(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, dict):
        payload = payload["models"]
    if not isinstance(payload, list):
        raise ValueError("expected model list")
    return payload


def fingerprint(model: dict[str, object]) -> tuple[str, dict[str, object]]:
    path = Path(str(model["path"]))
    with path.open("rb") as stream:
        header = stream.readline().decode("ascii").split()
    if header[0] not in {"aig", "aag"}:
        raise ValueError(f"unsupported AIGER header: {path}")
    inputs = int(header[2])
    latches = int(header[3])
    constraints = int(header[7]) if len(header) > 7 else 0
    latch_names = sorted(read_symbols(path).values())
    input_names = sorted(read_input_symbols(path).values())
    state = hashlib.sha256()
    state.update(
        f"I={inputs};L={latches};C={constraints};".encode("ascii")
    )
    for tag, names in ((b"i", input_names), (b"l", latch_names)):
        state.update(tag)
        for name in names:
            encoded = name.encode("utf-8")
            state.update(len(encoded).to_bytes(4, "big"))
            state.update(encoded)
    enriched = dict(model)
    enriched["inputs"] = inputs
    enriched["latches"] = latches
    enriched["constraints"] = constraints
    enriched["named_inputs"] = len(input_names)
    enriched["named_latches"] = len(latch_names)
    return state.hexdigest(), enriched


def main() -> int:
    args = parse_args()
    all_models = models(json.loads(args.manifest.read_text(encoding="utf-8")))
    hard_ids = {
        str(model["id"])
        for model in models(json.loads(args.hard_manifest.read_text(encoding="utf-8")))
    }
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        for index, (signature, model) in enumerate(
            executor.map(fingerprint, all_models), 1
        ):
            groups[signature].append(model)
            if index % 100 == 0 or index == len(all_models):
                print(f"scanned={index}/{len(all_models)}", flush=True)

    candidates = []
    for signature, members in groups.items():
        hard = [model for model in members if str(model["id"]) in hard_ids]
        safe = [model for model in members if model.get("baseline_status") == "SAFE"]
        if not hard or not safe:
            continue
        candidates.append(
            {
                "signature": signature,
                "size": len(members),
                "families": sorted({str(model.get("family", "")) for model in members}),
                "years": sorted({int(model["year"]) for model in members}),
                "hard_count": len(hard),
                "safe_source_count": len(safe),
                "hard": hard,
                "safe_sources": sorted(
                    safe,
                    key=lambda model: float(model.get("baseline_seconds", 1e30)),
                ),
                "members": members,
            }
        )
    candidates.sort(
        key=lambda group: (-int(group["hard_count"]), -int(group["size"]), group["signature"])
    )
    payload = {
        "schema": "symbol-layout-groups-v1",
        "model_count": len(all_models),
        "hard_count": len(hard_ids),
        "candidate_group_count": len(candidates),
        "hard_models_in_candidates": len(
            {str(model["id"]) for group in candidates for model in group["hard"]}
        ),
        "groups": candidates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"candidate_groups={len(candidates)} "
        f"candidate_hard={payload['hard_models_in_candidates']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
