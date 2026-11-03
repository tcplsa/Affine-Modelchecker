#!/usr/bin/env python3
"""Extract no-PDR structural features for AIG-to-XAG selection.

The script mirrors the local modelchecker's structural XOR recognizer.  It
does not run PDR; it only parses AIG/AAG files, recognizes XOR patterns, and
computes global plus cone-level features that can be used to decide whether
XAG is likely to help.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import functools
import math
import re
import statistics
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
TOOLS_DIR = SCRIPT_DIR.parent
RESULTS_DIR = SCRIPT_DIR / "results"


@dataclass
class Latch:
    lit: int
    next: int
    default: int = 0


@dataclass
class AndGate:
    out: int
    i0: int
    i1: int


@dataclass
class Aig:
    path: Path
    max_var: int
    inputs: list[int]
    latches: list[Latch]
    outputs: list[int]
    bads: list[int]
    constraints: list[int]
    ands: list[AndGate]


def lit_var(lit: int) -> int:
    return lit >> 1


def lit_sign(lit: int) -> int:
    return lit & 1


def read_ascii_aag(path: Path, first: str, rest: bytes) -> Aig:
    text = (first.encode() + b"\n" + rest).decode(
        "utf-8", errors="replace"
    ).splitlines()
    header = text[0].split()
    if len(header) < 6:
        raise ValueError(f"bad AAG header: {path}")
    _, m, i, l, o, a, *tail = header
    m_i, i_i, l_i, o_i, a_i = map(int, [m, i, l, o, a])
    b_i = int(tail[0]) if len(tail) >= 1 else 0
    c_i = int(tail[1]) if len(tail) >= 2 else 0

    pos = 1
    inputs = [int(text[pos + k].split()[0]) for k in range(i_i)]
    pos += i_i
    latches: list[Latch] = []
    for _ in range(l_i):
        parts = text[pos].split()
        latches.append(Latch(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0))
        pos += 1
    outputs = [int(text[pos + k].split()[0]) for k in range(o_i)]
    pos += o_i
    bads = [int(text[pos + k].split()[0]) for k in range(b_i)]
    pos += b_i
    constraints = [int(text[pos + k].split()[0]) for k in range(c_i)]
    pos += c_i
    ands = []
    for _ in range(a_i):
        parts = text[pos].split()
        ands.append(AndGate(int(parts[0]), int(parts[1]), int(parts[2])))
        pos += 1
    return Aig(path, m_i, inputs, latches, outputs, bads, constraints, ands)


def read_delta(data: bytes, pos: int) -> tuple[int, int]:
    x = 0
    shift = 0
    while True:
        if pos >= len(data):
            raise ValueError("truncated binary AIG delta")
        ch = data[pos]
        pos += 1
        x |= (ch & 0x7F) << shift
        if ch < 0x80:
            return x, pos
        shift += 7


def read_binary_aig(path: Path, first: str, rest: bytes) -> Aig:
    header = first.split()
    if len(header) < 6:
        raise ValueError(f"bad AIG header: {path}")
    _, m, i, l, o, a, *tail = header
    m_i, i_i, l_i, o_i, a_i = map(int, [m, i, l, o, a])
    b_i = int(tail[0]) if len(tail) >= 1 else 0
    c_i = int(tail[1]) if len(tail) >= 2 else 0

    lines: list[bytes] = []
    pos = 0
    for _ in range(l_i + o_i + b_i + c_i):
        end = rest.find(b"\n", pos)
        if end < 0:
            raise ValueError(f"truncated AIG header body: {path}")
        lines.append(rest[pos:end])
        pos = end + 1

    inputs = [2 * x for x in range(1, i_i + 1)]
    latches: list[Latch] = []
    for k in range(l_i):
        parts = lines[k].decode("ascii", errors="replace").split()
        latch_lit = 2 * (i_i + k + 1)
        next_lit = int(parts[0])
        default = int(parts[1]) if len(parts) > 1 else 0
        latches.append(Latch(latch_lit, next_lit, default))

    base = l_i
    outputs = [int(lines[base + k]) for k in range(o_i)]
    base += o_i
    bads = [int(lines[base + k]) for k in range(b_i)]
    base += b_i
    constraints = [int(lines[base + k]) for k in range(c_i)]
    pos = sum(len(line) + 1 for line in lines)

    ands: list[AndGate] = []
    for k in range(a_i):
        lhs = 2 * (i_i + l_i + k + 1)
        d0, pos = read_delta(rest, pos)
        d1, pos = read_delta(rest, pos)
        rhs0 = lhs - d0
        rhs1 = rhs0 - d1
        ands.append(AndGate(lhs, rhs0, rhs1))
    return Aig(path, m_i, inputs, latches, outputs, bads, constraints, ands)


def read_aig(path: Path) -> Aig:
    data = path.read_bytes()
    end = data.find(b"\n")
    if end < 0:
        raise ValueError(f"missing AIG header: {path}")
    first = data[:end].decode("ascii", errors="replace")
    rest = data[end + 1 :]
    if first.startswith("aag "):
        return read_ascii_aag(path, first, rest)
    if first.startswith("aig "):
        return read_binary_aig(path, first, rest)
    raise ValueError(f"unknown AIGER header: {path}")


def read_header_counts(path: Path) -> dict[str, int]:
    with path.open("rb") as f:
        header = f.readline().decode("ascii", errors="replace").split()
    if len(header) < 6 or header[0] not in {"aig", "aag"}:
        raise ValueError(f"bad AIGER header: {path}")
    _, max_var, inputs, latches, outputs, ands, *tail = header
    return {
        "max_var": int(max_var),
        "inputs": int(inputs),
        "latches": int(latches),
        "outputs": int(outputs),
        "ands": int(ands),
        "bads": int(tail[0]) if len(tail) >= 1 else 0,
        "constraints": int(tail[1]) if len(tail) >= 2 else 0,
    }


def family_name(name: str) -> str:
    match = re.match(r"([A-Za-z_]+)", name)
    return match.group(1) if match else name


def is_xor_output(aig: Aig, gate: AndGate, by_var: dict[int, AndGate]) -> tuple[bool, int, int]:
    if not lit_sign(gate.i0) or not lit_sign(gate.i1):
        return False, 0, 0
    v0 = lit_var(gate.i0)
    v1 = lit_var(gate.i1)
    lo = len(aig.inputs) + len(aig.latches) + 1
    if not (lo <= v0 <= aig.max_var and lo <= v1 <= aig.max_var):
        return False, 0, 0
    g0 = by_var.get(v0)
    g1 = by_var.get(v1)
    if g0 is None or g1 is None:
        return False, 0, 0

    def ordered(g: AndGate) -> tuple[int, int]:
        return (g.i0, g.i1) if lit_var(g.i0) < lit_var(g.i1) else (g.i1, g.i0)

    g00, g01 = ordered(g0)
    g10, g11 = ordered(g1)
    if lit_var(g00) != lit_var(g10) or lit_var(g01) != lit_var(g11):
        return False, 0, 0

    s00, s01, s10, s11 = map(lit_sign, [g00, g01, g10, g11])
    if (s00 and s01 and not s10 and not s11) or (not s00 and not s01 and s10 and s11):
        return True, lit_var(g00) << 1, lit_var(g01) << 1
    if (not s00 and s01 and s10 and not s11) or (s00 and not s01 and not s10 and s11):
        return True, lit_var(g00) << 1, (lit_var(g01) << 1) | 1
    return False, 0, 0


def backward_cone(roots: list[int], fanins: dict[int, tuple[int, int]]) -> set[int]:
    seen: set[int] = set()
    work = deque(lit_var(root) for root in roots)
    while work:
        var = work.popleft()
        if var in seen or var not in fanins:
            continue
        seen.add(var)
        a, b = fanins[var]
        va, vb = lit_var(a), lit_var(b)
        if va in fanins:
            work.append(va)
        if vb in fanins:
            work.append(vb)
    return seen


def compute_depths(aig: Aig) -> dict[int, int]:
    depths: dict[int, int] = {}
    for gate in aig.ands:
        depths[lit_var(gate.out)] = 1 + max(depths.get(lit_var(gate.i0), 0), depths.get(lit_var(gate.i1), 0))
    return depths


def depth_to_roots(roots: list[int], depths: dict[int, int]) -> int:
    return max([depths.get(lit_var(root), 0) for root in roots] or [0])


def structural_row(path: Path) -> dict[str, str]:
    aig = read_aig(path)
    by_var = {lit_var(g.out): g for g in aig.ands}
    raw_fanins = {lit_var(g.out): (g.i0, g.i1) for g in aig.ands}
    depths = compute_depths(aig)
    fanouts: Counter[int] = Counter()
    for gate in aig.ands:
        fanouts[lit_var(gate.i0)] += 1
        fanouts[lit_var(gate.i1)] += 1
    for latch in aig.latches:
        fanouts[lit_var(latch.next)] += 1
    for root in aig.outputs + aig.bads + aig.constraints:
        fanouts[lit_var(root)] += 1

    xor_vars: set[int] = set()
    xor_fanins: dict[int, tuple[int, int]] = {}
    for gate in aig.ands:
        ok, a, b = is_xor_output(aig, gate, by_var)
        if ok:
            var = lit_var(gate.out)
            xor_vars.add(var)
            xor_fanins[var] = (a, b)

    roots_next = [l.next for l in aig.latches]
    roots_reset = [
        l.default for l in aig.latches
        if l.default > 1 and l.default != l.lit
    ]
    roots_bad = aig.bads if aig.bads else aig.outputs
    roots_all = roots_next + roots_reset + roots_bad + aig.constraints
    cone_next = backward_cone(roots_next, raw_fanins)
    cone_reset = backward_cone(roots_reset, raw_fanins)
    cone_bad = backward_cone(roots_bad, raw_fanins)
    cone_all = backward_cone(roots_all, raw_fanins)

    def cnt_xor(cone: set[int]) -> int:
        return len(cone & xor_vars)

    def density(x: int, total: int) -> float:
        return x / total if total else 0.0

    original_ands = len(aig.ands)
    recognized_xors = len(xor_vars)
    # Match the converter's accounting: an XOR output stays as one XAG gate, and
    # the two implementation children become sweepable when unused.
    xag_ands_est = max(0, original_ands - 3 * recognized_xors)
    and_reduction = 1.0 - (xag_ands_est / original_ands) if original_ands else 0.0
    xor_density = recognized_xors / (xag_ands_est + recognized_xors) if (xag_ands_est + recognized_xors) else 0.0

    next_x = cnt_xor(cone_next)
    reset_x = cnt_xor(cone_reset)
    bad_x = cnt_xor(cone_bad)
    all_x = cnt_xor(cone_all)
    shared_x = len(xor_vars & cone_next & cone_bad)
    next_only_x = len((xor_vars & cone_next) - cone_bad)
    bad_only_x = len((xor_vars & cone_bad) - cone_next)
    root_depth = max(
        depth_to_roots(roots_next, depths),
        depth_to_roots(roots_reset, depths),
        depth_to_roots(roots_bad + aig.constraints, depths),
    )
    deep_threshold = math.ceil(root_depth * 0.5)
    deep_x = sum(
        var in cone_all and depths.get(var, 0) >= deep_threshold
        for var in xor_vars
    )
    xor_depths = [depths.get(var, 0) for var in xor_vars]
    xor_fanouts = [fanouts[var] for var in xor_vars]

    def xor_fanout_count(limit: int) -> int:
        return sum(value < limit for value in xor_fanouts)

    low_fanout_2_x = xor_fanout_count(2)
    low_fanout_4_x = xor_fanout_count(4)
    low_fanout_8_x = xor_fanout_count(8)
    next_low_fanout_4_x = sum(
        var in cone_next and fanouts[var] < 4 for var in xor_vars
    )
    bad_low_fanout_4_x = sum(
        var in cone_bad and fanouts[var] < 4 for var in xor_vars
    )
    next_density = density(next_x, len(cone_next))
    reset_density = density(reset_x, len(cone_reset))
    bad_density = density(bad_x, len(cone_bad))
    all_density = density(all_x, len(cone_all))

    # Conservative no-PDR selector learned from HWMCC2015 regular results:
    # XAG only looks promising when XORs are not merely present, but materially
    # affect sequential/property cones and reduce the AND representation.
    score = 0
    reasons: list[str] = []
    if recognized_xors >= 8:
        score += 1
        reasons.append("xors>=8")
    if and_reduction >= 0.08:
        score += 1
        reasons.append("and_reduction>=8%")
    if max(next_density, bad_density, all_density) >= 0.04:
        score += 2
        reasons.append("cone_xor_density>=4%")
    if next_x >= 8:
        score += 1
        reasons.append("next_cone_xors>=8")
    if bad_x >= 4:
        score += 1
        reasons.append("bad_cone_xors>=4")
    if original_ands < 200 and recognized_xors < 16:
        score -= 1
        reasons.append("tiny_low_xor")
    if len(aig.latches) > 1000 and next_density < 0.02 and bad_density < 0.02:
        score -= 1
        reasons.append("large_low_cone_xor")

    if score >= 4:
        pred = "xag_likely"
    elif score <= 1:
        pred = "aig_likely"
    else:
        pred = "uncertain"

    tier_reasons: list[str] = []
    if recognized_xors < 8 or max(next_density, bad_density, all_density) < 0.01 or and_reduction < 0.02:
        tier = "skip_xag"
        tier_reasons.append("low_structural_xor_signal")
    elif recognized_xors >= 16 and and_reduction >= 0.08 and bad_density >= 0.15:
        tier = "strong_xag"
        tier_reasons.append("dense_bad_cone_xor")
    elif recognized_xors >= 32 and and_reduction >= 0.08 and next_density >= 0.07 and bad_x >= 8:
        tier = "try_xag"
        tier_reasons.append("dense_next_cone_xor_with_bad_overlap")
    elif recognized_xors >= 16 and and_reduction >= 0.04 and max(next_density, bad_density, all_density) >= 0.04:
        tier = "try_xag"
        tier_reasons.append("moderate_cone_xor")
    else:
        tier = "uncertain"
        tier_reasons.append("weak_or_ambiguous_xor_signal")

    return {
        "name": path.stem,
        "aig_path": str(path),
        "size_bytes": str(path.stat().st_size),
        "family": family_name(path.stem),
        "inputs": str(len(aig.inputs)),
        "latches": str(len(aig.latches)),
        "outputs": str(len(aig.outputs)),
        "bads": str(len(aig.bads)),
        "constraints": str(len(aig.constraints)),
        "reset_functions": str(len(roots_reset)),
        "aig_ands": str(original_ands),
        "xag_ands_est": str(xag_ands_est),
        "recognized_xors": str(recognized_xors),
        "and_reduction": f"{and_reduction:.6f}",
        "xor_density": f"{xor_density:.6f}",
        "xor_fanout_mean": f"{statistics.mean(xor_fanouts):.6f}" if xor_fanouts else "0.000000",
        "xor_fanout_median": f"{statistics.median(xor_fanouts):.6f}" if xor_fanouts else "0.000000",
        "xor_fanout_max": str(max(xor_fanouts) if xor_fanouts else 0),
        "low_fanout_2_xors": str(low_fanout_2_x),
        "low_fanout_2_fraction": f"{density(low_fanout_2_x, recognized_xors):.6f}",
        "low_fanout_4_xors": str(low_fanout_4_x),
        "low_fanout_4_fraction": f"{density(low_fanout_4_x, recognized_xors):.6f}",
        "low_fanout_8_xors": str(low_fanout_8_x),
        "low_fanout_8_fraction": f"{density(low_fanout_8_x, recognized_xors):.6f}",
        "next_cone_gates": str(len(cone_next)),
        "next_cone_xors": str(next_x),
        "next_xor_density": f"{next_density:.6f}",
        "next_xor_fraction": f"{density(next_x, recognized_xors):.6f}",
        "next_low_fanout_4_xors": str(next_low_fanout_4_x),
        "next_low_fanout_4_fraction": f"{density(next_low_fanout_4_x, next_x):.6f}",
        "reset_cone_gates": str(len(cone_reset)),
        "reset_cone_xors": str(reset_x),
        "reset_xor_density": f"{reset_density:.6f}",
        "bad_cone_gates": str(len(cone_bad)),
        "bad_cone_xors": str(bad_x),
        "bad_xor_density": f"{bad_density:.6f}",
        "bad_xor_fraction": f"{density(bad_x, recognized_xors):.6f}",
        "bad_low_fanout_4_xors": str(bad_low_fanout_4_x),
        "bad_low_fanout_4_fraction": f"{density(bad_low_fanout_4_x, bad_x):.6f}",
        "root_cone_gates": str(len(cone_all)),
        "root_cone_xors": str(all_x),
        "root_xor_density": f"{all_density:.6f}",
        "root_xor_fraction": f"{density(all_x, recognized_xors):.6f}",
        "shared_cone_xors": str(shared_x),
        "next_only_xors": str(next_only_x),
        "bad_only_xors": str(bad_only_x),
        "deep_cone_xors": str(deep_x),
        "xor_depth_mean": f"{statistics.mean(xor_depths):.6f}" if xor_depths else "0.000000",
        "xor_depth_median": f"{statistics.median(xor_depths):.6f}" if xor_depths else "0.000000",
        "xor_depth_max": str(max(xor_depths) if xor_depths else 0),
        "next_depth": str(depth_to_roots(roots_next, depths)),
        "reset_depth": str(depth_to_roots(roots_reset, depths)),
        "bad_depth": str(depth_to_roots(roots_bad, depths)),
        "xag_score": str(score),
        "xag_prediction": pred,
        "xag_reasons": ",".join(reasons),
        "xag_tier": tier,
        "xag_tier_reasons": ",".join(tier_reasons),
    }


HEADER = [
    "name",
    "aig_path",
    "size_bytes",
    "family",
    "inputs",
    "latches",
    "outputs",
    "bads",
    "constraints",
    "reset_functions",
    "aig_ands",
    "xag_ands_est",
    "recognized_xors",
    "and_reduction",
    "xor_density",
    "xor_fanout_mean",
    "xor_fanout_median",
    "xor_fanout_max",
    "low_fanout_2_xors",
    "low_fanout_2_fraction",
    "low_fanout_4_xors",
    "low_fanout_4_fraction",
    "low_fanout_8_xors",
    "low_fanout_8_fraction",
    "next_cone_gates",
    "next_cone_xors",
    "next_xor_density",
    "next_xor_fraction",
    "next_low_fanout_4_xors",
    "next_low_fanout_4_fraction",
    "reset_cone_gates",
    "reset_cone_xors",
    "reset_xor_density",
    "bad_cone_gates",
    "bad_cone_xors",
    "bad_xor_density",
    "bad_xor_fraction",
    "bad_low_fanout_4_xors",
    "bad_low_fanout_4_fraction",
    "root_cone_gates",
    "root_cone_xors",
    "root_xor_density",
    "root_xor_fraction",
    "shared_cone_xors",
    "next_only_xors",
    "bad_only_xors",
    "deep_cone_xors",
    "xor_depth_mean",
    "xor_depth_median",
    "xor_depth_max",
    "next_depth",
    "reset_depth",
    "bad_depth",
    "xag_score",
    "xag_prediction",
    "xag_reasons",
    "xag_tier",
    "xag_tier_reasons",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract structural XAG-selection features without running PDR.")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=RESULTS_DIR / "xag_structural_features.tsv")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sort", choices=["name", "size"], default="name")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--max-ands",
        type=int,
        default=50_000_000,
        help="skip full parsing above this AND count while retaining header features (0 disables)",
    )
    return parser.parse_args()


def safe_structural_row(path: Path, max_ands: int = 50_000_000) -> dict[str, str]:
    try:
        counts = read_header_counts(path)
        if max_ands > 0 and counts["ands"] > max_ands:
            row = {key: "" for key in HEADER}
            row.update({
                "name": path.stem,
                "aig_path": str(path),
                "size_bytes": str(path.stat().st_size),
                "family": family_name(path.stem),
                "inputs": str(counts["inputs"]),
                "latches": str(counts["latches"]),
                "outputs": str(counts["outputs"]),
                "bads": str(counts["bads"]),
                "constraints": str(counts["constraints"]),
                "aig_ands": str(counts["ands"]),
                "xag_prediction": "TOO_LARGE",
                "xag_reasons": (
                    f"aig_ands={counts['ands']}>max_ands={max_ands}; "
                    "rerun this model with --max-ands 0"
                ),
                "xag_tier": "deferred",
                "xag_tier_reasons": "full_graph_scan_deferred",
            })
            return row
        return structural_row(path)
    except Exception as exc:
        row = {key: "" for key in HEADER}
        row.update({
            "name": path.stem,
            "aig_path": str(path),
            "xag_prediction": "ERROR",
            "xag_reasons": str(exc),
        })
        return row


def main() -> int:
    args = parse_args()
    paths = list(args.data_dir.rglob("*.aig")) + list(args.data_dir.rglob("*.aag"))
    stem_counts = Counter(path.stem for path in paths)
    if args.sort == "size":
        paths.sort(key=lambda p: (p.stat().st_size, p.name))
    else:
        paths.sort(key=lambda p: p.name)
    if args.limit > 0:
        paths = paths[: args.limit]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER, delimiter="\t")
        writer.writeheader()
        row_builder = functools.partial(
            safe_structural_row,
            max_ands=args.max_ands,
        )
        if args.workers > 1:
            executor = concurrent.futures.ProcessPoolExecutor(max_workers=args.workers)
            rows = executor.map(row_builder, paths)
        else:
            executor = None
            rows = map(row_builder, paths)
        try:
            for idx, (path, row) in enumerate(zip(paths, rows), 1):
                if stem_counts[path.stem] > 1:
                    row["name"] = "__".join(
                        path.relative_to(args.data_dir).with_suffix("").parts
                    )
                writer.writerow(row)
                if idx % 50 == 0:
                    print(f"[{idx}/{len(paths)}] {path.name}", flush=True)
        finally:
            if executor is not None:
                executor.shutdown()
    print(f"wrote {len(paths)} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
