#!/usr/bin/env python3
"""Screen cross-property proof curricula across symbol-compatible AIG builds."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
from pathlib import Path


IMPORT_RE = re.compile(
    r"PDR_INVARIANT_IMPORT status=(\w+) clauses=(\d+) pruned=(\d+) "
    r"proves_target=([01])"
)
STATS_RE = re.compile(
    r"PDR_STATS thread=(\d+).*?result=(\w+).*?depth=(-?\d+) "
    r"runtime=([0-9.]+)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--atlas", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--group", type=int, action="append", required=True)
    parser.add_argument("--max-sources", type=int, default=2)
    parser.add_argument("--source-timeout", type=int, default=120)
    parser.add_argument("--target-timeout", type=int, default=300)
    parser.add_argument("--source-workers", type=int, default=4)
    parser.add_argument("--target-workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=890001)
    parser.add_argument("--resume", action="store_true")
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
    parser.add_argument(
        "--remap",
        type=Path,
        default=Path(
            "/home/wudl/test_tools/compare/remap_pdr_invariant_symbols.py"
        ),
    )
    return parser.parse_args()


def slug(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value))


def run_logged(
    command: list[str], log: Path, timeout: int, env: dict[str, str]
) -> int:
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


def clause_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(
        bool(line.strip())
        and not line.startswith(("c", "#", "mc-pdr-invariant-v1"))
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
    )


def parse_result(log: Path) -> tuple[str, float, int]:
    text = log.read_text(encoding="utf-8", errors="replace")
    results = re.findall(r"^result: (\w+)", text, flags=re.MULTILINE)
    stats = STATS_RE.findall(text)
    return (
        results[-1] if results else "timeout",
        max((float(row[3]) for row in stats), default=0.0),
        max((int(row[2]) for row in stats), default=-1),
    )


def main() -> int:
    args = parse_args()
    payload = json.loads(args.atlas.read_text(encoding="utf-8"))
    groups = [(index, payload["groups"][index]) for index in args.group]
    args.output.mkdir(parents=True, exist_ok=True)

    sources: dict[str, dict[str, object]] = {}
    for _, group in groups:
        for source in group["safe_sources"][: args.max_sources]:
            sources[str(source["id"])] = source

    def export_source(source: dict[str, object]) -> dict[str, object]:
        source_id = str(source["id"])
        directory = args.output / "sources" / slug(source_id)
        merged = directory / "merged.inv"
        run_log = directory / "run.log"
        if args.resume and merged.exists() and clause_count(merged):
            return {
                "id": source_id,
                "path": source["path"],
                "result": "safe",
                "clauses": clause_count(merged),
                "invariant": str(merged),
                "returncode": 0,
            }
        directory.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update(
            {
                "MC_PDR_SEED": str(args.seed),
                "MC_PDR_STATS": "1",
                "MC_PDR_INVARIANT_EXPORT": str(directory / "thread-%t.inv"),
            }
        )
        returncode = run_logged(
            [str(args.modelchecker), "--forward-aig", "4", str(source["path"])],
            run_log,
            args.source_timeout,
            env,
        )
        result, runtime, depth = parse_result(run_log)
        invariants = sorted(directory.glob("thread-*.inv"))
        if invariants:
            subprocess.run(
                [sys.executable, str(args.merge), "--output", str(merged), *map(str, invariants)],
                check=True,
            )
        clauses = clause_count(merged)
        return {
            "id": source_id,
            "path": source["path"],
            "result": result,
            "runtime": runtime,
            "depth": depth,
            "clauses": clauses,
            "invariant": str(merged) if clauses else None,
            "returncode": returncode,
        }

    source_results: dict[str, dict[str, object]] = {}
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.source_workers
    ) as executor:
        for row in executor.map(export_source, sources.values()):
            source_results[str(row["id"])] = row
            print(
                f"source={row['id']} result={row['result']} "
                f"clauses={row['clauses']}",
                flush=True,
            )

    jobs = [
        (index, group, target)
        for index, group in groups
        for target in group["hard"]
    ]

    def run_target(
        job: tuple[int, dict[str, object], dict[str, object]]
    ) -> dict[str, object]:
        index, group, target = job
        target_id = str(target["id"])
        directory = args.output / "targets" / slug(target_id)
        report_path = directory / "result.json"
        if args.resume and report_path.exists():
            return json.loads(report_path.read_text(encoding="utf-8"))
        directory.mkdir(parents=True, exist_ok=True)
        remapped: list[Path] = []
        remap_reports: list[dict[str, object]] = []
        for source in group["safe_sources"][: args.max_sources]:
            source_result = source_results.get(str(source["id"]), {})
            invariant = source_result.get("invariant")
            if not invariant:
                continue
            mapped = directory / f"from-{slug(source['id'])}.inv"
            mapping_report = directory / f"from-{slug(source['id'])}.json"
            subprocess.run(
                [
                    sys.executable,
                    str(args.remap),
                    "--source-aig",
                    str(source["path"]),
                    "--target-aig",
                    str(target["path"]),
                    "--invariant",
                    str(invariant),
                    "--output",
                    str(mapped),
                    "--report",
                    str(mapping_report),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            remap_reports.append(json.loads(mapping_report.read_text(encoding="utf-8")))
            if clause_count(mapped):
                remapped.append(mapped)
        teacher = directory / "teachers.inv"
        if remapped:
            subprocess.run(
                [sys.executable, str(args.merge), "--output", str(teacher), *map(str, remapped)],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        log = directory / "run.log"
        result = "no-proof"
        runtime = 0.0
        depth = -1
        returncode = 0
        installed = 0
        pruned = 0
        proves_target = False
        if clause_count(teacher):
            env = os.environ.copy()
            env.update(
                {
                    "MC_PDR_SEED": str(args.seed + 100),
                    "MC_PDR_STATS": "1",
                    "MC_PDR_INVARIANT_IMPORT": str(teacher),
                    "MC_PDR_INVARIANT_PRUNE": "1",
                    "MC_PDR_INVARIANT_EXPORT": str(directory / "final-thread-%t.inv"),
                }
            )
            returncode = run_logged(
                [str(args.modelchecker), "--forward-aig", "4", str(target["path"])],
                log,
                args.target_timeout,
                env,
            )
            result, runtime, depth = parse_result(log)
            text = log.read_text(encoding="utf-8", errors="replace")
            imports = IMPORT_RE.findall(text)
            if imports:
                _, installed_text, pruned_text, proves_text = imports[-1]
                installed = int(installed_text)
                pruned = int(pruned_text)
                proves_target = proves_text == "1"
        row = {
            "group": index,
            "families": group["families"],
            "id": target_id,
            "path": target["path"],
            "result": result,
            "runtime": runtime,
            "depth": depth,
            "returncode": returncode,
            "teacher_clauses": clause_count(teacher),
            "installed": installed,
            "pruned": pruned,
            "proves_target": proves_target,
            "remaps": remap_reports,
            "log": str(log),
        }
        report_path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        return row

    target_results: list[dict[str, object]] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.target_workers
    ) as executor:
        for row in executor.map(run_target, jobs):
            target_results.append(row)
            print(
                f"target={row['id']} mapped={row['teacher_clauses']} "
                f"accepted={row['installed']} pruned={row['pruned']} "
                f"result={row['result']} depth={row['depth']}",
                flush=True,
            )

    target_results.sort(key=lambda row: (int(row["group"]), str(row["id"])))
    report = {
        "schema": "symbol-invariant-curriculum-v1",
        "atlas": str(args.atlas),
        "groups": args.group,
        "summary": {
            "sources": len(source_results),
            "targets": len(target_results),
            "solves": sum(row["result"] in {"safe", "unsafe"} for row in target_results),
            "proves_target_on_import": sum(bool(row["proves_target"]) for row in target_results),
        },
        "source_results": source_results,
        "target_results": target_results,
    }
    (args.output / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"], sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
