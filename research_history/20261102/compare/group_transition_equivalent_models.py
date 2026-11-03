#!/usr/bin/env python3
"""Group safety models that share Init, constraints, and next-state logic."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import struct
from collections import defaultdict
from pathlib import Path

from analyze_aig_deep_structure import Aag, BinaryAig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--converter",
        type=Path,
        default=Path(
            "/home/wudl/Modelchecker-bidirectional/modelchecker/aigtoaig"
        ),
    )
    parser.add_argument(
        "--family",
        action="append",
        default=[],
        help="Only group models from this family (repeatable).",
    )
    parser.add_argument("--workers", type=int, default=1)
    return parser.parse_args()


MASK64 = (1 << 64) - 1


def mix64(value: int) -> int:
    value = (value + 0x9E3779B97F4A7C15) & MASK64
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK64
    return value ^ (value >> 31)


def leaf_hash(tag: int, index: int) -> tuple[int, int]:
    return mix64(tag ^ index), mix64((tag << 1) ^ index ^ 0xD6E8FEB86659FD93)


def and_hash(
    left: tuple[int, int], right: tuple[int, int]
) -> tuple[int, int]:
    return (
        mix64(left[0] ^ mix64(right[0] ^ 0xA0761D6478BD642F)),
        mix64(left[1] ^ mix64(right[1] ^ 0xE7037ED1A0B428DB)),
    )


def transition_signature(aig: Aag) -> str:
    node_hashes: list[tuple[int, int]] = [(0, 0)] * (aig.maxvar + 1)
    node_hashes[0] = leaf_hash(0xC01157, 0)
    for index in range(aig.inputs):
        node_hashes[index + 1] = leaf_hash(0x1A2B3C, index)
    for index in range(aig.latches):
        variable = aig.inputs + index + 1
        node_hashes[variable] = leaf_hash(0x4D5E6F, index)

    def literal_hash(literal: int) -> tuple[int, int]:
        base = node_hashes[literal >> 1]
        if not literal & 1:
            return base
        return (
            mix64(base[0] ^ 0x8EBC6AF09C88C6E3),
            mix64(base[1] ^ 0x589965CC75374CC3),
        )

    for variable in range(aig.gate_start, aig.maxvar + 1):
        if not aig.is_gate(variable):
            continue
        children = sorted(
            (literal_hash(aig.left[variable]), literal_hash(aig.right[variable]))
        )
        node_hashes[variable] = and_hash(children[0], children[1])

    next_hashes = [literal_hash(literal) for literal in aig.next_lits]
    constraint_hashes = sorted(literal_hash(literal) for literal in aig.constraint_lits)
    init_hashes: list[tuple[int, int]] = []
    for index, literal in enumerate(aig.latch_init_lits):
        current = 2 * (aig.inputs + index + 1)
        normalized = 0 if literal is None else literal
        if normalized == current:
            init_hashes.append(leaf_hash(0x1A17, index))
        elif normalized in (0, 1):
            init_hashes.append(leaf_hash(0x1A10, normalized))
        else:
            reset = literal_hash(normalized)
            init_hashes.append(
                (mix64(reset[0] ^ 0x7E5E7), mix64(reset[1] ^ 0x7E5E8))
            )

    header = (
        f"inputs={aig.inputs};latches={aig.latches};"
        f"constraints={aig.constraints}"
    ).encode("ascii")
    digest = hashlib.sha256()
    digest.update(b"transition-v2\0")
    digest.update(header)
    for tag, hashes in (
        (b"next", next_hashes),
        (b"constraints", constraint_hashes),
        (b"init", init_hashes),
    ):
        digest.update(tag)
        digest.update(len(hashes).to_bytes(8, "big"))
        for first, second in hashes:
            digest.update(struct.pack(">QQ", first, second))
    return digest.hexdigest()


def load_models(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    models = payload["models"] if isinstance(payload, dict) else payload
    if not isinstance(models, list):
        raise ValueError("manifest must be a list or an object with a models list")
    return models


def coarse_signature(model: dict[str, object]) -> tuple[str, int, int, int]:
    source = Path(str(model["path"]))
    with source.open("rb") as stream:
        header = stream.readline().decode("ascii").split()
    if len(header) < 6 or header[0] not in {"aig", "aag"}:
        raise ValueError(f"invalid AIGER header: {source}")
    inputs = int(header[2])
    latches = int(header[3])
    constraints = int(header[7]) if len(header) > 7 else 0
    return str(model.get("family", "")), inputs, latches, constraints


def hash_model(model: dict[str, object]) -> tuple[str, dict[str, object]]:
    source = Path(str(model["path"]))
    parser = Aag if source.suffix == ".aag" else BinaryAig
    return transition_signature(parser(source)), model


def main() -> int:
    args = parse_args()
    models = load_models(args.manifest)
    if args.family:
        selected = set(args.family)
        models = [model for model in models if str(model.get("family", "")) in selected]
        missing = sorted(selected - {str(model.get("family", "")) for model in models})
        if missing:
            raise ValueError(f"families not present in manifest: {', '.join(missing)}")
    coarse_groups: dict[tuple[str, int, int, int], list[dict[str, object]]] = (
        defaultdict(list)
    )
    for model in models:
        coarse_groups[coarse_signature(model)].append(model)
    eligible = [
        model
        for members in coarse_groups.values()
        if len(members) > 1
        for model in members
    ]
    skipped_singletons = len(models) - len(eligible)
    print(
        f"coarse_groups={len(coarse_groups)} eligible={len(eligible)}/{len(models)}",
        flush=True,
    )

    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
        for index, (signature, model) in enumerate(
            executor.map(hash_model, eligible), 1
        ):
            groups[signature].append(model)
            if index % 50 == 0 or index == len(eligible):
                print(f"hashed={index}/{len(eligible)}", flush=True)

    repeated = [
        {"signature": signature, "size": len(members), "models": members}
        for signature, members in groups.items()
        if len(members) > 1
    ]
    repeated.sort(key=lambda group: (-int(group["size"]), str(group["signature"])))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "schema": "transition-equivalent-groups-v1",
                "model_count": len(models),
                "coarse_candidate_count": len(eligible),
                "group_count": skipped_singletons + len(groups),
                "repeated_group_count": len(repeated),
                "models_in_repeated_groups": sum(int(group["size"]) for group in repeated),
                "groups": repeated,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"groups={skipped_singletons + len(groups)} repeated={len(repeated)} "
        f"repeated_models={sum(int(group['size']) for group in repeated)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
