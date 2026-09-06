"""AAG (ASCII AIGER) exporter for Path B netlists.

AAG header:  aag M I L O A [B C] [J F]
  M = maximum variable index
  I = number of inputs
  L = number of latches
  O = number of outputs (regular)
  A = number of AND gates
  B = number of bad-state outputs
  C = number of constraints

Token order (AIGER spec):
  inputs (I lines)
  latches (L lines: cur next)
  outputs (O lines)
  bad outputs (B lines)
  constraint outputs (C lines)
  AND gates (A lines: out a b)

The netlist's xor/or gates are lowered to AIG AND structure here:
  xor:   (a ^ b)  = ~(a&b) & ~(~a & ~b)  -- but a compact 3-AND form:
         t0 = ~(a & b)   [nand]
         t1 = a | b      = ~(~a & ~b)
         out = t0 & t1
  or:    a | b          = ~(~a & ~b)
  not:   ~a              = handled via literal polarity.

Inverters are represented by odd literal polarity (AIGER convention), so no
explicit NOT AND-gates are needed.

AAG literal convention:
  variable v >= 1  -> literal 2*v
  negated variable -> literal 2*v+1
  literal 0 = constant false; literal 1 = constant true.
"""

from __future__ import annotations

from .netlist import CONST_0, CONST_1, Netlist


class _Lit:
    """Mutable literal counter for AAG variables."""

    def __init__(self):
        self.count = 0  # number of AIGER variables allocated

    def new_var(self) -> int:
        self.count += 1
        return self.count


def _lit_encode(var: int, neg: bool) -> int:
    """Encode (var, neg) as an AAG literal."""
    return 2 * var + (1 if neg else 0)


def _to_aag_lit(sig: int) -> int:
    """Convert a netlist fanin literal to an AAG literal.

    Netlist convention: positive id -> signal var = id; negative -> negated.
    id 0 -> literal 0 (constant false); -0 cannot exist.
    """
    if sig == 0:
        return 0
    if sig > 0:
        return 2 * sig          # var = sig, positive
    return 2 * (-sig) + 1      # var = -sig, negated


def _lower_and(a_lit: int, b_lit: int, v: _Lit) -> int:
    """Create an AIG AND gate from two AAG literals, returns its literal.

    The netlist's gate *output* is a signal id, but since inverters are
    polarity-encoded, an AND's output literal is always positive (2*var).
    """
    var = v.new_var()
    lit = _lit_encode(var, neg=False)
    return lit, a_lit, b_lit


def to_aag_text(net: Netlist, name="top") -> str:
    """Serialize a netlist to AAG text (returns string)."""
    v = _Lit()
    # ---- allocate variable ids ----
    # primary inputs: vars 1..I
    input_vars = {}   # netlist input id -> AIGER var
    for nid in net.inputs:
        var = v.new_var()
        input_vars[nid] = var
    # latches: current-state vars, in order
    latch_vars = []   # (name, cur_var, next_lit, init_value)
    for name, cur, init_value, next_lit in net.latches:
        var = v.new_var()
        latch_vars.append((name, var, next_lit, init_value))
    # AND gates: allocated on the fly in topological order
    lowered = []      # list of (out_lit, a_lit, b_lit) for AND-only output
    # maps netlist signal id -> AAG literal (positive-polarity literal; i.e.
    # the literal for the unnegated signal).  Netlist ids are NOT AAG var ids.
    gate_out_lit = {}

    def resolve_lit(sig: int) -> int:
        """Map a netlist fanin literal to an AAG literal."""
        if sig == 0:
            return 0
        if sig > 0:
            return gate_out_lit[sig]
        return gate_out_lit[-sig] ^ 1

    # pre-map inputs and latch current signals
    for nid, var in input_vars.items():
        gate_out_lit[nid] = _lit_encode(var, neg=False)

    # Build a cur-id -> var map for latches
    for (name, cur, _n, _i), (name2, var, n, i) in zip(net.latches, latch_vars):
        gate_out_lit[cur] = _lit_encode(var, neg=False)

    # Now lower gates in stored (topological) order.
    for g in net.gates:
        kind = g[0]
        if kind == 'not':
            _, out, a = g
            # out = ~a  -> represent by flipping polarity of the fanin literal.
            # AAG has no NOT gates; inversion is polarity (low bit). This also
            # maps constant 0<->1 correctly (lit 0 ^ 1 == 1, lit 1 ^ 1 == 0).
            a_lit = resolve_lit(a)
            gate_out_lit[out] = a_lit ^ 1
            continue
        _, out, a, b = g
        a_lit = resolve_lit(a)
        b_lit = resolve_lit(b)

        def emit_and(aa, bb):
            """Fold constants then emit an AIG AND; returns output literal."""
            # constant folding
            if aa == 0 or bb == 0:
                return 0
            if aa == 1:
                return bb
            if bb == 1:
                return aa
            olit, la, lb = _lower_and(aa, bb, v)
            lowered.append((olit, la, lb))
            return olit

        if kind == 'and':
            gate_out_lit[out] = emit_and(a_lit, b_lit)
        elif kind == 'xor':
            # out = a ^ b = (a|b) & ~(a&b)
            t1 = emit_and(a_lit, b_lit)          # a&b
            t1n = t1 ^ 1                         # ~(a&b)
            t2 = emit_and(a_lit ^ 1, b_lit ^ 1)  # (~a)&(~b)
            t2n = t2 ^ 1                         # a|b
            gate_out_lit[out] = emit_and(t1n, t2n)
        elif kind == 'or':
            t = emit_and(a_lit ^ 1, b_lit ^ 1)   # (~a)&(~b)
            gate_out_lit[out] = t ^ 1
        else:
            raise ValueError(f"unknown gate kind {kind}")

    # ---- resolve final literals for outputs / bad / constraints ----
    def final_lit(sig: int) -> int:
        if sig == 0:
            return 0
        if sig > 0:
            return gate_out_lit[sig]
        return gate_out_lit[-sig] ^ 1

    out_lits = [final_lit(s) for s in net.outputs]
    bad_lits = [final_lit(s) for s in net.bad]
    con_lits = [final_lit(s) for s in net.constraints]
    # latch next literals
    latch_next = []
    for _name, _cur, _init, next_lit in net.latches:
        latch_next.append(final_lit(next_lit))

    M = v.count
    I = len(net.inputs)
    L = len(net.latches)
    O = len(net.outputs)
    A = len(lowered)
    B = len(net.bad)
    C = len(net.constraints)

    lines = []
    header = f"aag {M} {I} {L} {O} {A}"
    if B or C:
        header += f" {B} {C}"
    lines.append(header)

    # inputs: literal 2*var (positive)
    for nid in net.inputs:
        lines.append(str(_lit_encode(input_vars[nid], neg=False)))

    # latches: "cur next reset"  (reset literal = 0 for init 0, 1 for init 1;
    # AIGER spec: reset 0/1 gives a fixed init value, matching rIC3's aiger-rs
    # parser which reads `init = Some(reset)` when reset.var != cur.var).
    for (name, cur, init_value, _n), (name2, var, _n2, init_val) in zip(net.latches, latch_vars):
        cur_lit = _lit_encode(var, neg=False)
        reset_lit = 1 if init_value else 0
        lines.append(f"{cur_lit} {latch_next.pop(0)} {reset_lit}")

    for l in out_lits:
        lines.append(str(l))
    for l in bad_lits:
        lines.append(str(l))
    for l in con_lits:
        lines.append(str(l))
    for (out_lit, a, b) in lowered:
        lines.append(f"{out_lit} {a} {b}")

    return "\n".join(lines) + "\n"


def write_aag(net: Netlist, path: str, name="top") -> None:
    with open(path, "w") as f:
        f.write(to_aag_text(net, name))
