"""Gate-level netlist intermediate representation for Path B.

The netlist is the single source of truth from which both AAG and BLIF are
exported.  Signals are non-negative integer IDs; literal polarity is tracked
as a Python sign in each gate's fanins (the exporters decide how to encode
inversion in AAG literals / BLIF .names rows).

Constants:
    CONST_0 = 0   (literal +0  = always false)
    CONST_1 = 1   (literal -0  = always true, represented as negated 0)
"""

from __future__ import annotations

CONST_0 = 0
CONST_1 = 1  # "negated 0": we model true as NOT(false) by convention


class Netlist:
    """A sequential AIG-like netlist with explicit XOR/OR gate types.

    Gate kinds and their fanin encodings:

        ('and', out, a, b)          out = a & b
        ('xor', out, a, b)          out = a ^ b
        ('or',  out, a, b)          out = a | b
        ('not', out, a)             out = ~a

    A fanin `f` is either:
        * a non-negative int >= 1  -> the signal literal in positive polarity,
          where 0 means CONST_0 (constant false);
        * a negative int <= -1     -> the signal `abs(f)` in negative polarity,
          where -0 is not representable; CONST_1 is handled by passing literal
          0 through a ('not', ...) gate.

    Latches:
        latches = [(name, cur, init_value, next_lit)] where `cur` is the
        current-state signal id (always a fresh positive id), `init_value`
        is the initialization value (0 or 1), and `next_lit` is a literal.

    Bad / outputs:
        bad  : list of literals (signals that must stay false)
        outputs : list of literals (ordinary outputs, informational)
        constraints : list of literals (must hold in every reachable state)
    """

    def __init__(self, name="top"):
        self.name = name
        self.inputs = []            # list[int] fresh signal ids
        self.latches = []           # list[(name, cur_id, init_lit, next_lit)]
        self.gates = []             # list[(kind, out, a, b) | (kind, out, a)]
        self.bad = []               # list[int] literals
        self.outputs = []           # list[int] literals
        self.constraints = []       # list[int] literals
        self._next_id = 2           # id 0 = CONST_0, id 1 = CONST_1; signals
                                    # therefore start at 2

    # ------------------------------------------------------------------ #
    #  builders
    # ------------------------------------------------------------------ #
    def _fresh(self) -> int:
        nid = self._next_id
        self._next_id += 1
        return nid

    def add_input(self) -> int:
        i = self._fresh()
        self.inputs.append(i)
        return i

    def add_latch(self, name, init_value, next_lit) -> int:
        """Create a latch; returns its current-state signal id.

        init_value is 0 or 1; next_lit is a literal (±signal id or 0).
        """
        cur = self._fresh()
        self.latches.append((name, cur, int(init_value), next_lit))
        return cur

    def and_gate(self, a, b, out=None):
        out = out if out is not None else self._fresh()
        self.gates.append(('and', out, a, b))
        return out

    def xor_gate(self, a, b, out=None):
        out = out if out is not None else self._fresh()
        self.gates.append(('xor', out, a, b))
        return out

    def or_gate(self, a, b, out=None):
        out = out if out is not None else self._fresh()
        self.gates.append(('or', out, a, b))
        return out

    def not_gate(self, a, out=None):
        out = out if out is not None else self._fresh()
        self.gates.append(('not', out, a))
        return out

    def add_bad(self, lit) -> None:
        self.bad.append(lit)

    def add_output(self, lit) -> None:
        self.outputs.append(lit)

    def add_constraint(self, lit) -> None:
        self.constraints.append(lit)

    # ------------------------------------------------------------------ #
    #  helpers
    # ------------------------------------------------------------------ #
    def lit_neg(self, lit: int) -> int:
        """Return the negated literal of `lit`.

        Positive id p -> -p; negative -p -> p; CONST_0 (0) -> CONST_1 is
        NOT representable as a bare literal, so callers must route a true
        constant through a not gate on CONST_0.  We expose a helper that
        allocates such a gate for the caller.
        """
        if lit == 0:
            raise ValueError(
                "cannot negate CONST_0 directly; use not_gate(CONST_0, out)")
        return -lit

    def const_true(self) -> int:
        """Return a signal id whose value is constant 1 (via NOT(CONST_0))."""
        return self.not_gate(0)

    def stats(self) -> dict:
        n_ands = sum(1 for g in self.gates if g[0] == 'and')
        n_xors = sum(1 for g in self.gates if g[0] == 'xor')
        n_ors = sum(1 for g in self.gates if g[0] == 'or')
        n_nots = sum(1 for g in self.gates if g[0] == 'not')
        return {
            "inputs": len(self.inputs),
            "latches": len(self.latches),
            "ands": n_ands,
            "xors": n_xors,
            "ors": n_ors,
            "nots": n_nots,
            "bad": len(self.bad),
            "outputs": len(self.outputs),
            "constraints": len(self.constraints),
        }

    def evaluate_sequential(self, init_state, input_stream):
        """Reference simulator used for differential checking.

        init_state : dict latch_name -> 0/1 (only latches with explicit init)
        input_stream : iterable of dict input_id -> 0/1, one per time step.
        Returns (reachable_bad_any, max_bad_time) for the first N steps.
        """
        # name -> bool value
        from collections import OrderedDict
        value = OrderedDict()
        value[0] = False
        # init latches
        latch_sig = {}
        for name, cur, init_value, _nxt in self.latches:
            latch_sig[name] = cur
            value[cur] = bool(init_value)
        # override with explicit init_state
        for name, v in (init_state or {}).items():
            value[latch_sig[name]] = bool(v)

        bad_any = False
        bad_time = None

        def lit_val(lit):
            if lit == 0:
                return False
            if lit < 0:
                return not value[abs(lit)]
            return value[lit]

        t = 0
        for step_inputs in input_stream:
            # set primary inputs first (gates may reference them)
            for iid, v in step_inputs.items():
                value[iid] = bool(v)
            # evaluate all gates in topological order (assume stored topo)
            for g in self.gates:
                kind = g[0]
                if kind == 'not':
                    _, out, a = g
                    value[out] = not lit_val(a)
                else:
                    _, out, a, b = g
                    va, vb = lit_val(a), lit_val(b)
                    if kind == 'and':
                        value[out] = va and vb
                    elif kind == 'xor':
                        value[out] = va != vb
                    elif kind == 'or':
                        value[out] = va or vb
            # check bad
            for blit in self.bad:
                if lit_val(blit):
                    bad_any = True
                    if bad_time is None:
                        bad_time = t
            # Latches update simultaneously.  Compute every next value from
            # the old state before committing any of them; updating in place
            # would incorrectly turn a register chain into combinational
            # propagation within one simulated cycle.
            next_values = [lit_val(nxt) for _name, _cur, _init, nxt in self.latches]
            for (_name, cur, _init, _nxt), next_value in zip(
                self.latches, next_values
            ):
                value[cur] = next_value
            t += 1
            if bad_time is not None and len(self.bad) > 0:
                break
        return bad_any, bad_time
