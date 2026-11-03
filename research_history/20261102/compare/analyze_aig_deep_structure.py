#!/usr/bin/env python3
"""Extract PDR-relevant structure from AIGER circuits.

The usual AIG header is too coarse for explaining why PDR stalls.  This tool
looks at the transition relation as a graph: the bad cone, the union of all
next-state cones, their overlap, canonical XOR/MUX roots, and sampled latch
dependencies.  It accepts binary ``.aig`` via the local ``aigtoaig`` converter
or an ASCII ``.aag`` directly.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import tempfile
from array import array
from collections import Counter
from pathlib import Path
from typing import Iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path,
                        help="JSON list or {models:[...]} with id/path fields")
    parser.add_argument("--aig", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--converter", type=Path,
                        default=Path("/home/wudl/Modelchecker-bidirectional/modelchecker/aigtoaig"))
    parser.add_argument("--sample-next", type=int, default=128)
    parser.add_argument("--unroll-depth", type=int, default=4,
                        help="report property-latch preimage cone growth through this many steps")
    parser.add_argument("--closure-steps", type=int, default=128,
                        help="maximum rounds when computing the exact property state closure")
    return parser.parse_args()


def lit_var(lit: int) -> int:
    return lit >> 1


class Aag:
    def __init__(self, path: Path) -> None:
        with path.open("r", encoding="ascii", errors="replace") as source:
            header = source.readline().split()
            if not header or header[0] != "aag" or len(header) < 6:
                raise ValueError(f"expected ASCII AIGER file: {path}")
            values = [int(value) for value in header[1:]]
            (self.maxvar, self.inputs, self.latches, self.outputs, self.ands) = values[:5]
            self.bads = values[5] if len(values) > 5 else 0
            self.constraints = values[6] if len(values) > 6 else 0
            self.justice = values[7] if len(values) > 7 else 0
            self.fairness = values[8] if len(values) > 8 else 0

            for _ in range(self.inputs):
                source.readline()
            self.next_lits: list[int] = []
            self.latch_lits: list[int] = []
            self.latch_init_lits: list[int | None] = []
            for _ in range(self.latches):
                fields = source.readline().split()
                self.latch_lits.append(int(fields[0]))
                self.next_lits.append(int(fields[1]))
                self.latch_init_lits.append(int(fields[2]) if len(fields) > 2 else None)
            self.output_lits = [int(source.readline()) for _ in range(self.outputs)]
            self.bad_lits = [int(source.readline()) for _ in range(self.bads)]
            self.constraint_lits = [int(source.readline()) for _ in range(self.constraints)]
            justice_sizes = [int(source.readline()) for _ in range(self.justice)]
            for _ in range(sum(justice_sizes) + self.fairness):
                source.readline()

            self.left = array("I", [0]) * (self.maxvar + 1)
            self.right = array("I", [0]) * (self.maxvar + 1)
            for _ in range(self.ands):
                lhs, rhs0, rhs1 = map(int, source.readline().split())
                var = lit_var(lhs)
                self.left[var] = rhs0
                self.right[var] = rhs1

    @property
    def gate_start(self) -> int:
        return self.inputs + self.latches + 1

    def is_gate(self, var: int) -> bool:
        return self.gate_start <= var <= self.maxvar and self.left[var] != 0

    def backward_cone(self, roots: Iterable[int]) -> bytearray:
        seen = bytearray(self.maxvar + 1)
        stack = [lit_var(root) for root in roots]
        while stack:
            var = stack.pop()
            if var == 0 or seen[var]:
                continue
            seen[var] = 1
            if self.is_gate(var):
                stack.append(lit_var(self.left[var]))
                stack.append(lit_var(self.right[var]))
        return seen

    def depths(self) -> array:
        depth = array("I", [0]) * (self.maxvar + 1)
        for var in range(self.gate_start, self.maxvar + 1):
            if not self.is_gate(var):
                continue
            depth[var] = 1 + max(depth[lit_var(self.left[var])],
                                 depth[lit_var(self.right[var])])
        return depth


    def is_xor(self, var: int) -> bool:
        """Match the canonical XOR/XNOR lowering used by our XAG frontend."""
        a, b = self.left[var], self.right[var]
        if not (a & 1 and b & 1):
            return False
        va, vb = lit_var(a), lit_var(b)
        if not (self.is_gate(va) and self.is_gate(vb)):
            return False
        a0, a1 = sorted((self.left[va], self.right[va]))
        b0, b1 = sorted((self.left[vb], self.right[vb]))
        if lit_var(a0) != lit_var(b0) or lit_var(a1) != lit_var(b1):
            return False
        signs = (a0 & 1, a1 & 1, b0 & 1, b1 & 1)
        return signs in {(1, 1, 0, 0), (0, 0, 1, 1), (0, 1, 1, 0), (1, 0, 0, 1)}

    def is_mux(self, var: int) -> bool:
        """Recognize an AND/NOT lowered two-way mux, independent of branch order."""
        a, b = self.left[var], self.right[var]
        if not (a & 1 and b & 1):
            return False
        va, vb = lit_var(a), lit_var(b)
        if not (self.is_gate(va) and self.is_gate(vb)):
            return False
        pa = (self.left[va], self.right[va])
        pb = (self.left[vb], self.right[vb])
        for xa in pa:
            for xb in pb:
                if lit_var(xa) == lit_var(xb) and (xa ^ xb) == 1:
                    return True
        return False

    def sampled_latch_dependencies(self, sample_size: int) -> tuple[float, float, int]:
        if self.latches == 0:
            return 0.0, 0.0, 0
        count = min(sample_size, self.latches)
        if count == self.latches:
            selected = list(range(self.latches))
        else:
            selected = [round(i * (self.latches - 1) / max(1, count - 1))
                        for i in range(count)]
        latch_begin = self.inputs + 1
        latch_end = self.inputs + self.latches
        seen = bytearray(self.maxvar + 1)
        stamp = 0
        lengths: list[int] = []
        self_loops = 0
        for index in selected:
            stamp += 1
            # A bytearray is reset lazily only when wrap-around occurs.
            if stamp == 255:
                seen = bytearray(self.maxvar + 1)
                stamp = 1
            deps: set[int] = set()
            stack = [lit_var(self.next_lits[index])]
            while stack:
                var = stack.pop()
                if var == 0 or seen[var] == stamp:
                    continue
                seen[var] = stamp
                if latch_begin <= var <= latch_end:
                    deps.add(var - latch_begin)
                elif self.is_gate(var):
                    stack.append(lit_var(self.left[var]))
                    stack.append(lit_var(self.right[var]))
            lengths.append(len(deps))
            if index in deps:
                self_loops += 1
        return (sum(lengths) / max(1, len(lengths)),
                max(lengths, default=0), self_loops)

    def predecessor_profile(self, starting_latches: Iterable[int], steps: int) -> tuple[list[int], list[int]]:
        """Return exact per-step gate counts and boundary latch counts.

        A level contains the combinational cone of the successor functions of
        the latch boundary from the previous level.  It is the COI required by
        a bounded predecessor/BMC query, and deliberately does not claim to
        be a sound unbounded PDR abstraction.
        """
        latch_begin = self.inputs + 1
        latch_end = self.inputs + self.latches
        frontier = {var for var in starting_latches if latch_begin <= var <= latch_end}
        gate_counts: list[int] = []
        latch_counts: list[int] = []
        for _ in range(steps):
            roots = [self.next_lits[var - latch_begin] for var in frontier]
            cone = self.backward_cone(roots)
            gates, _, latches = counts(cone, self)
            gate_counts.append(gates)
            latch_counts.append(latches)
            frontier = {var for var in range(latch_begin, latch_end + 1) if cone[var]}
        return gate_counts, latch_counts

    def property_state_closure(self, roots: Iterable[int], max_steps: int) -> tuple[set[int], int, bool]:
        """Compute the latch fixed point of property, constraints, and Init."""
        latch_begin = self.inputs + 1
        latch_end = self.inputs + self.latches
        root_cone = self.backward_cone(roots)
        known = {var for var in range(latch_begin, latch_end + 1) if root_cone[var]}
        frontier = set(known)
        rounds = 0
        while frontier and rounds < max_steps:
            rounds += 1
            step_roots = [self.next_lits[var - latch_begin] for var in frontier]
            # A non-constant AIGER reset function can make an otherwise
            # irrelevant latch observable at time zero, so it belongs to the
            # exact slice as well.
            step_roots.extend(
                init for var in frontier
                if (init := self.latch_init_lits[var - latch_begin]) is not None
            )
            cone = self.backward_cone(step_roots)
            discovered = {
                var for var in range(latch_begin, latch_end + 1)
                if cone[var] and var not in known
            }
            known.update(discovered)
            frontier = discovered
        return known, rounds, not frontier

    def closed_property_state_cone(self, roots: Iterable[int], max_steps: int) -> tuple[int, int, int, int, bool]:
        """Compute a transition-closed latch cone for property and constraints.

        Once this fixed point is reached, excluded latch values cannot affect a
        future property/constraint value.  Such a closure is a candidate for a
        sound PDR state slice, unlike a bounded BMC cone.
        """
        latch_begin = self.inputs + 1
        root_list = list(roots)
        known, rounds, stable = self.property_state_closure(root_list, max_steps)
        # Include the property and constraints themselves, not only successor
        # functions.  This is the exact gate set emitted by the slicer.
        closure_roots = root_list + [self.next_lits[var - latch_begin] for var in known]
        closure_roots.extend(
            init for var in known
            if (init := self.latch_init_lits[var - latch_begin]) is not None
        )
        closure = self.backward_cone(closure_roots)
        gates, inputs, _ = counts(closure, self)
        return len(known), gates, inputs, rounds, stable


class BinaryAig(Aag):
    """Read a binary AIGER file without expanding its AND section to ASCII."""

    def __init__(self, path: Path) -> None:
        with path.open("rb") as source:
            header = source.readline().decode("ascii").split()
            if not header or header[0] != "aig" or len(header) < 6:
                raise ValueError(f"expected binary AIGER file: {path}")
            values = [int(value) for value in header[1:]]
            (self.maxvar, self.inputs, self.latches, self.outputs, self.ands) = values[:5]
            self.bads = values[5] if len(values) > 5 else 0
            self.constraints = values[6] if len(values) > 6 else 0
            self.justice = values[7] if len(values) > 7 else 0
            self.fairness = values[8] if len(values) > 8 else 0

            self.latch_lits = [
                2 * (self.inputs + index + 1) for index in range(self.latches)
            ]
            self.next_lits = []
            self.latch_init_lits = []
            for _ in range(self.latches):
                fields = source.readline().split()
                if not fields:
                    raise ValueError(f"truncated latch section: {path}")
                self.next_lits.append(int(fields[0]))
                self.latch_init_lits.append(int(fields[1]) if len(fields) > 1 else None)
            self.output_lits = [int(source.readline()) for _ in range(self.outputs)]
            self.bad_lits = [int(source.readline()) for _ in range(self.bads)]
            self.constraint_lits = [int(source.readline()) for _ in range(self.constraints)]
            justice_sizes = [int(source.readline()) for _ in range(self.justice)]
            for _ in range(sum(justice_sizes) + self.fairness):
                source.readline()

            self.left = array("I", [0]) * (self.maxvar + 1)
            self.right = array("I", [0]) * (self.maxvar + 1)

            def decode_delta() -> int:
                value = 0
                shift = 0
                while True:
                    byte = source.read(1)
                    if not byte:
                        raise ValueError(f"truncated AND section: {path}")
                    number = byte[0]
                    value |= (number & 0x7F) << shift
                    if number < 0x80:
                        return value
                    shift += 7

            for index in range(self.ands):
                lhs = 2 * (self.inputs + self.latches + index + 1)
                rhs0 = lhs - decode_delta()
                rhs1 = rhs0 - decode_delta()
                variable = lit_var(lhs)
                self.left[variable] = rhs0
                self.right[variable] = rhs1


def counts(mask: bytearray, aig: Aag) -> tuple[int, int, int]:
    gate = sum(mask[aig.gate_start:])
    inp = sum(mask[1:aig.inputs + 1])
    latch = sum(mask[aig.inputs + 1:aig.inputs + aig.latches + 1])
    return gate, inp, latch


def masked_roots(mask: bytearray, aig: Aag) -> Counter[str]:
    kinds: Counter[str] = Counter()
    for var in range(aig.gate_start, aig.maxvar + 1):
        if not mask[var]:
            continue
        if aig.is_xor(var):
            kinds["xor"] += 1
        if aig.is_mux(var):
            kinds["mux"] += 1
    return kinds


def analyze(name: str, aig_path: Path, converter: Path, sample_next: int,
            unroll_depth: int, closure_steps: int) -> dict[str, object]:
    temp_path: Path | None = None
    try:
        if aig_path.suffix == ".aag":
            aag_path = aig_path
        else:
            handle, temp_name = tempfile.mkstemp(prefix="pdr-structure-", suffix=".aag")
            os.close(handle)
            temp_path = Path(temp_name)
            subprocess.run([str(converter), str(aig_path), str(temp_path)], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            aag_path = temp_path
        aig = Aag(aag_path)
        bad_roots = aig.bad_lits or aig.output_lits
        bad = aig.backward_cone(bad_roots)
        nxt = aig.backward_cone(aig.next_lits)
        shared = bytearray(a & b for a, b in zip(bad, nxt))
        # PDR predecessor queries constrain Bad(s'), not merely Bad(s).  The
        # successor functions of latches occurring in the bad cone are a cheap
        # exact proxy when the property is a monitor latch (the common case).
        bad_latch_begin = aig.inputs + 1
        bad_latch_end = aig.inputs + aig.latches
        bad_latch_next_roots = [
            aig.next_lits[var - bad_latch_begin]
            for var in range(bad_latch_begin, bad_latch_end + 1)
            if bad[var]
        ]
        bad_latch_next = aig.backward_cone(bad_latch_next_roots)
        bad_latch_vars = [var for var in range(bad_latch_begin, bad_latch_end + 1) if bad[var]]
        depth = aig.depths()
        bad_gates, bad_inputs, bad_latches = counts(bad, aig)
        next_gates, next_inputs, next_latches = counts(nxt, aig)
        shared_gates, shared_inputs, shared_latches = counts(shared, aig)
        bad_next_gates, bad_next_inputs, bad_next_latches = counts(bad_latch_next, aig)
        all_xor = masked_roots(bytearray(b"\x01") * (aig.maxvar + 1), aig)
        bad_kinds = masked_roots(bad, aig)
        bad_next_kinds = masked_roots(bad_latch_next, aig)
        next_kinds = masked_roots(nxt, aig)
        shared_kinds = masked_roots(shared, aig)
        avg_deps, max_deps, self_loops = aig.sampled_latch_dependencies(sample_next)
        predecessor_gates, predecessor_latches = aig.predecessor_profile(
            bad_latch_vars, unroll_depth)
        closure_latches, closure_gates, closure_inputs, closure_rounds, closure_stable = (
            aig.closed_property_state_cone(
                list(bad_roots) + aig.constraint_lits, closure_steps))
        root_depth = [depth[lit_var(root)] for root in bad_roots]
        next_depth = [depth[lit_var(root)] for root in aig.next_lits]
        return {
            "model_id": name,
            "path": str(aig_path),
            "inputs": aig.inputs, "latches": aig.latches, "ands": aig.ands,
            "bad_roots": len(bad_roots),
            "bad_gates": bad_gates, "bad_inputs": bad_inputs, "bad_latches": bad_latches,
            "bad_depth_max": max(root_depth, default=0),
            "bad_latch_next_gates": bad_next_gates,
            "bad_latch_next_inputs": bad_next_inputs,
            "bad_latch_next_latches": bad_next_latches,
            "bad_latch_next_xor": bad_next_kinds["xor"],
            "bad_latch_next_mux": bad_next_kinds["mux"],
            "bad_latch_next_gate_fraction": round(bad_next_gates / max(1, aig.ands), 6),
            "next_gates": next_gates, "next_inputs": next_inputs, "next_latches": next_latches,
            "next_depth_max": max(next_depth, default=0),
            "next_depth_mean": round(sum(next_depth) / max(1, len(next_depth)), 3),
            "shared_gates": shared_gates, "shared_inputs": shared_inputs,
            "shared_latches": shared_latches,
            "bad_next_gate_jaccard": round(shared_gates / max(1, bad_gates + next_gates - shared_gates), 6),
            "bad_next_latch_jaccard": round(shared_latches / max(1, bad_latches + next_latches - shared_latches), 6),
            "xor_all": all_xor["xor"], "xor_bad": bad_kinds["xor"],
            "xor_next": next_kinds["xor"], "xor_shared": shared_kinds["xor"],
            "mux_all": all_xor["mux"], "mux_bad": bad_kinds["mux"],
            "mux_next": next_kinds["mux"], "mux_shared": shared_kinds["mux"],
            "sampled_next": min(sample_next, aig.latches),
            "sampled_latch_dependencies_mean": round(avg_deps, 3),
            "sampled_latch_dependencies_max": max_deps,
            "sampled_next_self_loops": self_loops,
            "bad_preimage_step_gates": ",".join(map(str, predecessor_gates)),
            "bad_preimage_step_latches": ",".join(map(str, predecessor_latches)),
            "property_closure_latches": closure_latches,
            "property_closure_latch_fraction": round(closure_latches / max(1, aig.latches), 6),
            "property_closure_gates": closure_gates,
            "property_closure_gate_fraction": round(closure_gates / max(1, aig.ands), 6),
            "property_closure_inputs": closure_inputs,
            "property_closure_rounds": closure_rounds,
            "property_closure_stable": int(closure_stable),
        }
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def model_items(args: argparse.Namespace) -> list[tuple[str, Path]]:
    items = [(path.stem, path) for path in args.aig]
    if args.manifest:
        document = json.loads(args.manifest.read_text(encoding="utf-8"))
        models = document["models"] if isinstance(document, dict) else document
        items.extend((model.get("id", Path(model["path"]).stem), Path(model["path"]))
                     for model in models)
    return items


def main() -> int:
    args = parse_args()
    items = model_items(args)
    if not items:
        raise SystemExit("provide --manifest or at least one --aig")
    rows = []
    for index, (name, path) in enumerate(items, 1):
        try:
            row = analyze(name, path, args.converter, args.sample_next,
                          args.unroll_depth, args.closure_steps)
            row["error"] = ""
        except Exception as error:  # Keep a batch analysis useful after one malformed input.
            row = {"model_id": name, "path": str(path), "error": str(error)}
        rows.append(row)
        print(f"[{index}/{len(items)}] {name}: {row.get('error') or 'ok'}", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with args.output.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
