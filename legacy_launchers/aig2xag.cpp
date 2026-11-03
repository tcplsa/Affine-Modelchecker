#include "aig2xag.hpp"

#include <algorithm>
#include <cassert>
#include <queue>
#include <unordered_set>

namespace aig2xag {

namespace {

struct RawGate {
    XagGateType type = XAG_UNUSED;
    unsigned fanin0 = 0;
    unsigned fanin1 = 0;
    std::unordered_set<unsigned> fanouts;
    bool root = false;
    bool deleted = false;
};

inline unsigned lit_var(unsigned lit) {
    return lit >> 1;
}

inline bool lit_sign(unsigned lit) {
    return (lit & 1) != 0;
}

inline unsigned invert_lit(unsigned lit) {
    return lit ^ 1;
}

inline bool is_const_lit(unsigned lit) {
    return lit <= 1;
}

inline bool is_and_var(const Aiger &aig, unsigned var) {
    return var > static_cast<unsigned>(aig.num_inputs + aig.num_latches)
        && var <= static_cast<unsigned>(aig.max_var);
}

inline int and_index(const Aiger &aig, unsigned lit) {
    unsigned var = lit_var(lit);
    return static_cast<int>(var) - aig.num_inputs - aig.num_latches - 1;
}

inline unsigned sorted_first(unsigned a, unsigned b) {
    return lit_var(a) < lit_var(b) ? a : b;
}

inline unsigned sorted_second(unsigned a, unsigned b) {
    return lit_var(a) < lit_var(b) ? b : a;
}

void mark_root(std::vector<RawGate> &raw, unsigned lit) {
    unsigned var = lit_var(lit);
    if (var < raw.size())
        raw[var].root = true;
}

void add_fanout(std::vector<RawGate> &raw, unsigned fanin_lit, unsigned out_var) {
    unsigned fanin_var = lit_var(fanin_lit);
    if (fanin_var == 0 || fanin_var >= raw.size())
        return;
    raw[fanin_var].fanouts.insert(out_var);
}

bool is_xor_output(
    const Aiger &aig,
    const Aiger_and &gate,
    unsigned &lit0,
    unsigned &lit1
) {
    if (!lit_sign(gate.i1) || !lit_sign(gate.i2))
        return false;

    unsigned rhs0_var = lit_var(gate.i1);
    unsigned rhs1_var = lit_var(gate.i2);
    if (!is_and_var(aig, rhs0_var) || !is_and_var(aig, rhs1_var))
        return false;

    int idx0 = and_index(aig, gate.i1);
    int idx1 = and_index(aig, gate.i2);
    if (idx0 < 0 || idx1 < 0
        || idx0 >= static_cast<int>(aig.Aiger_ands.size())
        || idx1 >= static_cast<int>(aig.Aiger_ands.size()))
        return false;

    const Aiger_and &g0 = aig.Aiger_ands[idx0];
    const Aiger_and &g1 = aig.Aiger_ands[idx1];

    unsigned g0r0 = sorted_first(g0.i1, g0.i2);
    unsigned g0r1 = sorted_second(g0.i1, g0.i2);
    unsigned g1r0 = sorted_first(g1.i1, g1.i2);
    unsigned g1r1 = sorted_second(g1.i1, g1.i2);

    if (lit_var(g0r0) != lit_var(g1r0) || lit_var(g0r1) != lit_var(g1r1))
        return false;

    bool s00 = lit_sign(g0r0);
    bool s01 = lit_sign(g0r1);
    bool s10 = lit_sign(g1r0);
    bool s11 = lit_sign(g1r1);

    // ~(~a & ~b) & ~(a & b) == a xor b
    if ((s00 && s01 && !s10 && !s11) || (!s00 && !s01 && s10 && s11)) {
        lit0 = lit_var(g0r0) << 1;
        lit1 = lit_var(g0r1) << 1;
        return true;
    }

    // ~(a & ~b) & ~(~a & b) == a xnor b; encode as a xor ~b.
    if ((!s00 && s01 && s10 && !s11) || (s00 && !s01 && !s10 && s11)) {
        lit0 = lit_var(g0r0) << 1;
        lit1 = (lit_var(g0r1) << 1) | 1;
        return true;
    }

    return false;
}

unsigned remap_lit(const XagCircuit &xag, unsigned lit) {
    if (is_const_lit(lit))
        return lit;

    unsigned var = lit_var(lit);
    assert(var < xag.orig_to_xag_var.size());
    assert(xag.orig_to_xag_var[var] != 0);
    return (xag.orig_to_xag_var[var] << 1) | lit_sign(lit);
}

} // namespace

ConvertResult convert(const Aiger &aig, bool sweep_unused_gates) {
    ConvertResult result;
    result.stats.original_inputs = aig.num_inputs;
    result.stats.original_latches = aig.num_latches;
    result.stats.original_ands = aig.num_ands;

    std::vector<RawGate> raw(aig.max_var + 1);

    for (int i = 0; i < aig.num_inputs; ++i) {
        unsigned var = lit_var(aig.Aiger_inputs[i]);
        raw[var].type = XAG_INPUT;
    }

    for (int i = 0; i < aig.num_latches; ++i) {
        unsigned var = lit_var(aig.Aiger_latches[i].l);
        raw[var].type = XAG_LATCH;
    }

    for (int i = 0; i < aig.num_ands; ++i) {
        const Aiger_and &gate = aig.Aiger_ands[i];
        unsigned var = lit_var(gate.o);
        unsigned lit0 = 0, lit1 = 0;
        raw[var].type = XAG_AND;
        raw[var].fanin0 = gate.i1;
        raw[var].fanin1 = gate.i2;

        if (is_xor_output(aig, gate, lit0, lit1)) {
            raw[var].type = XAG_XOR;
            raw[var].fanin0 = lit0;
            raw[var].fanin1 = lit1;
            result.stats.recognized_xors++;
        }
    }

    for (int i = 0; i < aig.num_outputs; ++i)
        mark_root(raw, aig.Aiger_outputs[i]);
    for (int i = 0; i < aig.num_bads; ++i)
        mark_root(raw, aig.Aiger_bads[i]);
    for (int i = 0; i < aig.num_constraints; ++i)
        mark_root(raw, aig.Aiger_constraints[i]);

    // Latch next-state logic is a sequential root. This is the key extension
    // over the combinational X-SAT sweep, whose benchmarks have no latches.
    for (int i = 0; i < aig.num_latches; ++i)
        mark_root(raw, aig.Aiger_latches[i].next);

    for (int i = 0; i < aig.num_ands; ++i) {
        unsigned var = lit_var(aig.Aiger_ands[i].o);
        if (raw[var].type != XAG_AND && raw[var].type != XAG_XOR)
            continue;
        add_fanout(raw, raw[var].fanin0, var);
        add_fanout(raw, raw[var].fanin1, var);
    }

    if (sweep_unused_gates) {
        std::queue<unsigned> work;
        for (unsigned var = 1; var < raw.size(); ++var) {
            if ((raw[var].type == XAG_AND || raw[var].type == XAG_XOR)
                && raw[var].fanouts.empty()
                && !raw[var].root)
                work.push(var);
        }

        while (!work.empty()) {
            unsigned var = work.front();
            work.pop();
            if (raw[var].deleted || raw[var].root || !raw[var].fanouts.empty())
                continue;

            raw[var].deleted = true;
            unsigned parents[2] = { lit_var(raw[var].fanin0), lit_var(raw[var].fanin1) };
            for (unsigned parent : parents) {
                if (parent == 0 || parent >= raw.size())
                    continue;
                raw[parent].fanouts.erase(var);
                if ((raw[parent].type == XAG_AND || raw[parent].type == XAG_XOR)
                    && raw[parent].fanouts.empty()
                    && !raw[parent].root)
                    work.push(parent);
            }
        }
    }

    XagCircuit &xag = result.xag;
    xag.orig_to_xag_var.assign(aig.max_var + 1, 0);

    unsigned next_var = 1;
    for (int i = 0; i < aig.num_inputs; ++i) {
        unsigned orig_var = lit_var(aig.Aiger_inputs[i]);
        xag.orig_to_xag_var[orig_var] = next_var++;
        xag.inputs.push_back(xag.orig_to_xag_var[orig_var] << 1);
    }

    for (int i = 0; i < aig.num_latches; ++i) {
        unsigned orig_var = lit_var(aig.Aiger_latches[i].l);
        xag.orig_to_xag_var[orig_var] = next_var++;
    }

    for (int i = 0; i < aig.num_ands; ++i) {
        unsigned orig_var = lit_var(aig.Aiger_ands[i].o);
        if (raw[orig_var].deleted)
            continue;
        if (raw[orig_var].type != XAG_AND && raw[orig_var].type != XAG_XOR)
            continue;
        xag.orig_to_xag_var[orig_var] = next_var++;
    }

    for (int i = 0; i < aig.num_latches; ++i) {
        XagLatch latch;
        latch.original_lit = aig.Aiger_latches[i].l;
        latch.lit = remap_lit(xag, aig.Aiger_latches[i].l);
        latch.next = remap_lit(xag, aig.Aiger_latches[i].next);
        latch.default_val = aig.Aiger_latches[i].default_val;
        xag.latches.push_back(latch);
    }

    for (int i = 0; i < aig.num_ands; ++i) {
        unsigned orig_var = lit_var(aig.Aiger_ands[i].o);
        if (raw[orig_var].deleted)
            continue;
        if (raw[orig_var].type != XAG_AND && raw[orig_var].type != XAG_XOR)
            continue;

        XagGate gate;
        gate.type = raw[orig_var].type;
        gate.original_out = aig.Aiger_ands[i].o;
        gate.out = remap_lit(xag, aig.Aiger_ands[i].o);
        gate.fanin0 = remap_lit(xag, raw[orig_var].fanin0);
        gate.fanin1 = remap_lit(xag, raw[orig_var].fanin1);
        xag.gates.push_back(gate);

        if (gate.type == XAG_XOR)
            xag.num_xors++;
        else
            xag.num_ands++;
    }

    for (int i = 0; i < aig.num_outputs; ++i)
        xag.outputs.push_back(remap_lit(xag, aig.Aiger_outputs[i]));
    for (int i = 0; i < aig.num_bads; ++i)
        xag.bads.push_back(remap_lit(xag, aig.Aiger_bads[i]));
    for (int i = 0; i < aig.num_constraints; ++i)
        xag.constraints.push_back(remap_lit(xag, aig.Aiger_constraints[i]));

    xag.num_inputs = static_cast<int>(xag.inputs.size());
    xag.num_latches = static_cast<int>(xag.latches.size());
    result.stats.kept_ands = xag.num_ands;
    result.stats.removed_ands = aig.num_ands - xag.num_ands - xag.num_xors;

    return result;
}

} // namespace aig2xag
