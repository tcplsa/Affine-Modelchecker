#!/usr/bin/env python3
"""Write an exact property/constraint state-cone slice of one AIGER model.

The result preserves all inputs, the selected state latches, their Init values,
Bad, and constraints.  A latch is retained until the set is closed under its
next-state and reset-function dependencies.  Therefore this is suitable for
ordinary unbounded PDR, unlike a bounded preimage/BMC slice.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "aig_deep_structure", HERE / "analyze_aig_deep_structure.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load analyze_aig_deep_structure.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
Aag = MODULE.Aag
lit_var = MODULE.lit_var


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--converter", type=Path,
                        default=Path("/home/wudl/Modelchecker-bidirectional/modelchecker/aigtoaig"))
    parser.add_argument("--closure-steps", type=int, default=256)
    return parser.parse_args()


def read_aag(path: Path, converter: Path) -> tuple[object, Path | None]:
    if path.suffix == ".aag":
        return Aag(path), None
    fd, name = tempfile.mkstemp(prefix="pdr-state-slice-", suffix=".aag")
    os.close(fd)
    temporary = Path(name)
    subprocess.run([str(converter), str(path), str(temporary)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    return Aag(temporary), temporary


def main() -> int:
    args = parse_args()
    aig, temporary = read_aag(args.input, args.converter)
    try:
        roots = list(aig.bad_lits or aig.output_lits) + list(aig.constraint_lits)
        if not roots:
            raise ValueError("model has no bad/output property")
        selected, rounds, stable = aig.property_state_closure(roots, args.closure_steps)
        if not stable:
            raise RuntimeError(
                f"state closure did not stabilize within {args.closure_steps} rounds")

        latch_begin = aig.inputs + 1
        selected_latches = sorted(selected)
        selected_next = [aig.next_lits[var - latch_begin] for var in selected_latches]
        selected_init = [aig.latch_init_lits[var - latch_begin] for var in selected_latches]
        required_roots = roots + selected_next + [init for init in selected_init if init is not None]
        cone = aig.backward_cone(required_roots)
        selected_gates = [var for var in range(aig.gate_start, aig.maxvar + 1) if cone[var]]

        mapping: dict[int, int] = {var: var for var in range(1, aig.inputs + 1)}
        for index, var in enumerate(selected_latches, 1):
            mapping[var] = aig.inputs + index
        for index, var in enumerate(selected_gates, 1):
            mapping[var] = aig.inputs + len(selected_latches) + index

        def remap(literal: int) -> int:
            var = lit_var(literal)
            if var == 0:
                return literal
            if var not in mapping:
                raise RuntimeError(f"slice is not closed: missing variable {var}")
            return (mapping[var] << 1) | (literal & 1)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="ascii") as target:
            maxvar = aig.inputs + len(selected_latches) + len(selected_gates)
            target.write(
                f"aag {maxvar} {aig.inputs} {len(selected_latches)} 0 {len(selected_gates)} "
                f"{len(aig.bad_lits)} {len(aig.constraint_lits)}\n")
            for var in range(1, aig.inputs + 1):
                target.write(f"{var << 1}\n")
            for new_index, (old_var, next_lit, init_lit) in enumerate(
                zip(selected_latches, selected_next, selected_init), 1):
                current = (aig.inputs + new_index) << 1
                line = f"{current} {remap(next_lit)}"
                if init_lit is not None:
                    line += f" {remap(init_lit)}"
                target.write(line + "\n")
            for literal in aig.bad_lits:
                target.write(f"{remap(literal)}\n")
            for literal in aig.constraint_lits:
                target.write(f"{remap(literal)}\n")
            for old_var in selected_gates:
                target.write(
                    f"{mapping[old_var] << 1} {remap(aig.left[old_var])} "
                    f"{remap(aig.right[old_var])}\n")
            target.write("c\n")
            target.write(
                "property/constraint state-cone slice; "
                f"latches={len(selected_latches)}/{aig.latches}; "
                f"ands={len(selected_gates)}/{aig.ands}; closure_rounds={rounds}\n")
        print(
            f"slice={args.output} latches={len(selected_latches)}/{aig.latches} "
            f"ands={len(selected_gates)}/{aig.ands} rounds={rounds}")
        return 0
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
