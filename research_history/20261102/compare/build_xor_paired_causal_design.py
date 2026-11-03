#!/usr/bin/env python3
"""Build single-XOR remove/add-back interventions for the AllInterval pair."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from extract_xor_gate_features import rows_for_model  # noqa: E402


TARGETS = {
    "2024__AllInterval-019": "server-a",
    "2025__AllInterval-020": "server-b",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def keep_retain248(row: dict[str, str]) -> bool:
    fanout = int(row["fanout"])
    adjacent = int(row["fanin_xor_count"]) + int(row["fanout_xor_count"]) > 0
    parent = (
        int(row["in_next"]) == 1
        and fanout >= 2
        and int(row["impl_child_external_fanouts"]) == 0
    )
    return (
        not parent
        or fanout >= 4
        or (fanout in (2, 3) and int(row["distance_to_next"]) > 8 and adjacent)
    )


def write_allowlist(path: Path, variables: set[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{value}\n" for value in sorted(variables) or [0]), encoding="ascii")


def gate_metadata(row: dict[str, str]) -> dict[str, object]:
    fields = (
        "xor_var", "fanin0_var", "fanin1_var", "fanin0_sign", "fanin1_sign",
        "fanout", "depth", "relative_depth", "distance_to_next",
        "distance_to_bad", "in_next", "in_bad", "in_shared", "cone_class",
        "direct_next_root", "direct_bad_root", "impl_child0_var", "impl_child1_var",
        "impl_child_external_fanouts",
        "fanin_xor_count", "fanout_xor_count", "support0_size", "support1_size",
        "support_overlap", "support_jaccard",
    )
    integers = {
        "xor_var", "fanin0_var", "fanin1_var", "fanin0_sign", "fanin1_sign",
        "fanout", "depth", "distance_to_next", "distance_to_bad",
        "in_next", "in_bad", "in_shared", "direct_next_root", "direct_bad_root",
        "impl_child0_var", "impl_child1_var", "impl_child_external_fanouts",
        "fanin_xor_count", "fanout_xor_count",
        "support0_size", "support1_size", "support_overlap",
    }
    result: dict[str, object] = {}
    for field in fields:
        value = row[field]
        result[field] = int(value) if field in integers else value
    return result


def main() -> int:
    args = parse_args()
    source = json.loads(args.source_manifest.read_text(encoding="utf-8"))
    by_id = {model["id"]: model for model in source["models"]}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    allowlist_dir = args.output_dir / "allowlists"
    models = []
    for model_id, shard in TARGETS.items():
        source_model = by_id[model_id]
        path = Path(source_model["path"])
        # Support is not part of retain248; keep this pass linear even on 15k-XOR models.
        rows = rows_for_model(path, support_limit=1)
        by_var = {int(row["xor_var"]): row for row in rows}
        all_vars = set(by_var)
        retained = {var for var, row in by_var.items() if keep_retain248(row)}
        affected = sorted(all_vars - retained)
        if len(affected) != source_model["removed_xors"]:
            raise SystemExit(f"retain248 mismatch for {model_id}")

        model_dir = allowlist_dir / model_id
        variants = []
        full_path = model_dir / "baseline_full.allow"
        retain_path = model_dir / "baseline_retain248.allow"
        write_allowlist(full_path, all_vars)
        write_allowlist(retain_path, retained)
        variants.extend([
            {
                "id": "baseline_full",
                "kind": "baseline_full",
                "xor_var": 0,
                "selected_xors": len(all_vars),
                "allowlist": str(full_path),
            },
            {
                "id": "baseline_retain248",
                "kind": "baseline_retain248",
                "xor_var": 0,
                "selected_xors": len(retained),
                "allowlist": str(retain_path),
            },
        ])
        for var in affected:
            remove_path = model_dir / f"remove_{var}.allow"
            addback_path = model_dir / f"addback_{var}.allow"
            write_allowlist(remove_path, all_vars - {var})
            write_allowlist(addback_path, retained | {var})
            variants.extend([
                {
                    "id": f"remove_{var}",
                    "kind": "single_remove",
                    "xor_var": var,
                    "selected_xors": len(all_vars) - 1,
                    "allowlist": str(remove_path),
                },
                {
                    "id": f"addback_{var}",
                    "kind": "single_addback",
                    "xor_var": var,
                    "selected_xors": len(retained) + 1,
                    "allowlist": str(addback_path),
                },
            ])
        models.append({
            "id": model_id,
            "name": source_model["name"],
            "year": source_model["year"],
            "path": str(path),
            "shard": shard,
            "total_xors": len(all_vars),
            "retained_xors": len(retained),
            "affected_xors": len(affected),
            "affected_gates": [gate_metadata(by_var[var]) for var in affected],
            "variants": variants,
        })
        print(f"model={model_id} affected={len(affected)} variants={len(variants)} shard={shard}")

    manifest = {
        "version": 1,
        "experiment": "allinterval_single_xor_causal",
        "hypotheses": {
            "single_remove": "Is deleting this XOR from Full-XAG sufficient to change behavior?",
            "single_addback": "Is restoring this XOR to retain248 sufficient to change behavior?",
        },
        "models": models,
    }
    output = args.output_dir / "manifest.json"
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"manifest={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
