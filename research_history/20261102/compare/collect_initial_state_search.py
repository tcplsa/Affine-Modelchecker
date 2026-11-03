#!/usr/bin/env python3
"""Collect a reproducible search over mixed circuit initial states."""

from __future__ import annotations

import argparse
import csv
import json
import random
import signal
from pathlib import Path

from compare_runner import ExperimentRunner, discover_models, model_name


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
DEFAULT_FRACTIONS = (0.25, 0.5, 0.75)
BROAD_FRACTIONS = (0.1, 0.25, 0.5, 0.75, 0.9)
INPUT_ORDERS = ("original", "fanout-desc", "fanout-asc", "swap")
PERTURB_PROFILES = ("", "latch", "gate-run", "latch,gate-run")
XAG_POLICIES = ("all", "next", "bad", "shared", "deep")
LANE_FIELDS = (
    "forward_aig",
    "forward_compact_aig",
    "forward_lowered_xag",
    "forward_xag",
    "forward_auto",
    "reverse_aig",
    "reverse_compact_aig",
    "reverse_lowered_xag",
    "reverse_xag",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search mixed AIG/XAG representation, ordering and numbering states."
    )
    parser.add_argument(
        "--year", choices=["2015", "2017", "2019", "2020", "2024", "2025"],
        default="2015",
    )
    parser.add_argument(
        "--group",
        default="regular",
        help="group key from --groups-file (for example fast_unique, medium_unique, or all)",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--workers", type=int, default=6,
        help="benchmark workers; total solver processes are about workers*candidates",
    )
    parser.add_argument("--candidates", type=int, default=20)
    parser.add_argument(
        "--design-profile",
        choices=["standard", "broad"],
        default="standard",
        help="broad adds interpretable representation and one-factor anchors",
    )
    parser.add_argument(
        "--candidate-ids",
        default="",
        help="comma-separated generated state IDs to run, for held-out validation",
    )
    parser.add_argument("--solver-seed", type=int, default=1)
    parser.add_argument("--design-seed", type=int, default=1)
    parser.add_argument(
        "--lanes-per-state",
        type=int,
        default=1,
        help="number of same-representation PDR lanes inside each candidate",
    )
    parser.add_argument("--ctg-depth", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--groups-file", type=Path)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--baseline-results", type=Path)
    parser.add_argument("--baseline-prefix", default="mc_a")
    parser.add_argument("--min-baseline-seconds", type=float, default=0.0)
    parser.add_argument("--max-baseline-seconds", type=float, default=float("inf"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-existing", action="store_true")
    return parser.parse_args()


def baseline_times(path: Path, prefix: str) -> dict[str, float]:
    status_column = f"{prefix}_status" if prefix else "status"
    time_column = f"{prefix}_wall_seconds" if prefix else "wall_seconds"
    result = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row.get(status_column) not in {"SAFE", "UNSAFE"}:
                continue
            try:
                result[row["name"]] = float(row[time_column])
            except (KeyError, ValueError):
                continue
    return result


def base_config(config_id: str, label: str, binary: Path, ctg_depth: int) -> dict:
    return {
        "id": config_id,
        "kind": "mc",
        "label": label,
        "binary": str(binary),
        "ctg_depth": ctg_depth,
        "deterministic_lanes": True,
        "input_order": "original",
        "input_order_seed": 1,
        "xag_policy": "all",
        "xag_fraction": 1.0,
        "xag_seed": 1,
        "perturb_modes": "",
        "perturb_seed": 1,
    }


def build_candidates(
    count: int,
    binary: Path,
    ctg_depth: int,
    design_seed: int,
) -> list[dict]:
    if count < 4:
        raise ValueError("candidates must be at least 4")
    rng = random.Random(design_seed)

    baseline = base_config("state_000", "AIG original", binary, ctg_depth)
    baseline["forward_aig"] = 1

    full_xag = base_config("state_001", "XAG all original", binary, ctg_depth)
    full_xag["forward_xag"] = 1

    hybrid = base_config("state_002", "Hybrid XAG 50%", binary, ctg_depth)
    hybrid.update({
        "forward_xag": 1,
        "xag_policy": "sample",
        "xag_fraction": 0.5,
        "xag_seed": design_seed,
    })

    compact = base_config("state_003", "Compact AIG state", binary, ctg_depth)
    compact.update({
        "forward_xag": 1,
        "xag_policy": "sample",
        "xag_fraction": 0.0,
        "xag_seed": design_seed,
    })

    configs = [baseline, full_xag, hybrid, compact]
    for index in range(4, count):
        input_order = INPUT_ORDERS[(index - 4) % len(INPUT_ORDERS)]
        perturb_modes = PERTURB_PROFILES[
            ((index - 4) // len(INPUT_ORDERS)) % len(PERTURB_PROFILES)
        ]
        input_seed = rng.getrandbits(32)
        perturb_seed = rng.getrandbits(32)
        xag_seed = rng.getrandbits(32)

        config = base_config(
            f"state_{index:03d}", f"Initial state {index:03d}",
            binary, ctg_depth,
        )
        config.update({
            "input_order": input_order,
            "input_order_seed": input_seed,
            "perturb_modes": perturb_modes,
            "perturb_seed": perturb_seed,
        })
        if index % 5 == 4:
            config["forward_aig"] = 1
            if input_order == "original" and not perturb_modes:
                config["perturb_modes"] = "input"
                perturb_modes = "input"
            config["label"] = (
                f"AIG {input_order} {perturb_modes or 'no-renumber'}"
            )
        else:
            fraction = DEFAULT_FRACTIONS[(index - 4) % len(DEFAULT_FRACTIONS)]
            config.update({
                "forward_xag": 1,
                "xag_policy": "sample",
                "xag_fraction": fraction,
                "xag_seed": xag_seed,
                "label": (
                    f"Hybrid {fraction:g} {input_order} "
                    f"{perturb_modes or 'no-renumber'}"
                ),
            })
        configs.append(config)
    return configs


def build_broad_candidates(
    count: int,
    binary: Path,
    ctg_depth: int,
    design_seed: int,
) -> list[dict]:
    if count < 16:
        raise ValueError("broad candidates must be at least 16")
    rng = random.Random(design_seed)
    configs: list[dict] = []

    def add(label: str, lane: str, **updates: object) -> None:
        if len(configs) >= count:
            return
        config = base_config(
            f"state_{len(configs):03d}", label, binary, ctg_depth,
        )
        config[lane] = 1
        config.update(updates)
        config["design_family"] = str(
            updates.get(
                "design_family",
                lane[len("forward_"):] if lane.startswith("forward_") else lane,
            )
        )
        configs.append(config)

    # Representation anchors isolate the encoding effect without ordering noise.
    add("AIG original", "forward_aig", design_family="aig")
    add("Native XAG all", "forward_xag", design_family="native-xag")
    add(
        "Compact AIG via XAG recovery", "forward_xag",
        xag_policy="sample", xag_fraction=0.0, xag_seed=design_seed,
        design_family="compact-aig",
    )
    add(
        "Lowered XAG", "forward_lowered_xag",
        design_family="lowered-xag",
    )
    add("Static auto representation", "forward_auto", design_family="auto")

    for policy in XAG_POLICIES[1:]:
        add(
            f"Selective XAG {policy}", "forward_xag",
            xag_policy=policy, xag_fraction=1.0, xag_seed=design_seed,
            design_family=f"selective-{policy}",
        )
    for fraction in BROAD_FRACTIONS:
        add(
            f"Sampled XAG {fraction:g}", "forward_xag",
            xag_policy="sample", xag_fraction=fraction,
            xag_seed=design_seed,
            design_family="partial-xag",
        )

    # One-factor anchors make input ordering and numbering effects identifiable.
    for order in INPUT_ORDERS[1:]:
        add(
            f"AIG input {order}", "forward_aig",
            input_order=order, input_order_seed=design_seed,
            design_family="aig-input-order",
        )
    for order in INPUT_ORDERS[1:]:
        add(
            f"XAG input {order}", "forward_xag",
            input_order=order, input_order_seed=design_seed,
            design_family="xag-input-order",
        )
    for perturb in PERTURB_PROFILES[1:]:
        add(
            f"AIG renumber {perturb}", "forward_aig",
            perturb_modes=perturb, perturb_seed=design_seed,
            design_family="aig-renumber",
        )
    for perturb in PERTURB_PROFILES[1:]:
        add(
            f"XAG renumber {perturb}", "forward_xag",
            perturb_modes=perturb, perturb_seed=design_seed,
            design_family="xag-renumber",
        )

    # Fill the remaining budget with a balanced, reproducible factorial sample.
    factorial: list[tuple[str, float, str, str]] = []
    for policy in ("sample", "next", "bad", "shared", "deep"):
        fractions = BROAD_FRACTIONS if policy == "sample" else (1.0,)
        for fraction in fractions:
            for order in INPUT_ORDERS:
                for perturb in PERTURB_PROFILES:
                    factorial.append((policy, fraction, order, perturb))
    rng.shuffle(factorial)
    for policy, fraction, order, perturb in factorial:
        if len(configs) >= count:
            break
        xag_seed = rng.getrandbits(32)
        input_seed = rng.getrandbits(32)
        perturb_seed = rng.getrandbits(32)
        add(
            (
                f"XAG {policy}:{fraction:g} {order} "
                f"{perturb or 'no-renumber'}"
            ),
            "forward_xag",
            xag_policy=policy,
            xag_fraction=fraction,
            xag_seed=xag_seed,
            input_order=order,
            input_order_seed=input_seed,
            perturb_modes=perturb,
            perturb_seed=perturb_seed,
            design_family="factorial-xag",
        )
    return configs


def main() -> int:
    args = parse_args()
    if args.lanes_per_state < 1:
        raise SystemExit("--lanes-per-state must be positive")
    binary = args.binary or (
        ROOT / "Modelchecker-bidirectional" / "modelchecker" / "modelchecker"
    )
    discovery = {"year": args.year, "group": args.group, "sort": "size"}
    if args.data_dir:
        discovery["data_dir"] = str(args.data_dir)
    if args.groups_file:
        discovery["groups_file"] = str(args.groups_file)
    paths = discover_models(discovery)

    if args.baseline_results:
        times = baseline_times(args.baseline_results, args.baseline_prefix)
        paths = [
            path for path in paths
            if model_name(path, discovery) in times
            and args.min_baseline_seconds
                <= times[model_name(path, discovery)]
                <= args.max_baseline_seconds
        ]
        paths.sort(key=lambda path: (times[model_name(path, discovery)], path.name))
    if args.limit:
        paths = paths[: args.limit]

    builder = (
        build_broad_candidates
        if args.design_profile == "broad"
        else build_candidates
    )
    configs = builder(args.candidates, binary, args.ctg_depth, args.design_seed)
    if args.candidate_ids:
        requested = {
            item.strip() for item in args.candidate_ids.split(",") if item.strip()
        }
        available = {config["id"] for config in configs}
        missing = requested - available
        if missing:
            raise SystemExit(
                "unknown candidate IDs: " + ", ".join(sorted(missing))
            )
        configs = [config for config in configs if config["id"] in requested]
        if not configs:
            raise SystemExit("--candidate-ids selected no states")
    for config in configs:
        active_lane_fields = [
            field for field in LANE_FIELDS if int(config.get(field, 0)) > 0
        ]
        if len(active_lane_fields) != 1:
            raise SystemExit(
                f"{config['id']} must define exactly one active PDR lane group"
            )
        config[active_lane_fields[0]] = args.lanes_per_state
    tier = (
        f"{args.min_baseline_seconds:g}_{args.max_baseline_seconds:g}"
        if args.baseline_results else "size_order"
    ).replace("inf", "up")
    output = args.output or (
        SCRIPT_DIR / "results"
        / f"mc_initial_state_hwmcc{args.year}_{args.group}_{tier}.tsv"
    )
    settings = {
        "name": f"initial_state_{args.year}_{args.group}_{tier}",
        "year": args.year,
        "group": args.group,
        "timeout": args.timeout,
        "workers": args.workers,
        "mc_seed": args.solver_seed,
        "output": str(output),
        "skip_existing": args.skip_existing,
        "model_paths": [str(path) for path in paths],
        "configs": configs,
    }
    if args.data_dir:
        settings["data_dir"] = str(args.data_dir)

    design_path = output.with_name(output.stem + "_design.json")
    design_path.parent.mkdir(parents=True, exist_ok=True)
    design_path.write_text(
        json.dumps(
            {
                "year": args.year,
                "group": args.group,
                "solver_seed": args.solver_seed,
                "design_seed": args.design_seed,
                "design_profile": args.design_profile,
                "lanes_per_state": args.lanes_per_state,
                "timeout": args.timeout,
                "configs": configs,
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    def progress(event: dict) -> None:
        if event["type"] == "started":
            print(
                f"running {event['total']} models x {len(configs)} initial states; "
                f"max processes~"
                f"{args.workers * len(configs) * args.lanes_per_state}, "
                f"output={output}",
                flush=True,
            )
        elif event["type"] == "row":
            completed = event["completed"]
            if completed <= 10 or completed % 10 == 0 or completed == event["total"]:
                row = event["row"]
                print(
                    f"[{completed}/{event['total']}] {row['name']} "
                    f"winner={row['winner']}",
                    flush=True,
                )

    runner = ExperimentRunner(settings, progress=progress)

    def stop(_signum: int, _frame: object) -> None:
        runner.cancel()
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        result = runner.run()
    except KeyboardInterrupt:
        runner.cancel()
        print(f"cancelled output={output}", flush=True)
        return 130
    print(
        f"completed={result['completed']} total={result['total']} "
        f"cancelled={int(result['cancelled'])} output={output} design={design_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
