#!/usr/bin/env python3
"""Continue PDR from exact-transition sibling invariants on hard targets."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import os
import re
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transfer-report", type=Path, required=True)
    parser.add_argument("--baseline-progress", type=Path, required=True)
    parser.add_argument("--exclude", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--workers", type=int, default=29)
    parser.add_argument("--lanes", type=int, default=4)
    parser.add_argument(
        "--modelchecker",
        type=Path,
        default=Path(
            "/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker"
        ),
    )
    return parser.parse_args()


def model_list(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, dict):
        payload = payload["models"]
    if not isinstance(payload, list):
        raise ValueError("expected a model list")
    return payload


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def main() -> int:
    args = parse_args()
    report = json.loads(args.transfer_report.read_text(encoding="utf-8"))
    excluded = {
        str(model["id"])
        for model in model_list(json.loads(args.exclude.read_text(encoding="utf-8")))
    }
    baseline: dict[str, dict[str, str]] = {}
    with args.baseline_progress.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            baseline[row["model_id"]] = row

    group_invariants = {
        int(group["index"]): group["invariant"]
        for group in report["groups"]
        if group.get("invariant")
    }
    jobs = [
        target
        for target in report["targets"]
        if int(target["installed"]) > 0
        and str(target["id"]) not in excluded
        and int(target["group"]) in group_invariants
    ]
    args.output.mkdir(parents=True, exist_ok=True)
    snapshot_root = args.output / "snapshots"
    snapshot_root.mkdir(exist_ok=True)

    def run_target(target: dict[str, object]) -> dict[str, object]:
        model_id = str(target["id"])
        group = int(target["group"])
        log = args.output / f"{slug(model_id)}.log"
        env = os.environ.copy()
        env.update(
            {
                "MC_PDR_SEED": "770001",
                "MC_PDR_STATS": "1",
                "MC_PDR_PROGRESS_SECONDS": "30",
                "MC_PDR_INVARIANT_IMPORT": str(group_invariants[group]),
                "MC_PDR_INVARIANT_SAME_TRANSITION": "1",
                "MC_PDR_INVARIANT_SNAPSHOT": str(
                    snapshot_root / f"{slug(model_id)}-thread-%t.inv"
                ),
            }
        )
        with log.open("w", encoding="utf-8") as stream:
            completed = subprocess.run(
                [
                    "timeout",
                    f"{args.timeout}s",
                    str(args.modelchecker),
                    "--forward-aig",
                    str(args.lanes),
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
        best_depth = max((int(item[2]) for item in stats), default=-1)
        max_runtime = max((float(item[3]) for item in stats), default=0.0)
        base = baseline.get(model_id, {})
        base_depth = int(base.get("aig_legacy4_progress_pdr_depth") or -1)
        return {
            "id": model_id,
            "family": target["family"],
            "group": group,
            "result": results[-1] if results else "timeout",
            "returncode": completed.returncode,
            "runtime": max_runtime,
            "best_depth": best_depth,
            "baseline_depth_600": base_depth,
            "depth_delta": best_depth - base_depth if base_depth >= 0 else None,
            "installed": target["installed"],
            "log": str(log),
        }

    results: list[dict[str, object]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(run_target, target) for target in jobs]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            print(
                f"target={result['id']} result={result['result']} "
                f"depth={result['best_depth']} baseline={result['baseline_depth_600']} "
                f"delta={result['depth_delta']}",
                flush=True,
            )

    results.sort(key=lambda result: str(result["id"]))
    summary = {
        "attempts": len(results),
        "solves": sum(result["result"] in {"safe", "unsafe"} for result in results),
        "excluded_historical_mc_aig_solves": len(excluded),
        "deeper": sum(
            result["depth_delta"] is not None and result["depth_delta"] >= 3
            for result in results
        ),
    }
    (args.output / "report.json").write_text(
        json.dumps(
            {
                "schema": "transition-invariant-continuation-v1",
                "summary": summary,
                "results": results,
            },
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
