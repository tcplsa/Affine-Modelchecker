"""BLIF exporter for Path B netlists (native-XOR-preserving).

BLIF uses .names blocks with truth-table rows.  Two-input gate truth tables
follow the convention consumed by `blif_output._split_names_to_ands_xors`
(and `blif_input.parse_blif_core`), so the downstream blif/CryptoMiniSat PDR
recognizes XOR gates and emits native `add_xor` equations instead of CNF.

Gate encoding (2-input, output column last):

  AND  -> .names a b out      11 1
  XOR  -> .names a b out      01 1 / 10 1      (native-XOR recognized)
  OR   -> .names a b out      1- 1 / -1 1
  NOT  -> .names a out        0 1

Signal polarity is handled by explicit inverter .names blocks (a 1-input
`0 1` row), matching the .names-based parser rather than .gate/.subckt.

Constants:
  _const0 : always 0   (.names _const0 -> row 0, recognized as constraint)
  _const1 : always 1   (.names _const1 -> row 1)

To avoid parser ambiguity, constant-true signals are materialized via a NOT
gate on _const0 (i.e. .names _const0 _c1 / 0 1) only when referenced; a bare
`.names _const1` + `1` row is also accepted by blif_input/Output.
"""

from __future__ import annotations

from .netlist import Netlist

_ID_COUNTER = 0


def _sig_name(nid: int) -> str:
    """Netlist signal id -> BLIF signal name."""
    if nid == 0:
        return "_const0"
    return f"s{nid}"


def _inv_name(base: str) -> str:
    global _ID_COUNTER
    _ID_COUNTER += 1
    return f"inv{_ID_COUNTER}_{base}"


def to_blif_text(net: Netlist, name="top") -> str:
    global _ID_COUNTER
    _ID_COUNTER = 0  # deterministic across calls
    out = []
    out.append(f".model {name}")
    in_names = [_sig_name(nid) for nid in net.inputs]
    if in_names:
        out.append(".inputs " + " ".join(in_names))
    # ordinary outputs then bad outputs; constraints stay as .names constraints
    out_names = [f"out{i}" for i in range(len(net.outputs))]
    bad_names = [f"bad{i}" for i in range(len(net.bad))]
    all_outs = out_names + bad_names
    if all_outs:
        out.append(".outputs " + " ".join(all_outs))

    # constants
    out.append(".names _const0\n0")
    out.append(".names _const1\n1")

    # inverters needed by gates (resolve per gate; we emit them inline)
    def emit_gate(kind, a_lit, b_lit, out_name):
        """a_lit/b_lit are netlist literals (0, 1, +id, -id)."""
        def resolve_input(lit):
            if lit == 0:
                return "_const0"
            if lit == 1:
                return "_const1"
            if lit > 0:
                return _sig_name(lit)
            # negative literal -> emit an inverter
            base = _sig_name(-lit)
            inv = _inv_name(base)
            out.append(f".names {base} {inv}\n0 1")
            return inv

        an = resolve_input(a_lit)
        if kind in ('and', 'xor', 'or'):
            bn = resolve_input(b_lit)
            if kind == 'and':
                out.append(f".names {an} {bn} {out_name}\n11 1")
            elif kind == 'xor':
                out.append(f".names {an} {bn} {out_name}\n01 1\n10 1")
            else:  # or
                out.append(f".names {an} {bn} {out_name}\n1- 1\n-1 1")
        elif kind == 'not':
            # out = ~a : use .names a out  (0 1) directly
            out.append(f".names {an} {out_name}\n0 1")
        else:
            raise ValueError(f"unknown kind {kind}")

    # gate output names
    gate_names = {}
    for g in net.gates:
        out_id = g[1]
        gate_names[out_id] = _sig_name(out_id)

    # emit gates in stored (topological) order
    for g in net.gates:
        kind = g[0]
        out_id = g[1]
        out_name = gate_names[out_id]
        if kind == 'not':
            emit_gate('not', g[2], None, out_name)
        else:
            emit_gate(kind, g[2], g[3], out_name)

    # ordinary output buffers
    def final_name(lit):
        if lit == 0:
            return "_const0"
        if lit == 1:
            return "_const1"
        if lit > 0:
            return gate_names[lit] if lit in gate_names else _sig_name(lit)
        inv = _inv_name(gate_names[-lit])
        out.append(f".names {gate_names[-lit]} {inv}\n0 1")
        return inv

    for i, lit in enumerate(net.outputs):
        out.append(f".names {final_name(lit)} out{i}\n1 1")
    for i, lit in enumerate(net.bad):
        out.append(f".names {final_name(lit)} bad{i}\n1 1")

    # constraints
    for lit in net.constraints:
        fn = final_name(lit)
        out.append(f".names {fn}\n1")

    # latches
    for lname, cur, init_value, next_lit in net.latches:
        nxt = final_name(next_lit)
        out.append(f".latch {nxt} {_sig_name(cur)} {init_value}")

    out.append(".end")
    return "\n".join(out) + "\n"


def write_blif(net: Netlist, path: str, name="top") -> None:
    with open(path, "w") as f:
        f.write(to_blif_text(net, name))
