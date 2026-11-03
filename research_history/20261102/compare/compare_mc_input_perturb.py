#!/usr/bin/env python3
"""
Modelchecker-xag structure perturbation experiment.

Runs the same AIG under multiple -pseed values and records PDR
stats.  This isolates whether semantics-preserving renumbering of inputs,
latches, or local gate runs can significantly change IC3/PDR search.
"""

import argparse
import concurrent.futures
import os
import re
import subprocess
import time
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
TOOLS_DIR = SCRIPT_DIR.parent
ROOT = TOOLS_DIR.parent

MODELCHECKER_DIR = ROOT / "Modelchecker-xag" / "modelchecker"
MODELCHECKER_BIN = MODELCHECKER_DIR / "modelchecker"
HWMCC_DATA = TOOLS_DIR / "hwmcc2015" / "data"
RESULTS_DIR = SCRIPT_DIR / "results"
LOG_DIR = RESULTS_DIR / "input_perturb_logs"
DEFAULT_OUTPUT = RESULTS_DIR / "compare_mc_input_perturb.tsv"


HEADER = [
    "name",
    "mode",
    "perturb",
    "seed",
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


def parse_args():
    p = argparse.ArgumentParser(description="MC structure perturbation experiment")
    p.add_argument("benchmarks", nargs="+", help="benchmark stem or .aig path")
    p.add_argument("--mode", choices=["aig", "xag"], default="xag")
    p.add_argument(
        "--perturb",
        default="input",
        help="comma-separated perturb modes: input,input-swap,input-fanout,input-fanout-rev,latch,gate-run,all",
    )
    p.add_argument("--seeds", type=int, default=32, help="run seeds 0..N-1")
    p.add_argument("--seed-start", type=int, default=0)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--mc-pdr", type=int, default=1)
    p.add_argument("--repeats", type=int, default=1, help="repeat each seed and take the fastest in summaries")
    p.add_argument("--include-baseline", action="store_true", help="also run once without -perturb")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return p.parse_args()


def resolve_benchmark(arg):
    p = Path(arg)
    if p.exists():
        return p
    return HWMCC_DATA / f"{arg}.aig"


def parse_key_values(line):
    out = {}
    for part in line.split():
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k] = v
    return out


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
    global_maps = []

    for line in text.splitlines():
        if "_PERMUTE" in line or "INPUT_SCORE_" in line or "INPUT_SWAP" in line:
            kv = parse_key_values(line)
            tag = line.split()[1] if len(line.split()) > 1 else "PERMUTE"
            global_maps.append(f"{tag}:{kv.get('map', '')}")
        elif "PDR_STATS" in line:
            kv = parse_key_values(line)
            current = {
                "pdr_runtime": kv.get("runtime", ""),
                "pdr_thread": kv.get("thread", ""),
                "depth": kv.get("depth", ""),
                "status": kv.get("result", status).upper(),
            }
            blocks.append(current)
        elif "PDR_COUNTERS" in line:
            kv = parse_key_values(line)
            target = current if current is not None else row
            target["queries"] = kv.get("queries", "")
            target["inductive"] = kv.get("inductive", "")
            target["cti"] = kv.get("cti", "")
            target["generalize"] = kv.get("generalize", "")
            target["extract"] = kv.get("extract", "")
            target["pre"] = kv.get("pre", "")
        elif "XAG_STATS" in line:
            kv = parse_key_values(line)
            target = current if current is not None else row
            target["ands"] = kv.get("ands", "")
            target["xors"] = kv.get("xors", "")

    row["map"] = ";".join(global_maps)
    complete = [b for b in blocks if b.get("pdr_runtime")]
    if complete:
        best = min(complete, key=lambda b: float(b["pdr_runtime"]))
        for key in [
            "status", "pdr_runtime", "pdr_thread", "depth", "queries", "inductive",
            "cti", "generalize", "extract", "pre", "ands", "xors"
        ]:
            if key in best:
                row[key] = best[key]

    return row


def run_one(aig_path, mode, seed, repeat, args):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    name = aig_path.stem
    seed_label = "baseline" if seed is None else f"seed{seed}"
    perturb_label = args.perturb.replace(",", "+")
    log_path = LOG_DIR / f"{name}_{mode}_{perturb_label}_{seed_label}_rep{repeat}.log"
    cmd = [str(MODELCHECKER_BIN), str(aig_path), "-pdr", str(args.mc_pdr), f"-{mode}"]
    env = os.environ.copy()
    env["MC_PDR_STATS"] = "1"
    if seed is not None:
        cmd.extend(["-perturb", args.perturb, "-pseed", str(seed)])

    t0 = time.perf_counter()
    try:
        with log_path.open("w") as lf:
            lf.write("cmd: " + " ".join(cmd) + "\n")
            if seed is not None:
                lf.write(f"args: -perturb {args.perturb} -pseed {seed}\n")
            lf.flush()
            proc = subprocess.run(
                cmd,
                cwd=str(MODELCHECKER_DIR),
                stdout=lf,
                stderr=subprocess.STDOUT,
                timeout=args.timeout,
                env=env,
            )
        text = log_path.read_text(errors="ignore")
        row = parse_output(text, proc.returncode)
    except subprocess.TimeoutExpired:
        row = {k: "" for k in HEADER}
        row["status"] = "TIMEOUT"

    row.update({
        "name": name,
        "mode": mode,
        "perturb": args.perturb if seed is not None else "baseline",
        "seed": "baseline" if seed is None else seed,
        "repeat": repeat,
        "wall": f"{time.perf_counter() - t0:.3f}",
    })
    return row


def main():
    args = parse_args()
    aig_paths = [resolve_benchmark(x) for x in args.benchmarks]
    for p in aig_paths:
        if not p.exists():
            raise SystemExit(f"missing benchmark: {p}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\t".join(HEADER) + "\n")

    jobs = []
    for aig_path in aig_paths:
        if args.include_baseline:
            for repeat in range(args.repeats):
                jobs.append((aig_path, None, repeat))
        for seed in range(args.seed_start, args.seed_start + args.seeds):
            for repeat in range(args.repeats):
                jobs.append((aig_path, seed, repeat))

    print(
        f"running {len(jobs)} jobs, mode={args.mode}, perturb={args.perturb}, mc-pdr={args.mc_pdr}, "
        f"repeats={args.repeats}, workers={args.workers}, output={args.output}"
    )
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_one, p, args.mode, seed, repeat, args) for p, seed, repeat in jobs]
        for fut in concurrent.futures.as_completed(futs):
            row = fut.result()
            rows.append(row)
            with args.output.open("a") as f:
                f.write("\t".join(str(row.get(k, "")) for k in HEADER) + "\n")
            print(
                f"{row['name']} {row['mode']} perturb={row['perturb']} seed={row['seed']} rep={row['repeat']} {row['status']} "
                f"wall={row['wall']} pdr={row.get('pdr_runtime', '')} "
                f"thread={row.get('pdr_thread', '')} queries={row.get('queries', '')} "
                f"inductive={row.get('inductive', '')}",
                flush=True,
            )

    by_name = {}
    for row in rows:
        if row.get("queries"):
            by_name.setdefault(row["name"], []).append(row)
    for name, rs in by_name.items():
        best_by_seed = {}
        for r in rs:
            key = (r["mode"], r["perturb"], r["seed"])
            metric = float(r["pdr_runtime"] or r["wall"])
            if key not in best_by_seed or metric < float(best_by_seed[key]["pdr_runtime"] or best_by_seed[key]["wall"]):
                best_by_seed[key] = r
        best_rows = list(best_by_seed.values())
        qs = [int(r["queries"]) for r in best_rows]
        ts = [float(r["pdr_runtime"] or r["wall"]) for r in best_rows]
        best = min(best_rows, key=lambda r: float(r["pdr_runtime"] or r["wall"]))
        worst = max(best_rows, key=lambda r: float(r["pdr_runtime"] or r["wall"]))
        print(
            f"SUMMARY {name}: configs={len(best_rows)} runs={len(rs)} "
            f"query_min={min(qs)} query_max={max(qs)} query_ratio={max(qs)/min(qs):.3f} "
            f"pdr_min={min(ts):.3f} pdr_max={max(ts):.3f} pdr_ratio={max(ts)/min(ts):.3f} "
            f"best_seed={best['seed']} worst_seed={worst['seed']}",
            flush=True,
        )


if __name__ == "__main__":
    main()
