#!/usr/bin/env python3
"""Harvest sibling proofs and validate them on hard transition-related targets."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
from pathlib import Path


IMPORT_RE = re.compile(
    r"PDR_INVARIANT_IMPORT status=(\w+) clauses=(\d+) pruned=(\d+) "
    r"proves_target=([01])"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--modelchecker",
        type=Path,
        default=Path(
            "/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker"
        ),
    )
    parser.add_argument(
        "--merge",
        type=Path,
        default=Path("/home/wudl/test_tools/compare/merge_pdr_invariants.py"),
    )
    parser.add_argument("--max-sources", type=int, default=2)
    parser.add_argument("--source-workers", type=int, default=8)
    parser.add_argument("--validation-workers", type=int, default=16)
    parser.add_argument("--source-timeout", type=int, default=180)
    parser.add_argument("--validation-timeout", type=int, default=120)
    parser.add_argument("--source-lanes", type=int, default=4)
    parser.add_argument(
        "--exact-transition",
        action="store_true",
        help="Reuse source inductiveness only for an exact-transition plan.",
    )
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def run_logged(command: list[str], log: Path, timeout: int, env: dict[str, str]) -> int:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as stream:
        completed = subprocess.run(
            ["timeout", f"{timeout}s", *command],
            stdout=stream,
            stderr=subprocess.STDOUT,
            env=env,
            check=False,
        )
    return completed.returncode


def invariant_cube_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith(("c", "#", "mc-pdr-invariant-v1"))
    )


def main() -> int:
    args = parse_args()
    payload = json.loads(args.plan.read_text(encoding="utf-8"))
    groups = payload["groups"]
    if args.exact_transition and any(
        group.get("source_match") != "exact" for group in groups
    ):
        raise ValueError("--exact-transition requires exact source matches")
    args.output.mkdir(parents=True, exist_ok=True)
    source_root = args.output / "sources"
    group_root = args.output / "groups"
    target_root = args.output / "targets"

    selected_sources: dict[str, dict[str, object]] = {}
    for group in groups:
        for source in group["sources"][: args.max_sources]:
            selected_sources[str(source["id"])] = source

    def export_source(item: tuple[str, dict[str, object]]) -> dict[str, object]:
        source_id, source = item
        directory = source_root / slug(source_id)
        directory.mkdir(parents=True, exist_ok=True)
        export_pattern = directory / "thread-%t.inv"
        merged = directory / "merged.inv"
        if args.resume and (directory / "run.log").exists() and merged.exists():
            cube_count = invariant_cube_count(merged)
            return {
                "id": source_id,
                "returncode": 0,
                "invariant": str(merged) if cube_count else None,
                "export_count": len(list(directory.glob("thread-*.inv"))),
                "cube_count": cube_count,
            }
        env = os.environ.copy()
        env.update(
            {
                "MC_PDR_SEED": "760001",
                "MC_PDR_STATS": "1",
                "MC_PDR_INVARIANT_EXPORT": str(export_pattern),
            }
        )
        returncode = run_logged(
            [
                str(args.modelchecker),
                "--forward-aig",
                str(args.source_lanes),
                str(source["path"]),
            ],
            directory / "run.log",
            args.source_timeout,
            env,
        )
        invariants = sorted(directory.glob("thread-*.inv"))
        if invariants:
            subprocess.run(
                [str(args.merge), "--output", str(merged), *map(str, invariants)],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        cube_count = invariant_cube_count(merged)
        return {
            "id": source_id,
            "returncode": returncode,
            "invariant": str(merged) if cube_count else None,
            "export_count": len(invariants),
            "cube_count": cube_count,
        }

    source_results: dict[str, dict[str, object]] = {}
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.source_workers
    ) as executor:
        futures = {
            executor.submit(export_source, item): item[0]
            for item in selected_sources.items()
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            source_results[str(result["id"])] = result
            print(
                f"source={result['id']} exports={result['export_count']} "
                f"cubes={result['cube_count']} "
                f"returncode={result['returncode']}",
                flush=True,
            )

    prepared_groups: list[dict[str, object]] = []
    for index, group in enumerate(groups):
        directory = group_root / f"g{index:02d}-{slug(str(group['family']))}"
        directory.mkdir(parents=True, exist_ok=True)
        invariants = []
        for source in group["sources"][: args.max_sources]:
            result = source_results.get(str(source["id"]), {})
            invariant = result.get("invariant")
            if invariant:
                invariants.append(str(invariant))
        merged = directory / "teachers.inv"
        if merged.exists():
            merged.unlink()
        if invariants:
            subprocess.run(
                [str(args.merge), "--output", str(merged), *invariants],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        prepared_groups.append(
            {
                "index": index,
                "family": group["family"],
                "targets": group["targets"],
                "invariant": str(merged) if invariants and merged.exists() else None,
                "teacher_count": len(invariants),
            }
        )

    jobs = [
        (group, target)
        for group in prepared_groups
        if group["invariant"]
        for target in group["targets"]
    ]

    def validate_target(job: tuple[dict[str, object], dict[str, object]]) -> dict[str, object]:
        group, target = job
        target_id = str(target["id"])
        log = target_root / f"g{group['index']:02d}-{slug(target_id)}.log"
        env = os.environ.copy()
        env.update(
            {
                "MC_PDR_SEED": "760101",
                "MC_PDR_STATS": "1",
                "MC_PDR_INVARIANT_IMPORT": str(group["invariant"]),
                "MC_PDR_INVARIANT_PRUNE": "1",
            }
        )
        if args.exact_transition:
            env["MC_PDR_INVARIANT_SAME_TRANSITION"] = "1"
        returncode = run_logged(
            [str(args.modelchecker), "-aig", str(target["path"])],
            log,
            args.validation_timeout,
            env,
        )
        text = log.read_text(encoding="utf-8", errors="replace")
        matches = IMPORT_RE.findall(text)
        status, installed, pruned, proof = (
            matches[-1] if matches else ("missing", "0", "0", "0")
        )
        result_match = re.findall(r"^result: (\w+)", text, flags=re.MULTILINE)
        return {
            "group": group["index"],
            "family": group["family"],
            "id": target_id,
            "path": target["path"],
            "status": status,
            "installed": int(installed),
            "pruned": int(pruned),
            "proves_target": proof == "1",
            "result": result_match[-1] if result_match else "timeout",
            "returncode": returncode,
            "log": str(log),
        }

    target_results: list[dict[str, object]] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.validation_workers
    ) as executor:
        futures = [executor.submit(validate_target, job) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            target_results.append(result)
            print(
                f"target={result['id']} installed={result['installed']} "
                f"pruned={result['pruned']} proof={int(result['proves_target'])}",
                flush=True,
            )

    target_results.sort(key=lambda item: (int(item["group"]), str(item["id"])))
    report = {
        "schema": "transition-invariant-transfer-results-v1",
        "plan": str(args.plan),
        "sources": sorted(source_results.values(), key=lambda item: str(item["id"])),
        "groups": prepared_groups,
        "targets": target_results,
        "summary": {
            "source_attempts": len(source_results),
            "source_exports": sum(
                1 for result in source_results.values() if result["invariant"]
            ),
            "target_attempts": len(target_results),
            "target_proofs": sum(
                1 for result in target_results if result["proves_target"]
            ),
        },
    }
    (args.output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"], sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
