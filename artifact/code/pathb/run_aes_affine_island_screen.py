#!/usr/bin/env python3
"""Screen flattened XOR-island summaries on the public HWMCC24 AES targets."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compare_runner import ExperimentRunner  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=1013001)
    parser.add_argument(
        "--configs", default="",
        help="Comma-separated configuration IDs; empty runs every configuration",
    )
    parser.add_argument(
        "--name-pattern", default="",
        help="Keep only models whose manifest name contains this string",
    )
    parser.add_argument(
        "--repeat-seeds", default="",
        help="Comma-separated MC seeds; duplicates each selected configuration",
    )
    args = parser.parse_args()

    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    models = payload["models"] if isinstance(payload, dict) else payload
    if args.name_pattern:
        models = [
            model for model in models
            if args.name_pattern in model.get("name", Path(model["path"]).stem)
        ]
    paths = [str(Path(model["path"]).resolve()) for model in models]
    metadata = {
        str(Path(model["path"]).resolve()): {
            "scope": model.get("scope", ""),
            "family": model.get("family", ""),
            "category": model.get("category", ""),
            "expected": model.get("expected", ""),
        }
        for model in models
    }

    common = {
        "kind": "mc",
        "binary": str(args.binary.resolve()),
        "ctg_depth": 1,
        "deterministic_lanes": True,
        "forward_xag": 1,
        "minisat_elim_order": "legacy",
        "progress_seconds": 30,
    }
    cmsat = {
        "MC_PDR_SOLVER": "cmsat",
        "MC_PDR_CMSAT_GAUSS": "1",
        "MC_PDR_CMSAT_SIMPLIFY": "0",
    }

    def island_env(min_xors: int) -> dict[str, str]:
        return {
            **cmsat,
            "MC_PDR_AFFINE_ISLAND_SUMMARY": "1",
            "MC_PDR_AFFINE_ISLAND_MIN_XORS": str(min_xors),
            "MC_PDR_AFFINE_ISLAND_MAX_SUPPORT": "512",
        }

    def replace_env(min_xors: int) -> dict[str, str]:
        return {
            **island_env(min_xors),
            "MC_PDR_AFFINE_ISLAND_REPLACE": "1",
        }

    configs = [
        {
            **common,
            "id": "cadical",
            "label": "CaDiCaL XAG",
            "extra_env": {"MC_PDR_SOLVER": "cadical"},
        },
        {
            **common,
            "id": "cmsat_gauss",
            "label": "CMSat Gaussian gate equations",
            "extra_env": cmsat,
        },
        {
            **common,
            "id": "island_min2",
            "label": "CMSat Gaussian XOR islands min2",
            "extra_env": island_env(2),
        },
        {
            **common,
            "id": "island_min4",
            "label": "CMSat Gaussian XOR islands min4",
            "extra_env": island_env(4),
        },
        {
            **common,
            "id": "island_min8",
            "label": "CMSat Gaussian XOR islands min8",
            "extra_env": island_env(8),
        },
        {
            **common,
            "id": "island_min4_dynamic",
            "label": "CMSat XOR islands min4 plus dynamic stop",
            "extra_env": {
                **island_env(4),
                "MC_PDR_CMSAT_GAUSS_AUTO_GATE": "1",
                "MC_PDR_CMSAT_GAUSS_AUTO_PATIENCE": "1",
            },
        },
        {
            **common,
            "id": "replace_min2",
            "label": "CMSat replace XOR islands min2",
            "extra_env": replace_env(2),
        },
        {
            **common,
            "id": "replace_min4",
            "label": "CMSat replace XOR islands min4",
            "extra_env": replace_env(4),
        },
        {
            **common,
            "id": "replace_min8",
            "label": "CMSat replace XOR islands min8",
            "extra_env": replace_env(8),
        },
    ]
    if args.configs:
        selected = set(args.configs.split(","))
        configs = [config for config in configs if config["id"] in selected]
        missing = selected - {config["id"] for config in configs}
        if missing:
            parser.error("unknown configs: " + ",".join(sorted(missing)))
    if args.repeat_seeds:
        repeated = []
        for seed_text in args.repeat_seeds.split(","):
            seed_value = int(seed_text)
            for config in configs:
                clone = dict(config)
                clone["id"] = f"{config['id']}_s{seed_value}"
                clone["label"] = f"{config['label']} seed {seed_value}"
                clone["extra_env"] = {
                    **config.get("extra_env", {}),
                    "MC_PDR_SEED": str(seed_value),
                    "MC_PDR_CMSAT_SEED": str(seed_value),
                }
                repeated.append(clone)
        configs = repeated

    def progress(event: dict[str, object]) -> None:
        if event.get("type") == "started":
            print(
                f"models={event['total']} configs={len(configs)} "
                f"workers={args.workers}",
                flush=True,
            )
        elif event.get("type") == "row":
            completed = int(event["completed"])
            if completed % 5 == 0 or completed == int(event["total"]):
                print(f"completed={completed}/{event['total']}", flush=True)

    runner = ExperimentRunner({
        "year": "generated",
        "group": "aes-affine-islands",
        "data_dir": "/home/wudl/test_tools",
        "model_paths": paths,
        "model_metadata": metadata,
        "metadata_fields": ["scope", "family", "category", "expected"],
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
    print(json.dumps(result, sort_keys=True), flush=True)
    return 130 if result["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
