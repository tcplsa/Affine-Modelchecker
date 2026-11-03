#!/usr/bin/env python3
"""
Dedicated Modelchecker-xag PI pair-swap experiment.

For each benchmark this script reads the AIG header, enumerates primary-input
pairs in the same order as Modelchecker-xag's -perturb input-swap, and compares the
best swap against the unperturbed baseline.  The default uses single-threaded
PDR per Modelchecker-xag process to make runs easier to reproduce.
"""

import argparse
import concurrent.futures
import csv
import os
import random
import re
import subprocess
import threading
import time
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
TOOLS_DIR = SCRIPT_DIR.parent
ROOT = TOOLS_DIR.parent

MODELCHECKER_DIR = ROOT / "Modelchecker-xag" / "modelchecker"
MODELCHECKER_BIN = MODELCHECKER_DIR / "modelchecker"
HWMCC_DATA = TOOLS_DIR / "hwmcc2015" / "data"
HWMCC_SAMPLES = TOOLS_DIR / "hwmcc2015" / "samples" / "all.txt"
RESULTS_DIR = SCRIPT_DIR / "results"
LOG_DIR = RESULTS_DIR / "input_swap_logs"
DEFAULT_OUTPUT = RESULTS_DIR / "compare_mc_input_swap.tsv"
DEFAULT_SUMMARY = RESULTS_DIR / "compare_mc_input_swap_summary.tsv"

TSV_LOCK = threading.Lock()


DETAIL_HEADER = [
    "name",
    "aig_path",
    "mode",
    "num_inputs",
    "pair_count",
    "pair_index",
    "pair_i",
    "pair_j",
    "repeat",
    "status",
    "wall",
    "reported",
    "pdr_runtime",
    "pdr_thread",
    "depth",
    "queries",
    "inductive",
    "cti",
    "generalize",
    "extract",
    "pre",
    "ands",
    "xors",
    "map",
]

SUMMARY_HEADER = [
    "name",
    "aig_path",
    "mode",
    "num_inputs",
    "pair_count",
    "tested_pairs",
    "baseline_status",
    "baseline_pdr",
    "baseline_queries",
    "best_status",
    "best_pair_index",
    "best_pair",
    "best_pdr",
    "best_queries",
    "speedup_pdr",
    "query_ratio",
    "best_map",
    "worst_pair_index",
    "worst_pair",
    "worst_pdr",
    "spread_pdr",
]


def parse_args():
    p = argparse.ArgumentParser(description="Exhaustive/capped MC input-swap experiment")
    p.add_argument("benchmarks", nargs="*", help="benchmark stem or .aig path")
    p.add_argument("--all-hwmcc2015", action="store_true", help="run benchmarks from --sample-file")
    p.add_argument("--glob-all", action="store_true", help="with --all-hwmcc2015, scan data/*.aig instead of sample file")
    p.add_argument("--sample-file", type=Path, default=HWMCC_SAMPLES)
    p.add_argument("--max-size", type=int, default=0, help="skip AIG files larger than this many bytes; 0 disables")
    p.add_argument("--limit", type=int, default=0, help="run only first N selected benchmarks; 0 disables")
    p.add_argument("--mode", choices=["aig", "xag"], default="xag")
    p.add_argument("--mc-pdr", type=int, default=1)
    p.add_argument("--workers", type=int, default=16, help="concurrent MC processes")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--max-pairs", type=int, default=0, help="0 means enumerate every pair")
    p.add_argument("--sample", choices=["first", "random"], default="first")
    p.add_argument("--sample-seed", type=int, default=1)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY)
    p.add_argument("--skip-existing", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="only print selected benchmark/job count")
    p.add_argument("--summary-every", type=int, default=50, help="refresh summary after this many completed jobs; 0 disables")
    return p.parse_args()


def resolve_benchmark(arg):
    p = Path(arg)
    if p.exists():
        return p
    return HWMCC_DATA / f"{arg}.aig"


def discover_hwmcc2015(sample_file, glob_all, max_size, limit):
    if glob_all:
        paths = sorted(HWMCC_DATA.glob("*.aig"))
    else:
        if not sample_file.exists():
            raise SystemExit(f"missing sample file: {sample_file}")
        paths = []
        with sample_file.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                name = line.strip()
                if not name or name.startswith("#"):
                    continue
                p = HWMCC_DATA / name
                if p.exists():
                    paths.append(p)
                elif (HWMCC_DATA / f"{name}.aig").exists():
                    paths.append(HWMCC_DATA / f"{name}.aig")

    if max_size > 0:
        paths = [p for p in paths if p.stat().st_size <= max_size]
    paths.sort(key=lambda p: (p.stat().st_size, p.name))
    if limit > 0:
        paths = paths[:limit]
    return paths


def read_aig_header(aig_path):
    with aig_path.open("rb") as f:
        chunk = f.read(4096)
    first_line = chunk.split(b"\n", 1)[0]
    header = first_line.decode("ascii", errors="ignore").strip().split()
    if len(header) < 6 or header[0] not in ("aig", "aag"):
        raise ValueError(f"bad AIG header in {aig_path}")
    return {
        "format": header[0],
        "max_var": int(header[1]),
        "inputs": int(header[2]),
        "latches": int(header[3]),
        "outputs": int(header[4]),
        "ands": int(header[5]),
    }


def pair_for_index(num_inputs, pair_index):
    count = 0
    for i in range(1, num_inputs + 1):
        for j in range(i + 1, num_inputs + 1):
            if count == pair_index:
                return i, j
            count += 1
    raise ValueError(f"pair index out of range: {pair_index}")


def choose_pair_indices(num_inputs, max_pairs, sample, sample_seed):
    pair_count = num_inputs * (num_inputs - 1) // 2
    if max_pairs and pair_count > max_pairs:
        if sample == "random":
            rng = random.Random(sample_seed)
            indices = sorted(rng.sample(range(pair_count), max_pairs))
        else:
            indices = list(range(max_pairs))
    else:
        indices = list(range(pair_count))
    return pair_count, indices


def parse_key_values(line):
    out = {}
    for part in line.split():
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k] = v
    return out


def first_float(value):
    m = re.match(r"[0-9]+(?:\.[0-9]+)?", value or "")
    return m.group(0) if m else ""


def first_int(value):
    m = re.match(r"[0-9]+", value or "")
    return m.group(0) if m else ""


def parse_output(text, rc):
    lower = text.lower()
    if "result: safe" in lower:
        status = "SAFE"
    elif "result: unsafe" in lower:
        status = "UNSAFE"
    elif rc != 0:
        status = "ERROR"
    else:
        status = "UNKNOWN"

    row = {
        "status": status,
        "reported": "",
        "pdr_runtime": "",
        "pdr_thread": "",
        "depth": "",
        "queries": "",
        "inductive": "",
        "cti": "",
        "generalize": "",
        "extract": "",
        "pre": "",
        "ands": "",
        "xors": "",
        "map": "",
    }

    m = re.search(r"^time\s*=\s*([0-9.]+)s", text, re.MULTILINE)
    if m:
        row["reported"] = m.group(1)

    blocks = []
    current = None
    maps = []
    for line in text.splitlines():
        if "INPUT_SWAP" in line:
            kv = parse_key_values(line)
            maps.append(kv.get("map", ""))
        elif "PDR_STATS" in line:
            kv = parse_key_values(line)
            current = {
                "pdr_runtime": first_float(kv.get("runtime", "")),
                "pdr_thread": first_int(kv.get("thread", "")),
                "depth": first_int(kv.get("depth", "")),
                "status": kv.get("result", status).upper(),
            }
            blocks.append(current)
        elif "PDR_COUNTERS" in line:
            kv = parse_key_values(line)
            target = current if current is not None else row
            target["queries"] = first_int(kv.get("queries", ""))
            target["inductive"] = first_int(kv.get("inductive", ""))
            target["cti"] = first_int(kv.get("cti", ""))
            target["generalize"] = first_int(kv.get("generalize", ""))
            target["extract"] = first_int(kv.get("extract", ""))
            target["pre"] = first_int(kv.get("pre", ""))
        elif "XAG_STATS" in line:
            kv = parse_key_values(line)
            target = current if current is not None else row
            target["ands"] = first_int(kv.get("ands", ""))
            target["xors"] = first_int(kv.get("xors", ""))

    row["map"] = ";".join(maps)
    complete = [b for b in blocks if b.get("pdr_runtime")]
    if complete:
        best = min(complete, key=lambda b: float(b["pdr_runtime"]))
        for key in [
            "status", "pdr_runtime", "pdr_thread", "depth", "queries",
            "inductive", "cti", "generalize", "extract", "pre", "ands", "xors"
        ]:
            if key in best:
                row[key] = best[key]
    return row


def run_one(job, args):
    aig_path, num_inputs, pair_count, pair_index, repeat = job
    name = aig_path.stem
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if pair_index == "baseline":
        pair_i = pair_j = ""
        suffix = f"baseline_rep{repeat}"
        cmd = [str(MODELCHECKER_BIN), str(aig_path), "-pdr", str(args.mc_pdr), f"-{args.mode}"]
    else:
        pair_i, pair_j = pair_for_index(num_inputs, pair_index)
        suffix = f"swap{pair_index}_{pair_i}_{pair_j}_rep{repeat}"
        cmd = [
            str(MODELCHECKER_BIN),
            str(aig_path),
            "-pdr",
            str(args.mc_pdr),
            f"-{args.mode}",
            "-perturb",
            "input-swap",
            "-pseed",
            str(pair_index),
        ]

    log_path = LOG_DIR / f"{name}_{args.mode}_{suffix}.log"
    env = os.environ.copy()
    env["MC_PDR_STATS"] = "1"

    t0 = time.perf_counter()
    try:
        with log_path.open("w") as lf:
            lf.write("cmd: " + " ".join(cmd) + "\n")
            lf.flush()
            proc = subprocess.run(
                cmd,
                cwd=str(MODELCHECKER_DIR),
                stdout=lf,
                stderr=subprocess.STDOUT,
                timeout=args.timeout,
                env=env,
            )
        row = parse_output(log_path.read_text(errors="ignore"), proc.returncode)
    except subprocess.TimeoutExpired:
        row = {k: "" for k in DETAIL_HEADER}
        row["status"] = "TIMEOUT"

    row.update({
        "name": name,
        "aig_path": str(aig_path),
        "mode": args.mode,
        "num_inputs": num_inputs,
        "pair_count": pair_count,
        "pair_index": pair_index,
        "pair_i": pair_i,
        "pair_j": pair_j,
        "repeat": repeat,
        "wall": f"{time.perf_counter() - t0:.3f}",
    })
    return row


def metric(row):
    return float(row.get("pdr_runtime") or row.get("wall") or "inf")


def write_summary(rows, summary_output, append=False):
    by_name = {}
    for row in rows:
        if row.get("status") not in ("SAFE", "UNSAFE") or not row.get("pdr_runtime"):
            continue
        by_name.setdefault(row["name"], []).append(row)

    mode = "a" if append and summary_output.exists() else "w"
    with summary_output.open(mode, newline="") as f:
        w = csv.DictWriter(f, delimiter="\t", fieldnames=SUMMARY_HEADER)
        if mode == "w":
            w.writeheader()
        for name, rs in sorted(by_name.items()):
            baseline_rows = [r for r in rs if r["pair_index"] == "baseline"]
            swap_rows = [r for r in rs if r["pair_index"] != "baseline"]
            if not baseline_rows or not swap_rows:
                continue
            baseline = min(baseline_rows, key=metric)
            best = min(swap_rows, key=metric)
            worst = max(swap_rows, key=metric)
            speedup = metric(baseline) / metric(best) if metric(best) > 0 else 0.0
            query_ratio = ""
            if baseline.get("queries") and best.get("queries"):
                query_ratio = f"{int(baseline['queries']) / int(best['queries']):.6f}"
            w.writerow({
                "name": name,
                "aig_path": baseline["aig_path"],
                "mode": baseline["mode"],
                "num_inputs": baseline["num_inputs"],
                "pair_count": baseline["pair_count"],
                "tested_pairs": len({r["pair_index"] for r in swap_rows}),
                "baseline_status": baseline["status"],
                "baseline_pdr": baseline["pdr_runtime"],
                "baseline_queries": baseline["queries"],
                "best_status": best["status"],
                "best_pair_index": best["pair_index"],
                "best_pair": f"{best['pair_i']},{best['pair_j']}",
                "best_pdr": best["pdr_runtime"],
                "best_queries": best["queries"],
                "speedup_pdr": f"{speedup:.6f}",
                "query_ratio": query_ratio,
                "best_map": best["map"],
                "worst_pair_index": worst["pair_index"],
                "worst_pair": f"{worst['pair_i']},{worst['pair_j']}",
                "worst_pdr": worst["pdr_runtime"],
                "spread_pdr": f"{metric(worst) / metric(best):.6f}" if metric(best) > 0 else "",
            })


def existing_completed(output):
    if not output.exists():
        return set()
    done = set()
    with output.open(newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row.get("status") in ("SAFE", "UNSAFE"):
                done.add((row["name"], row.get("mode", ""), row["pair_index"], row["repeat"]))
    return done


def main():
    args = parse_args()
    if args.all_hwmcc2015:
        aig_paths = discover_hwmcc2015(args.sample_file, args.glob_all, args.max_size, args.limit)
    else:
        if not args.benchmarks:
            raise SystemExit("provide benchmarks or use --all-hwmcc2015")
        aig_paths = [resolve_benchmark(x) for x in args.benchmarks]

    if not aig_paths:
        raise SystemExit("no benchmarks selected")
    for p in aig_paths:
        if not p.exists():
            raise SystemExit(f"missing benchmark: {p}")

    jobs = []
    total_pairs = 0
    for aig_path in aig_paths:
        header = read_aig_header(aig_path)
        num_inputs = header["inputs"]
        pair_count, pair_indices = choose_pair_indices(
            num_inputs, args.max_pairs, args.sample, args.sample_seed)
        total_pairs += len(pair_indices)
        for repeat in range(args.repeats):
            base_key = (aig_path.stem, "baseline", str(repeat))
            jobs.append((aig_path, num_inputs, pair_count, "baseline", repeat))
            for pair_index in pair_indices:
                jobs.append((aig_path, num_inputs, pair_count, pair_index, repeat))

    completed = existing_completed(args.output) if args.skip_existing else set()
    total_jobs = len(jobs)
    if completed:
        jobs = [
            job for job in jobs
            if (job[0].stem, args.mode, str(job[3]), str(job[4])) not in completed
        ]

    print(
        f"selected {len(aig_paths)} benchmarks; total_jobs={total_jobs}; "
        f"remaining_jobs={len(jobs)}, mode={args.mode}, pdr={args.mc_pdr}, "
        f"repeats={args.repeats}, max_pairs={args.max_pairs}, workers={args.workers}",
        flush=True,
    )
    if args.dry_run:
        print(f"dry-run: selected_pairs_per_repeat={total_pairs}", flush=True)
        print(f"dry-run: completed_jobs={len(completed)}", flush=True)
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)

    write_header = not args.output.exists() or not args.skip_existing
    if write_header:
        args.output.write_text("\t".join(DETAIL_HEADER) + "\n")
        if args.summary_output.exists():
            args.summary_output.unlink()
    elif not jobs and args.output.exists():
        with args.output.open(newline="") as f:
            write_summary(list(csv.DictReader(f, delimiter="\t")), args.summary_output, append=False)
        print(f"summary refreshed: {args.summary_output}", flush=True)
        return

    rows = []
    completed_now = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_one, job, args) for job in jobs]
        for fut in concurrent.futures.as_completed(futs):
            row = fut.result()
            rows.append(row)
            with TSV_LOCK:
                with args.output.open("a", newline="") as f:
                    w = csv.DictWriter(f, delimiter="\t", fieldnames=DETAIL_HEADER)
                    w.writerow({k: row.get(k, "") for k in DETAIL_HEADER})
            pair = "baseline" if row["pair_index"] == "baseline" else f"{row['pair_i']}<->{row['pair_j']}"
            print(
                f"{row['name']} pair={pair} rep={row['repeat']} {row['status']} "
                f"pdr={row.get('pdr_runtime', '')} queries={row.get('queries', '')}",
                flush=True,
            )
            completed_now += 1
            if args.summary_every > 0 and completed_now % args.summary_every == 0:
                with args.output.open(newline="") as f:
                    write_summary(list(csv.DictReader(f, delimiter="\t")), args.summary_output, append=False)
                print(f"summary refreshed after {completed_now} jobs: {args.summary_output}", flush=True)

    all_rows = []
    with args.output.open(newline="") as f:
        all_rows = list(csv.DictReader(f, delimiter="\t"))
    write_summary(all_rows, args.summary_output, append=False)
    print(f"detail: {args.output}", flush=True)
    print(f"summary: {args.summary_output}", flush=True)


if __name__ == "__main__":
    main()
