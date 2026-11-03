#!/usr/bin/env python3
"""Export one structural row per recognized XOR without running PDR."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
from collections import Counter, deque
from pathlib import Path

from xag_structural_features import (
    backward_cone,
    compute_depths,
    is_xor_output,
    lit_sign,
    lit_var,
    read_aig,
)


HEADER = [
    "name", "aig_path", "xor_var", "xor_lit", "fanin0_var", "fanin1_var",
    "fanin0_sign", "fanin1_sign", "fanout", "depth", "relative_depth",
    "distance_to_next", "distance_to_bad", "in_next", "in_bad", "in_shared",
    "cone_class", "direct_next_root", "direct_bad_root", "impl_child0_var",
    "impl_child1_var", "impl_child_external_fanouts", "fanin_xor_count",
    "fanout_xor_count", "support0_size", "support1_size", "support_overlap",
    "support_jaccard", "support_truncated", "circuit_xors", "circuit_ands",
    "circuit_latches", "next_depth", "bad_depth",
]


def root_distances(roots: list[int], fanins: dict[int, tuple[int, int]]) -> dict[int, int]:
    distances: dict[int, int] = {}
    work = deque((lit_var(root), 0) for root in roots)
    while work:
        var, distance = work.popleft()
        previous = distances.get(var)
        if previous is not None and previous <= distance:
            continue
        distances[var] = distance
        if var not in fanins:
            continue
        for lit in fanins[var]:
            work.append((lit_var(lit), distance + 1))
    return distances


def bounded_support(
    lit: int,
    fanins: dict[int, tuple[int, int]],
    limit: int,
) -> tuple[set[int], bool]:
    leaves: set[int] = set()
    seen: set[int] = set()
    work = [lit_var(lit)]
    truncated = False
    while work:
        var = work.pop()
        if var in seen:
            continue
        seen.add(var)
        if len(seen) > limit:
            truncated = True
            break
        inputs = fanins.get(var)
        if inputs is None:
            if var:
                leaves.add(var)
            continue
        work.extend(lit_var(item) for item in inputs)
    return leaves, truncated


def rows_for_model(path: Path, support_limit: int) -> list[dict[str, str]]:
    aig = read_aig(path)
    by_var = {lit_var(gate.out): gate for gate in aig.ands}
    fanins = {
        lit_var(gate.out): (gate.i0, gate.i1)
        for gate in aig.ands
    }
    fanouts: Counter[int] = Counter()
    fanout_vars: dict[int, set[int]] = {}
    for gate in aig.ands:
        out_var = lit_var(gate.out)
        for lit in (gate.i0, gate.i1):
            var = lit_var(lit)
            fanouts[var] += 1
            fanout_vars.setdefault(var, set()).add(out_var)
    for latch in aig.latches:
        fanouts[lit_var(latch.next)] += 1
    for root in aig.outputs + aig.bads + aig.constraints:
        fanouts[lit_var(root)] += 1

    candidates: dict[int, tuple[int, int, int, int]] = {}
    for gate in aig.ands:
        matched, fanin0, fanin1 = is_xor_output(aig, gate, by_var)
        if matched:
            candidates[lit_var(gate.out)] = (
                fanin0,
                fanin1,
                lit_var(gate.i0),
                lit_var(gate.i1),
            )

    next_roots = [latch.next for latch in aig.latches]
    bad_roots = aig.bads if aig.bads else aig.outputs
    next_cone = backward_cone(next_roots, fanins)
    bad_cone = backward_cone(bad_roots, fanins)
    next_distance = root_distances(next_roots, fanins)
    bad_distance = root_distances(bad_roots, fanins)
    depths = compute_depths(aig)
    next_depth = max([depths.get(lit_var(root), 0) for root in next_roots] or [0])
    bad_depth = max([depths.get(lit_var(root), 0) for root in bad_roots] or [0])
    root_depth = max(next_depth, bad_depth, 1)
    next_root_vars = {lit_var(root) for root in next_roots}
    bad_root_vars = {lit_var(root) for root in bad_roots}
    xor_vars = set(candidates)

    rows: list[dict[str, str]] = []
    for var, (fanin0, fanin1, child0, child1) in sorted(candidates.items()):
        in_next = var in next_cone
        in_bad = var in bad_cone
        if in_next and in_bad:
            cone_class = "shared"
        elif in_next:
            cone_class = "next-only"
        elif in_bad:
            cone_class = "bad-only"
        else:
            cone_class = "outside"
        support0, truncated0 = bounded_support(fanin0, fanins, support_limit)
        support1, truncated1 = bounded_support(fanin1, fanins, support_limit)
        overlap = len(support0 & support1)
        union = len(support0 | support1)
        external_children = max(0, fanouts[child0] - 1) + max(0, fanouts[child1] - 1)
        rows.append({
            "name": path.stem,
            "aig_path": str(path),
            "xor_var": str(var),
            "xor_lit": str(var << 1),
            "fanin0_var": str(lit_var(fanin0)),
            "fanin1_var": str(lit_var(fanin1)),
            "fanin0_sign": str(lit_sign(fanin0)),
            "fanin1_sign": str(lit_sign(fanin1)),
            "fanout": str(fanouts[var]),
            "depth": str(depths.get(var, 0)),
            "relative_depth": f"{depths.get(var, 0) / root_depth:.6f}",
            "distance_to_next": str(next_distance.get(var, -1)),
            "distance_to_bad": str(bad_distance.get(var, -1)),
            "in_next": str(int(in_next)),
            "in_bad": str(int(in_bad)),
            "in_shared": str(int(in_next and in_bad)),
            "cone_class": cone_class,
            "direct_next_root": str(int(var in next_root_vars)),
            "direct_bad_root": str(int(var in bad_root_vars)),
            "impl_child0_var": str(child0),
            "impl_child1_var": str(child1),
            "impl_child_external_fanouts": str(external_children),
            "fanin_xor_count": str(int(lit_var(fanin0) in xor_vars) + int(lit_var(fanin1) in xor_vars)),
            "fanout_xor_count": str(sum(item in xor_vars for item in fanout_vars.get(var, ()))),
            "support0_size": str(len(support0)),
            "support1_size": str(len(support1)),
            "support_overlap": str(overlap),
            "support_jaccard": f"{overlap / union:.6f}" if union else "0.000000",
            "support_truncated": str(int(truncated0 or truncated1)),
            "circuit_xors": str(len(candidates)),
            "circuit_ands": str(len(aig.ands)),
            "circuit_latches": str(len(aig.latches)),
            "next_depth": str(next_depth),
            "bad_depth": str(bad_depth),
        })
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--support-limit", type=int, default=4096)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.workers <= 0 or args.support_limit <= 0:
        raise SystemExit("workers and support-limit must be positive")
    all_rows: list[dict[str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(rows_for_model, path, args.support_limit): path
            for path in args.models
        }
        for future in concurrent.futures.as_completed(futures):
            all_rows.extend(future.result())
    all_rows.sort(key=lambda row: (row["name"], int(row["xor_var"])))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER, delimiter="\t")
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"models={len(args.models)} xors={len(all_rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
