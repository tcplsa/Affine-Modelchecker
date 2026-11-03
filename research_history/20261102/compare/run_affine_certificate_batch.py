#!/usr/bin/env python3
"""Batch the independent affine-PDR certificate checker over a TSV manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_affine_pdr_certificate import check_certificate  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_model(name: str, directories: list[Path]) -> Path:
    filename = f"{name}.aag"
    matches = []
    for directory in directories:
        direct = directory / filename
        if direct.is_file():
            matches.append(direct)
        else:
            matches.extend(directory.rglob(filename))
    unique = sorted({path.resolve() for path in matches})
    if len(unique) != 1:
        raise RuntimeError(f"expected one AAG for {name}, found {len(unique)}")
    return unique[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-tsv", type=Path, required=True)
    parser.add_argument("--benchmark-dir", type=Path, action="append", required=True)
    parser.add_argument("--cmsat-wrapper", type=Path, required=True)
    parser.add_argument("--cmsat-library", type=Path)
    parser.add_argument("--wrapper-source", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260825)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with args.manifest_tsv.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    names = list(dict.fromkeys(row["name"] for row in rows))
    summaries = []
    failures = 0
    for index, name in enumerate(names):
        model = find_model(name, args.benchmark_dir)
        try:
            result = check_certificate(
                model=model,
                invariant=None,
                library=args.cmsat_wrapper.resolve(),
                property_index=0,
                seed=args.seed + index * 3,
            )
            result["model_sha256"] = sha256(model)
            status = "PASS"
            error = ""
        except Exception as exception:  # Preserve every failed obligation.
            result = None
            status = "FAIL"
            error = f"{type(exception).__name__}: {exception}"
            failures += 1
        if result is not None:
            (args.output_dir / f"{name}.json").write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        summary = {
            "name": name,
            "status": status,
            "error": error,
            "model_sha256": sha256(model),
            "latches": result["latches"] if result else "",
            "ands": result["ands"] if result else "",
            "recognized_xors": result["recognized_xors"] if result else "",
            "affine_next_equations": result["affine_next_equations"] if result else "",
            "blocked_cubes": result["blocked_cubes"] if result else "",
            "obligations": len(result["obligations"]) if result else "",
            "total_seconds": result["total_seconds"] if result else "",
        }
        summaries.append(summary)
        print(f"{status}\t{name}\tseconds={summary['total_seconds']}")

    fields = list(summaries[0]) if summaries else []
    with (args.output_dir / "summary.tsv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, delimiter="\t", fieldnames=fields)
        writer.writeheader()
        writer.writerows(summaries)
    metadata = {
        "schema": "affine-pdr-independent-certificate-batch-v1",
        "models": len(summaries),
        "passed": len(summaries) - failures,
        "failed": failures,
        "manifest": str(args.manifest_tsv.resolve()),
        "manifest_sha256": sha256(args.manifest_tsv),
        "checker_sha256": sha256(Path(__file__).with_name("check_affine_pdr_certificate.py")),
        "wrapper_sha256": sha256(args.cmsat_wrapper),
        "cmsat_library_sha256": sha256(args.cmsat_library) if args.cmsat_library else None,
        "wrapper_source_sha256": sha256(args.wrapper_source) if args.wrapper_source else None,
        "seed": args.seed,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report = [
        "# Independent SAFE Certificate Validation",
        "",
        f"- Models: {metadata['models']}",
        f"- Passed: {metadata['passed']}",
        f"- Failed: {metadata['failed']}",
        "- Obligations: `Init => I` and `I & T => I'`, where `I` contains the safety property.",
        "- XOR trust check: exhaustive four-assignment validation of every recognized local pattern.",
        "- SAT backend: CryptoMiniSat native XOR with Gaussian elimination.",
        "",
        "The checker parses the original AAG independently and does not call MC's PDR implementation.",
    ]
    (args.output_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
