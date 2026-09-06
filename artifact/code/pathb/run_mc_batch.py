#!/usr/bin/env python3
"""Batch-run MC on a set of AAG benchmarks with config variants.

Usage:
  python3 run_mc_batch.py --bench /dir/bench1.aag /dir/bench2.aag ... \
      [--env "KEY=VAL" ...] [--mc /path/to/modelchecker] [--timeout N] \
      [--threads N] [--out /tmp/out.csv]

Extracts runtime / depth / cti / lemma stats from MC's PDR_COUNTERS line.
"""
import argparse
import csv
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

MC_DEFAULT = "/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker"

STAT_RE = {
    "runtime": re.compile(r"runtime=([0-9.]+)"),
    "depth": re.compile(r"depth=([0-9]+)"),
    "cti": re.compile(r"cti=([0-9]+)"),
    "inductive": re.compile(r"inductive=([0-9]+)"),
    "queries": re.compile(r"queries=([0-9]+)"),
    "mic": re.compile(r"mic=([0-9]+)"),
    "lemma_added": re.compile(r"lemma_added=([0-9]+)"),
    "lemma_literals": re.compile(r"lemma_literals=([0-9]+)"),
    "frame_core": re.compile(r"frame_core=([0-9]+)"),
    "frame_core_literals": re.compile(r"frame_core_literals=([0-9]+)"),
    "abort_mic": re.compile(r"abort_mic=([0-9]+)"),
}


def run_one(bench, env, mc, timeout):
    """Run MC once, return dict of stats + result."""
    bench_name = os.path.basename(bench)
    base_env = dict(os.environ)
    base_env.update(env)
    base_env["MC_PDR_STATS"] = "1"
    cmd = [mc, "--forward-xag", "1", bench]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, env=base_env, capture_output=True,
                              text=True, timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        timed_out = True
        proc = None
    elapsed = time.time() - t0

    out = proc.stdout if proc else ""
    row = {"bench": bench_name, "timed_out": timed_out,
           "wall": round(elapsed, 4), "exit": proc.returncode if proc else -1}
    for key, regex in STAT_RE.items():
        m = regex.search(out)
        row[key] = m.group(1) if m else ""
    m = re.search(r"result:\s*(\w+)", out)
    row["result"] = m.group(1) if m else ""
    if not timed_out and proc and proc.returncode != 0 and not row["result"]:
        row["result"] = f"ERR({proc.returncode})"
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", nargs="+", required=True)
    ap.add_argument("--env", action="append", default=[],
                    help="extra env VAR=VAL; each is a variant")
    ap.add_argument("--mc", default=MC_DEFAULT)
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--out", default=None)
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    # variants: a list of env-dicts; --env "A=1" --env "B=2" is one variant.
    # To test multiple configs, pass them space separated per --env? We instead
    # treat each --env as an independent single-knob toggle plus a baseline.
    variants = [dict()]  # baseline
    for ev in args.env:
        key, val = ev.split("=", 1)
        d = dict()
        d[key] = val
        variants.append(d)

    tasks = []
    for bench in args.bench:
        for v in variants:
            tasks.append((bench, v))
    results = []
    with ThreadPoolExecutor(max_workers=args.threads) as ex:
        futs = {ex.submit(run_one, b, v, args.mc, args.timeout): (b, v)
                for b, v in tasks}
        for fut in futs:
            b, v = futs[fut]
            row = fut.result()
            row["variant"] = ",".join(f"{k}={val}" for k, val in sorted(v.items()))
            results.append(row)

    fieldnames = (["bench", "variant", "result", "timed_out", "wall", "exit",
                   "runtime", "depth", "cti", "queries", "inductive", "mic",
                   "lemma_added", "lemma_literals", "abort_mic"] +
                  sorted({k for r in results for k in r} - set(
                      ["bench", "variant", "result", "timed_out", "wall",
                       "exit", "runtime", "depth", "cti", "queries",
                       "inductive", "mic", "lemma_added", "lemma_literals",
                       "abort_mic"])))
    if args.out:
        with open(args.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in sorted(results, key=lambda x: (x["bench"], x["variant"])):
                w.writerow(r)
        print(f"wrote {args.out}")
    if args.show:
        for r in sorted(results, key=lambda x: (x["bench"], x["variant"])):
            print(f"{r['bench']:<40} {r['variant']:<20} "
                  f"res={r['result']:<6} wall={r['wall']:<7} "
                  f"depth={r['depth']:<5} cti={r['cti']:<6} "
                  f"runtime={r['runtime']}")


if __name__ == "__main__":
    main()
