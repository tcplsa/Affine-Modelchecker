#!/usr/bin/env python3
"""Screen specialist PDR policies after exact-transition proof transfer."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
from pathlib import Path


STRATEGIES: dict[str, dict[str, str]] = {
    "transfer-default": {},
    "heuristic": {"MC_PDR_HEURISTIC": "1"},
    "persistent-init": {
        "MC_PDR_PRE_PHASE_LANES": "default,target,opposite,init",
        "MC_PDR_PRE_PHASE_SEEDS": "810101,810102,810103,810104",
    },
    "mic-mixed": {
        "MC_PDR_MIC_ORDER_LANES": "legacy,distance-near,distance-far,feedback"
    },
    "aig-xag": {},
    "control-default": {},
    "control-heuristic": {"MC_PDR_HEURISTIC": "1"},
    "control-persistent-init": {
        "MC_PDR_PRE_PHASE_LANES": "default,target,opposite,init",
        "MC_PDR_PRE_PHASE_SEEDS": "810101,810102,810103,810104",
    },
    "control-aig-xag": {},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transfer-report", type=Path, required=True)
    parser.add_argument("--continuation-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--seed", type=int, default=810001)
    parser.add_argument("--model-id", action="append", default=[])
    parser.add_argument("--strategy", action="append", choices=tuple(STRATEGIES))
    parser.add_argument("--override-invariant", type=Path)
    parser.add_argument(
        "--modelchecker",
        type=Path,
        default=Path("/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker"),
    )
    return parser.parse_args()


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def main() -> int:
    args = parse_args()
    transfer = json.loads(args.transfer_report.read_text(encoding="utf-8"))
    continuation = json.loads(args.continuation_report.read_text(encoding="utf-8"))
    continuation_by_id = {row["id"]: row for row in continuation["results"]}
    group_invariants = {
        int(group["index"]): str(group["invariant"])
        for group in transfer["groups"]
        if group.get("invariant")
    }

    # The first specialist screen is deliberately narrow: exact-transition
    # ZipCPU targets which still timed out after the plain transferred proof.
    targets = [
        target
        for target in transfer["targets"]
        if target["family"] == "zipcpu"
        and target["id"] in continuation_by_id
        and continuation_by_id[target["id"]]["result"] == "timeout"
        and int(target["group"]) in group_invariants
    ]
    if args.model_id:
        selected_models = set(args.model_id)
        targets = [target for target in targets if target["id"] in selected_models]
    selected_strategies = args.strategy or list(STRATEGIES)
    jobs = [
        (strategy, target)
        for strategy in selected_strategies
        for target in targets
    ]
    args.output.mkdir(parents=True, exist_ok=True)

    def run(job: tuple[str, dict[str, object]]) -> dict[str, object]:
        strategy, target = job
        model_id = str(target["id"])
        group = int(target["group"])
        log = args.output / f"{slug(model_id)}--{strategy}.log"
        env = os.environ.copy()
        env.update({
            "MC_PDR_SEED": str(args.seed),
            "MC_PDR_STATS": "1",
            "MC_PDR_PROGRESS_SECONDS": "30",
            **STRATEGIES[strategy],
        })
        if not strategy.startswith("control-"):
            env["MC_PDR_INVARIANT_IMPORT"] = str(
                args.override_invariant or group_invariants[group]
            )
            env["MC_PDR_INVARIANT_SAME_TRANSITION"] = "1"
        else:
            env.pop("MC_PDR_INVARIANT_IMPORT", None)
            env.pop("MC_PDR_INVARIANT_SAME_TRANSITION", None)
        lanes = ["--forward-aig", "4"]
        if strategy.endswith("aig-xag"):
            lanes = ["--forward-aig", "2", "--forward-xag", "2"]
        with log.open("w", encoding="utf-8") as stream:
            completed = subprocess.run(
                [
                    "timeout",
                    f"{args.timeout}s",
                    str(args.modelchecker),
                    *lanes,
                    str(target["path"]),
                ],
                stdout=stream,
                stderr=subprocess.STDOUT,
                env=env,
                check=False,
            )
        text = log.read_text(encoding="utf-8", errors="replace")
        results = re.findall(r"^result: (\w+)", text, flags=re.MULTILINE)
        stats = re.findall(
            r"PDR_STATS thread=(\d+).*?result=(\w+).*?depth=(-?\d+) "
            r"runtime=([0-9.]+)",
            text,
        )
        return {
            "id": model_id,
            "group": group,
            "strategy": strategy,
            "result": results[-1] if results else "timeout",
            "returncode": completed.returncode,
            "runtime": max((float(row[3]) for row in stats), default=0.0),
            "best_depth": max((int(row[2]) for row in stats), default=-1),
            "plain_transfer_depth": continuation_by_id[model_id]["best_depth"],
            "log": str(log),
        }

    rows: list[dict[str, object]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        for row in executor.map(run, jobs):
            rows.append(row)
            print(
                f"strategy={row['strategy']} target={row['id']} "
                f"result={row['result']} depth={row['best_depth']}",
                flush=True,
            )
    rows.sort(key=lambda row: (str(row["strategy"]), str(row["id"])))
    summary = {
        "jobs": len(rows),
        "targets": len(targets),
        "solves": sum(row["result"] in {"safe", "unsafe"} for row in rows),
        "solves_by_strategy": {
            strategy: sum(
                row["strategy"] == strategy
                and row["result"] in {"safe", "unsafe"}
                for row in rows
            )
            for strategy in selected_strategies
        },
    }
    (args.output / "report.json").write_text(
        json.dumps(
            {"schema": "transition-invariant-specialists-v1", "summary": summary, "results": rows},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
