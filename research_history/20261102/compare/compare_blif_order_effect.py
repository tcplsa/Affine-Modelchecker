#!/usr/bin/env python3
"""
隔离 BLIF/PIC3 中“变量排序/初始结构”影响的小实验。

同一个 PDRblif.pdr_main 算法，分别喂入:
  layered-blif : 现有 BLIF parser 的 layered variable order
  aiger-xag    : AIG->XAG 后保留 AIGER/XAG 原始变量顺序

用法:
  python3 compare_blif_order_effect.py --mode layered-blif shift1add512
  python3 compare_blif_order_effect.py --all shift1add256 shift1add512
"""

import argparse
import importlib
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BLIF_DIR = ROOT / "blif"
PIC3_AIG_DIR = ROOT / "PIC3_aig"
HWMCC_DATA = ROOT / "test_tools" / "hwmcc2015" / "data"
CONV_BLIF_DIR = ROOT / "test_tools" / "compare" / "results" / "conversion" / "blif"


def lit_var(lit):
    return lit >> 1


def lit_sign(lit):
    return lit & 1


def aiger_to_dimacs(lit):
    var = lit >> 1
    return -var - 1 if lit & 1 else var + 1


def dimacs_to_aiger(lit):
    if lit < 0:
        return ((-lit - 1) << 1) | 1
    return (lit - 1) << 1


def load_aig_as_xag(name):
    if str(PIC3_AIG_DIR) not in sys.path:
        sys.path.insert(0, str(PIC3_AIG_DIR))
    from Aiger import read_aig
    from aig2xag import convert_aig_to_xag

    path = HWMCC_DATA / f"{name}.aig"
    return convert_aig_to_xag(read_aig(str(path)))


def make_result_class():
    if str(BLIF_DIR) not in sys.path:
        sys.path.insert(0, str(BLIF_DIR))
    from blif_output import BLIFParserResult
    return BLIFParserResult


def xag_to_blif_result(xag):
    BLIFParserResult = make_result_class()
    result = BLIFParserResult()
    result.inputs = [aiger_to_dimacs(lit) for lit in xag["inputs"]]
    result.outputs = [aiger_to_dimacs(lit) for lit in xag["bad"][:1]]
    result.constraints = [aiger_to_dimacs(lit) for lit in xag.get("constraints", [])]
    result.latches = [
        (aiger_to_dimacs(l["next"]), aiger_to_dimacs(l["current"]), l.get("default", 0))
        for l in xag["latches"]
    ]
    result.ands = [(aiger_to_dimacs(o), aiger_to_dimacs(i1), aiger_to_dimacs(i2)) for o, i1, i2 in xag["ands"]]
    result.xors = [(aiger_to_dimacs(o), aiger_to_dimacs(i1), aiger_to_dimacs(i2)) for o, i1, i2 in xag.get("xors", [])]
    result.ors = [(aiger_to_dimacs(o), aiger_to_dimacs(i1), aiger_to_dimacs(i2)) for o, i1, i2 in xag.get("ors", [])]
    result.var_count = xag["M"] + 1
    return result


def load_layered_blif(name):
    if str(BLIF_DIR) not in sys.path:
        sys.path.insert(0, str(BLIF_DIR))
    from blif_output import parse_blif_with_layered_vars

    return parse_blif_with_layered_vars(str(CONV_BLIF_DIR / f"{name}.blif"))


def reset_pdrblif_module():
    # PDRblif uses global state; reload it for each run in this process.
    if str(BLIF_DIR) not in sys.path:
        sys.path.insert(0, str(BLIF_DIR))
    if "PDRblif" in sys.modules:
        return importlib.reload(sys.modules["PDRblif"])
    return importlib.import_module("PDRblif")


def run_mode(name, mode, solver):
    os.environ["BLIF_SOLVER_BACKEND"] = solver
    pdr = reset_pdrblif_module()
    pdr._worker_silent = True

    if mode == "layered-blif":
        data = load_layered_blif(name)
    elif mode == "aiger-xag":
        data = xag_to_blif_result(load_aig_as_xag(name))
    else:
        raise ValueError(mode)

    t0 = time.perf_counter()
    result, log, extra = pdr.pdr_main(data)
    elapsed = time.perf_counter() - t0
    status = "SAFE" if result == 20 else ("UNSAFE" if result == 10 else "UNKNOWN")
    return {
        "name": name,
        "mode": mode,
        "status": status,
        "time": elapsed,
        "depth": extra.get("converged_frame", ""),
        "inductive": log.inductive_cnt,
        "generalize": log.generlize_cnt,
        "ctg": log.ctg_cnt,
        "extract": log.extrct_cnt,
        "pre": log.prebad_cnt,
        "ands": len(data.ands),
        "xors": len(data.xors),
        "ors": len(data.ors),
    }


def print_row(row):
    print(
        "{name}\t{mode}\t{status}\t{time:.6f}\t{depth}\t{inductive}\t{generalize}\t{ctg}\t"
        "{extract}\t{pre}\t{ands}\t{xors}\t{ors}".format(**row),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description="Compare PDRblif ordering effects")
    parser.add_argument("names", nargs="+", help="benchmark stem names, e.g. shift1add512")
    parser.add_argument("--mode", choices=["layered-blif", "aiger-xag"], default="layered-blif")
    parser.add_argument("--all", action="store_true", help="run all supported modes for every benchmark")
    parser.add_argument("--solver", choices=["minisat", "cmsat"], default="minisat")
    args = parser.parse_args()

    modes = ["layered-blif", "aiger-xag"] if args.all else [args.mode]
    print("name\tmode\tstatus\ttime\tdepth\tinductive\tgeneralize\tctg\textract\tpre\tands\txors\tors")
    for name in args.names:
        for mode in modes:
            try:
                print_row(run_mode(name, mode, args.solver))
            except Exception as exc:
                print(f"{name}\t{mode}\tERROR\t0\t\t0\t0\t0\t0\t0\t0\t0\t0\t{type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    main()
