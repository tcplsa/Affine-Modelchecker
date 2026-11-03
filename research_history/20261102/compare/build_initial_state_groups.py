#!/usr/bin/env python3
"""Build runtime tiers and exact-deduplicated train/validation/test groups."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from compare_runner import ROOT, model_name


SCRIPT_DIR = Path(__file__).resolve().parent
SOLVED = {"SAFE", "UNSAFE"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tier fixed-AIG baselines and remove exact cross-year duplicates."
    )
    parser.add_argument(
        "--years",
        nargs="+",
        default=["2020", "2024", "2025"],
        choices=["2015", "2017", "2019", "2020", "2024", "2025"],
    )
    parser.add_argument("--train-years", nargs="*", default=[])
    parser.add_argument("--validation-years", nargs="*", default=[])
    parser.add_argument("--test-years", nargs="*", default=[])
    parser.add_argument("--trivial-cutoff", type=float, default=0.1)
    parser.add_argument("--fast-cutoff", type=float, default=2.0)
    parser.add_argument("--medium-cutoff", type=float, default=20.0)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--baseline-pattern",
        default="mc_initial_state_baseline_hwmcc{year}_all.tsv",
        help="filename pattern under results/; {year} is replaced",
    )
    parser.add_argument(
        "--retry-pattern",
        default="mc_initial_state_baseline_hwmcc{year}_error_retry.tsv",
        help="optional retry filename pattern under results/",
    )
    parser.add_argument("--hash-workers", type=int, default=16)
    parser.add_argument("--output-dir", type=Path, default=SCRIPT_DIR)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=SCRIPT_DIR / "results" / "initial_state_dataset_manifest.tsv",
    )
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(4 * 1024 * 1024)
            if not block:
                break
            value.update(block)
    return value.hexdigest()


def runtime_tier(
    row: dict[str, str],
    trivial: float,
    fast: float,
    medium: float,
) -> str:
    status = row.get("aig_base_status", "")
    if status not in SOLVED:
        return "timeout" if status == "TIMEOUT" else "error"
    try:
        seconds = float(row.get("aig_base_wall_seconds", ""))
    except ValueError:
        return "error"
    if seconds < trivial:
        return "trivial"
    if seconds < fast:
        return "fast"
    if seconds < medium:
        return "medium"
    return "slow"


def build_roles(args: argparse.Namespace) -> dict[str, str]:
    explicit = args.train_years or args.validation_years or args.test_years
    if not explicit:
        roles = ["train", "validation", "test"]
        return {
            year: roles[index] if index < len(roles) else f"holdout_{index}"
            for index, year in enumerate(args.years)
        }

    role_by_year: dict[str, str] = {}
    for role, years in (
        ("train", args.train_years),
        ("validation", args.validation_years),
        ("test", args.test_years),
    ):
        for year in years:
            if year not in args.years:
                raise SystemExit(
                    f"{role} year {year} is not present in --years"
                )
            if year in role_by_year:
                raise SystemExit(f"year {year} has more than one role")
            role_by_year[year] = role
    for year in args.years:
        role_by_year.setdefault(year, "holdout")
    return role_by_year


def main() -> int:
    args = parse_args()
    if not (
        0.0 <= args.trivial_cutoff
        <= args.fast_cutoff
        <= args.medium_cutoff
        <= args.timeout
    ):
        raise SystemExit(
            "cutoffs must satisfy 0 <= trivial <= fast <= medium <= timeout"
        )
    role_by_year = build_roles(args)
    records: list[dict[str, object]] = []
    for year in args.years:
        data_dir = ROOT / "test_tools" / f"hwmcc{year}" / "data"
        baseline = SCRIPT_DIR / "results" / args.baseline_pattern.format(year=year)
        if not baseline.exists():
            raise SystemExit(f"missing baseline TSV: {baseline}")
        settings = {"year": year, "group": "all", "data_dir": str(data_dir)}
        paths = list(data_dir.rglob("*.aig")) + list(data_dir.rglob("*.aag"))
        path_by_name = {model_name(path, settings): path for path in paths}
        baseline_rows = {
            row.get("name", ""): row for row in read_tsv(baseline)
        }
        retry = SCRIPT_DIR / "results" / args.retry_pattern.format(year=year)
        if retry.exists():
            for row in read_tsv(retry):
                baseline_rows[row.get("name", "")] = row
        for row in baseline_rows.values():
            name = row.get("name", "")
            path = path_by_name.get(name)
            if path is None:
                raise SystemExit(f"{year}: baseline model not found: {name}")
            records.append({
                "year": year,
                "role": role_by_year[year],
                "name": name,
                "path": path,
                "size_bytes": path.stat().st_size,
                "status": row.get("aig_base_status", ""),
                "wall_seconds": row.get("aig_base_wall_seconds", ""),
                "tier": runtime_tier(
                    row, args.trivial_cutoff, args.fast_cutoff,
                    args.medium_cutoff,
                ),
            })

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.hash_workers
    ) as executor:
        hashes = executor.map(digest, [record["path"] for record in records])
        for record, value in zip(records, hashes):
            record["sha256"] = value

    owner_by_hash: dict[str, tuple[str, str]] = {}
    for record in records:
        value = str(record["sha256"])
        owner_by_hash.setdefault(
            value, (str(record["year"]), str(record["name"]))
        )
        owner_year, owner_name = owner_by_hash[value]
        record["duplicate"] = int(
            owner_year != record["year"] or owner_name != record["name"]
        )
        record["duplicate_of"] = (
            "" if not record["duplicate"] else f"{owner_year}:{owner_name}"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for year in args.years:
        year_records = [record for record in records if record["year"] == year]
        year_baseline = (
            SCRIPT_DIR / "results" / args.baseline_pattern.format(year=year)
        )
        groups: dict[str, list[str]] = {
            "trivial": [], "fast": [], "medium": [], "slow": [],
            "timeout": [], "error": [],
            "unique": [], "duplicate": [], "trivial_unique": [],
            "fast_unique": [], "medium_unique": [], "slow_unique": [],
            "timeout_unique": [],
            "error_unique": [], "trainable_unique": [],
        }
        for record in year_records:
            name = str(record["name"])
            tier = str(record["tier"])
            groups[tier].append(name)
            duplicate = bool(record["duplicate"])
            groups["duplicate" if duplicate else "unique"].append(name)
            if not duplicate:
                groups[f"{tier}_unique"].append(name)
                if tier in {"fast", "medium", "slow"}:
                    groups["trainable_unique"].append(name)
        for names in groups.values():
            names.sort()
        role = role_by_year[year]
        groups[role] = list(groups["trainable_unique"])
        output = (
            args.output_dir
            / f"hwmcc{year}_groups_mc_{int(args.timeout)}.json"
        )
        payload = {
            "source": str(year_baseline),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "timeout_seconds": args.timeout,
            "cutoffs": {
                "trivial": args.trivial_cutoff,
                "fast": args.fast_cutoff,
                "medium": args.medium_cutoff,
            },
            "role": role,
            "dedup_order": args.years,
            "counts": {key: len(value) for key, value in groups.items()},
            "groups": groups,
        }
        output.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            f"{year} role={role} "
            + " ".join(
                f"{key}={len(groups[key])}"
                for key in (
                    "trivial_unique", "fast_unique", "medium_unique",
                    "slow_unique",
                    "timeout", "duplicate",
                )
            )
            + f" output={output}"
        )

    manifest_rows = []
    for record in records:
        manifest_rows.append({
            key: str(record[key])
            for key in (
                "year", "role", "name", "path", "size_bytes", "status",
                "wall_seconds", "tier", "sha256", "duplicate", "duplicate_of",
            )
        })
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    with args.manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(manifest_rows[0]), delimiter="\t"
        )
        writer.writeheader()
        writer.writerows(manifest_rows)
    print(f"manifest={args.manifest} rows={len(manifest_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
