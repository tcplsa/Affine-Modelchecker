#!/usr/bin/env python3
"""Independently validate an MC PDR invariant with native XOR reasoning.

The trusted input is the original ASCII AAG plus an optional
``mc-pdr-invariant-v1`` file.  The checker does not call MC or its PDR code.  It
encodes the original AND network as CNF, independently recognizes canonical
two-input XOR patterns, validates those equations against the AND encoding,
and then asks CryptoMiniSat to prove initiation and one-step consecution.

The invariant represented by an MC export is ``not bad`` conjoined with the
negations of all exported blocked cubes.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SAT = 10
UNSAT = 20


@dataclass(frozen=True)
class Aag:
    maxvar: int
    inputs: tuple[int, ...]
    latches: tuple[tuple[int, int, int], ...]
    outputs: tuple[int, ...]
    bads: tuple[int, ...]
    constraints: tuple[int, ...]
    ands: dict[int, tuple[int, int]]


def parse_aag(path: Path) -> Aag:
    lines = path.read_text(encoding="ascii").splitlines()
    if not lines:
        raise ValueError("empty AAG")
    header = lines[0].split()
    if header[0] != "aag":
        raise ValueError("only ASCII AAG input is supported")
    values = [int(value) for value in header[1:]]
    if len(values) < 5:
        raise ValueError("malformed AAG header")
    maximum, ni, nl, no, na = values[:5]
    nb = values[5] if len(values) > 5 else 0
    nc = values[6] if len(values) > 6 else 0
    nj = values[7] if len(values) > 7 else 0
    nf = values[8] if len(values) > 8 else 0

    cursor = 1
    inputs = tuple(int(lines[cursor + index]) for index in range(ni))
    cursor += ni
    latches = []
    for _ in range(nl):
        fields = [int(value) for value in lines[cursor].split()]
        cursor += 1
        if len(fields) < 2:
            raise ValueError("malformed latch line")
        current, nxt = fields[:2]
        initial = fields[2] if len(fields) > 2 else 0
        latches.append((current, nxt, initial))
    outputs = tuple(int(lines[cursor + index]) for index in range(no))
    cursor += no
    bads = tuple(int(lines[cursor + index]) for index in range(nb))
    cursor += nb
    constraints = tuple(int(lines[cursor + index]) for index in range(nc))
    cursor += nc
    justice_sizes = [int(lines[cursor + index]) for index in range(nj)]
    cursor += nj + sum(justice_sizes)
    cursor += nf
    ands: dict[int, tuple[int, int]] = {}
    for _ in range(na):
        output, left, right = (int(value) for value in lines[cursor].split())
        cursor += 1
        if output & 1 or output // 2 in ands:
            raise ValueError("malformed or duplicate AND output")
        ands[output // 2] = (left, right)
    return Aag(
        maximum,
        inputs,
        tuple(latches),
        outputs,
        bads,
        constraints,
        ands,
    )


def parse_invariant(path: Path | None, latch_count: int) -> list[tuple[int, ...]]:
    if path is None:
        return []
    lines = path.read_text(encoding="ascii").splitlines()
    if not lines:
        raise ValueError("empty invariant file")
    header = lines[0].split()
    if header != ["mc-pdr-invariant-v1", str(latch_count)]:
        raise ValueError("invariant header or latch count mismatch")
    cubes: set[tuple[int, ...]] = set()
    for line_number, line in enumerate(lines[1:], 2):
        stripped = line.strip()
        if not stripped or stripped.startswith(("c", "#")):
            continue
        fields = [int(value) for value in stripped.split()]
        if not fields or fields[-1] != 0 or 0 in fields[:-1]:
            raise ValueError(f"malformed invariant line {line_number}")
        cube = tuple(sorted(fields[:-1], key=lambda value: (abs(value), value < 0)))
        if not cube or any(abs(value) > latch_count for value in cube):
            raise ValueError(f"out-of-range invariant line {line_number}")
        if any(-value in cube for value in cube):
            raise ValueError(f"contradictory blocked cube on line {line_number}")
        cubes.add(cube)
    return sorted(cubes)


class Cmsat:
    def __init__(self, library: Path, seed: int = 1):
        self.library_path = library
        self.lib = ctypes.CDLL(str(library))
        self._bind()
        self.handle = self.lib.cmsat_create()
        if not self.handle:
            raise RuntimeError("cmsat_create failed")
        self.lib.cmsat_set_seed(self.handle, seed)
        self.lib.cmsat_enable_gauss(self.handle)
        self.maximum = 0
        self.clauses = 0
        self.xors = 0

    def _bind(self) -> None:
        pointer = ctypes.c_void_p
        integer_pointer = ctypes.POINTER(ctypes.c_int)
        self.lib.cmsat_create.restype = pointer
        self.lib.cmsat_destroy.argtypes = [pointer]
        self.lib.cmsat_add_clause.argtypes = [pointer, integer_pointer, ctypes.c_int]
        self.lib.cmsat_add_clause.restype = ctypes.c_bool
        self.lib.cmsat_add_xor_clause_lits.argtypes = [
            pointer,
            integer_pointer,
            ctypes.c_int,
            ctypes.c_bool,
        ]
        self.lib.cmsat_add_xor_clause_lits.restype = ctypes.c_bool
        self.lib.cmsat_solve_with_assumptions.argtypes = [
            pointer,
            integer_pointer,
            ctypes.c_int,
        ]
        self.lib.cmsat_solve_with_assumptions.restype = ctypes.c_int
        self.lib.cmsat_set_seed.argtypes = [pointer, ctypes.c_uint]
        self.lib.cmsat_enable_gauss.argtypes = [pointer]
        self.lib.cmsat_get_last_conflicts.argtypes = [pointer]
        self.lib.cmsat_get_last_conflicts.restype = ctypes.c_uint64
        self.lib.cmsat_get_last_decisions.argtypes = [pointer]
        self.lib.cmsat_get_last_decisions.restype = ctypes.c_uint64
        self.lib.cmsat_get_last_propagations.argtypes = [pointer]
        self.lib.cmsat_get_last_propagations.restype = ctypes.c_uint64

    def close(self) -> None:
        if getattr(self, "handle", None):
            self.lib.cmsat_destroy(self.handle)
            self.handle = None

    def __enter__(self) -> "Cmsat":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    @staticmethod
    def _array(values: list[int]) -> tuple[object, int]:
        if not values:
            return ctypes.POINTER(ctypes.c_int)(), 0
        array = (ctypes.c_int * len(values))(*values)
        return array, len(values)

    def fresh(self) -> int:
        self.maximum += 1
        return self.maximum

    def observe(self, literals: Iterable[int]) -> None:
        for literal in literals:
            self.maximum = max(self.maximum, abs(literal))

    def add_clause(self, literals: Iterable[int | bool]) -> None:
        clause: list[int] = []
        seen: set[int] = set()
        for literal in literals:
            if literal is True:
                return
            if literal is False:
                continue
            value = int(literal)
            if -value in seen:
                return
            if value not in seen:
                seen.add(value)
                clause.append(value)
        self.observe(clause)
        array, length = self._array(clause)
        if not self.lib.cmsat_add_clause(self.handle, array, length):
            # An empty clause or immediate contradiction is a valid formula
            # state. CryptoMiniSat reports it through this return value.
            pass
        self.clauses += 1

    def add_xor(self, variables: Iterable[int], rhs: bool) -> None:
        parity: set[int] = set()
        for variable in variables:
            if variable <= 0:
                raise ValueError("XOR variables must be positive")
            if variable in parity:
                parity.remove(variable)
            else:
                parity.add(variable)
        ordered = sorted(parity)
        if not ordered:
            if rhs:
                self.add_clause([])
            return
        self.observe(ordered)
        array, length = self._array(ordered)
        self.lib.cmsat_add_xor_clause_lits(self.handle, array, length, rhs)
        self.xors += 1

    def add_xor_literals(self, literals: Iterable[int], rhs: bool = False) -> None:
        variables = []
        adjusted = rhs
        for literal in literals:
            if literal == 0:
                continue
            if literal < 0:
                adjusted = not adjusted
            variables.append(abs(literal))
        self.add_xor(variables, adjusted)

    def solve(self, assumptions: Iterable[int] = ()) -> tuple[int, dict[str, int | float]]:
        values = list(assumptions)
        self.observe(values)
        array, length = self._array(values)
        started = time.monotonic()
        result = self.lib.cmsat_solve_with_assumptions(self.handle, array, length)
        elapsed = time.monotonic() - started
        return result, {
            "seconds": elapsed,
            "conflicts": int(self.lib.cmsat_get_last_conflicts(self.handle)),
            "decisions": int(self.lib.cmsat_get_last_decisions(self.handle)),
            "propagations": int(self.lib.cmsat_get_last_propagations(self.handle)),
        }


def aig_literal(literal: int) -> int | bool:
    if literal == 0:
        return False
    if literal == 1:
        return True
    variable = literal // 2
    return -variable if literal & 1 else variable


def negate(literal: int | bool) -> int | bool:
    if isinstance(literal, bool):
        return not literal
    return -literal


def add_and(solver: Cmsat, output: int, left: int | bool, right: int | bool) -> None:
    solver.add_clause([-output, left])
    solver.add_clause([-output, right])
    solver.add_clause([output, negate(left), negate(right)])


def add_equivalence(solver: Cmsat, output: int, value: int | bool) -> None:
    solver.add_clause([-output, value])
    solver.add_clause([output, negate(value)])


def recognize_xors(aag: Aag) -> dict[int, tuple[int, int]]:
    """Recognize the exact canonical AIG patterns used by aig2xag."""

    found: dict[int, tuple[int, int]] = {}
    for output, (outer_left, outer_right) in aag.ands.items():
        if not (outer_left & 1 and outer_right & 1):
            continue
        first = aag.ands.get(outer_left // 2)
        second = aag.ands.get(outer_right // 2)
        if first is None or second is None:
            continue
        first = tuple(sorted(first, key=lambda literal: literal // 2))
        second = tuple(sorted(second, key=lambda literal: literal // 2))
        if tuple(literal // 2 for literal in first) != tuple(
            literal // 2 for literal in second
        ):
            continue
        signs = tuple(bool(literal & 1) for literal in first + second)
        if signs in ((True, True, False, False), (False, False, True, True)):
            found[output] = (first[0] & ~1, first[1] & ~1)
        elif signs in ((False, True, True, False), (True, False, False, True)):
            found[output] = (first[0] & ~1, first[1] | 1)
    return found


def affine_expressions(
    aag: Aag, xors: dict[int, tuple[int, int]]
) -> dict[int, tuple[frozenset[int], bool]]:
    expressions: dict[int, tuple[frozenset[int], bool]] = {0: (frozenset(), False)}
    for literal in aag.inputs:
        expressions[literal // 2] = (frozenset((literal // 2,)), False)
    for current, _nxt, _initial in aag.latches:
        expressions[current // 2] = (frozenset((current // 2,)), False)
    for output in sorted(xors):
        left, right = xors[output]
        left_expression = expressions.get(left // 2)
        right_expression = expressions.get(right // 2)
        if left_expression is None or right_expression is None:
            continue
        support = left_expression[0] ^ right_expression[0]
        rhs = left_expression[1] ^ bool(left & 1) ^ right_expression[1] ^ bool(right & 1)
        expressions[output] = (support, rhs)
    return expressions


def encode_original(solver: Cmsat, aag: Aag, xors: dict[int, tuple[int, int]]) -> None:
    solver.maximum = max(solver.maximum, aag.maxvar)
    for output, (left, right) in aag.ands.items():
        add_and(solver, output, aig_literal(left), aig_literal(right))
    for output, (left, right) in xors.items():
        solver.add_xor_literals([output, int(aig_literal(left)), int(aig_literal(right))])


def validate_xor_recovery(
    aag: Aag, xors: dict[int, tuple[int, int]]
) -> dict[str, int | float | str]:
    """Exhaustively validate each recognized three-AND XOR pattern.

    This is stronger and cheaper than asking a SAT solver to rediscover the
    local equivalence inside the full circuit.  Every pattern has exactly two
    Boolean leaves, so all four assignments are checked.
    """

    started = time.monotonic()

    def value_of_literal(literal: int, values: dict[int, bool]) -> bool:
        if literal < 2:
            return bool(literal)
        value = values[literal // 2]
        return not value if literal & 1 else value

    for output, (left, right) in xors.items():
        outer = aag.ands[output]
        inner_variables = (outer[0] // 2, outer[1] // 2)
        leaves = sorted({left // 2, right // 2})
        if len(leaves) != 2:
            raise RuntimeError(f"degenerate XOR pattern at variable {output}")
        for assignment in range(4):
            values = {
                leaves[0]: bool(assignment & 1),
                leaves[1]: bool(assignment & 2),
            }
            for inner in inner_variables:
                fanins = aag.ands[inner]
                values[inner] = value_of_literal(fanins[0], values) and value_of_literal(
                    fanins[1], values
                )
            values[output] = value_of_literal(outer[0], values) and value_of_literal(
                outer[1], values
            )
            expected = value_of_literal(left, values) ^ value_of_literal(right, values)
            if values[output] != expected:
                raise RuntimeError(f"XOR truth-table mismatch at variable {output}")
    return {
        "equations": len(xors),
        "assignments_checked": 4 * len(xors),
        "method": "exhaustive-local-truth-table",
        "seconds": time.monotonic() - started,
    }


class NextEncoder:
    def __init__(self, solver: Cmsat, aag: Aag, xors: dict[int, tuple[int, int]]):
        self.solver = solver
        self.aag = aag
        self.xors = xors
        self.memo: dict[int, int] = {}
        self.input_variables = {literal // 2 for literal in aag.inputs}
        self.latch_variables = {
            current // 2: solver.fresh() for current, _nxt, _initial in aag.latches
        }
        self.next_inputs: dict[int, int] = {}

    def map_literal(self, literal: int) -> int | bool:
        if literal < 2:
            return bool(literal)
        variable = literal // 2
        inverted = bool(literal & 1)
        if variable in self.latch_variables:
            mapped = self.latch_variables[variable]
        elif variable in self.input_variables:
            mapped = self.next_inputs.setdefault(variable, self.solver.fresh())
        elif variable in self.memo:
            mapped = self.memo[variable]
        else:
            gate = self.aag.ands.get(variable)
            if gate is None:
                raise ValueError(f"undefined AAG variable {variable}")
            mapped = self.solver.fresh()
            self.memo[variable] = mapped
            left = self.map_literal(gate[0])
            right = self.map_literal(gate[1])
            add_and(self.solver, mapped, left, right)
            xor_gate = self.xors.get(variable)
            if xor_gate is not None:
                xor_left = self.map_literal(xor_gate[0])
                xor_right = self.map_literal(xor_gate[1])
                self.solver.add_xor_literals([mapped, int(xor_left), int(xor_right)])
        return -mapped if inverted else mapped


def add_initial_state(solver: Cmsat, aag: Aag) -> None:
    for current, _nxt, initial in aag.latches:
        variable = current // 2
        if initial == 0:
            solver.add_clause([-variable])
        elif initial == 1:
            solver.add_clause([variable])
        elif initial == current:
            continue
        else:
            raise ValueError("only constant or unknown AIGER latch initialization is supported")


def current_cube(aag: Aag, cube: tuple[int, ...]) -> list[int]:
    variables = [current // 2 for current, _nxt, _initial in aag.latches]
    return [(variables[abs(value) - 1] if value > 0 else -variables[abs(value) - 1]) for value in cube]


def current_invariant_clauses(aag: Aag, cubes: list[tuple[int, ...]]) -> list[list[int]]:
    return [[-literal for literal in current_cube(aag, cube)] for cube in cubes]


def require_unsat(
    solver: Cmsat,
    assumptions: Iterable[int],
    label: str,
    obligations: list[dict[str, object]],
) -> None:
    result, stats = solver.solve(assumptions)
    record: dict[str, object] = {"label": label, "result": result, **stats}
    obligations.append(record)
    if result != UNSAT:
        status = "SAT" if result == SAT else "UNKNOWN"
        raise RuntimeError(f"certificate obligation {label} is {status}, expected UNSAT")


def check_certificate(
    model: Path,
    invariant: Path | None,
    library: Path,
    property_index: int,
    seed: int,
) -> dict[str, object]:
    started = time.monotonic()
    aag = parse_aag(model)
    bads = aag.bads or aag.outputs
    if property_index < 0 or property_index >= len(bads):
        raise ValueError("property index out of range")
    bad = bads[property_index]
    cubes = parse_invariant(invariant, len(aag.latches))
    xors = recognize_xors(aag)
    expressions = affine_expressions(aag, xors)
    xor_validation = validate_xor_recovery(aag, xors)
    obligations: list[dict[str, object]] = []

    # Init => (not bad and every exported blocked-cube clause).
    with Cmsat(library, seed + 1) as initiation:
        encode_original(initiation, aag, xors)
        add_initial_state(initiation, aag)
        for constraint in aag.constraints:
            initiation.add_clause([aig_literal(constraint)])
        require_unsat(initiation, [int(aig_literal(bad))], "init_implies_property", obligations)
        for index, cube in enumerate(cubes):
            require_unsat(
                initiation,
                current_cube(aag, cube),
                f"init_implies_lemma_{index}",
                obligations,
            )

    # I(s) & T(s,i,s') => I(s').
    with Cmsat(library, seed + 2) as consecution:
        encode_original(consecution, aag, xors)
        consecution.add_clause([negate(aig_literal(bad))])
        for clause in current_invariant_clauses(aag, cubes):
            consecution.add_clause(clause)
        for constraint in aag.constraints:
            consecution.add_clause([aig_literal(constraint)])

        nxt = NextEncoder(consecution, aag, xors)
        affine_summaries = 0
        for current, next_literal, _initial in aag.latches:
            prime = nxt.latch_variables[current // 2]
            add_equivalence(consecution, prime, aig_literal(next_literal))
            expression = expressions.get(next_literal // 2)
            if expression is not None:
                support, rhs = expression
                consecution.add_xor(
                    [prime, *support], rhs ^ bool(next_literal & 1)
                )
                affine_summaries += 1

        next_bad = nxt.map_literal(bad)
        for constraint in aag.constraints:
            consecution.add_clause([nxt.map_literal(constraint)])
        require_unsat(
            consecution,
            [int(next_bad)],
            "invariant_implies_next_property",
            obligations,
        )
        for index, cube in enumerate(cubes):
            assumptions = []
            for literal in cube:
                current = aag.latches[abs(literal) - 1][0] // 2
                prime = nxt.latch_variables[current]
                assumptions.append(prime if literal > 0 else -prime)
            require_unsat(
                consecution,
                assumptions,
                f"invariant_implies_next_lemma_{index}",
                obligations,
            )

    return {
        "schema": "affine-pdr-independent-certificate-v1",
        "model": str(model),
        "invariant": str(invariant) if invariant is not None else None,
        "property_index": property_index,
        "latches": len(aag.latches),
        "ands": len(aag.ands),
        "recognized_xors": len(xors),
        "affine_next_equations": affine_summaries,
        "blocked_cubes": len(cubes),
        "xor_validation": xor_validation,
        "obligations": obligations,
        "total_seconds": time.monotonic() - started,
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path)
    parser.add_argument("--invariant", type=Path)
    parser.add_argument("--cmsat-wrapper", type=Path, required=True)
    parser.add_argument("--property-index", type=int, default=0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    result = check_certificate(
        args.model,
        args.invariant,
        args.cmsat_wrapper,
        args.property_index,
        args.seed,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.json is not None:
        args.json.write_text(rendered + "\n", encoding="utf-8")
    print(
        f"PASS\t{args.model}\txors={result['recognized_xors']}"
        f"\taffine_next={result['affine_next_equations']}"
        f"\tseconds={result['total_seconds']:.6f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
