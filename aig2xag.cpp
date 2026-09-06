#include "aig2xag.hpp"

#include <algorithm>
#include <cassert>
#include <cmath>
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

std::vector<char> backward_cone(const Aiger &aig, const std::vector<unsigned> &roots) {
    std::vector<char> cone(aig.max_var + 1, 0);
    std::queue<unsigned> work;
    for (unsigned lit : roots)
        work.push(lit_var(lit));

    while (!work.empty()) {
        unsigned var = work.front();
        work.pop();
        if (var == 0 || var >= cone.size() || cone[var])
            continue;
        cone[var] = 1;
        if (!is_and_var(aig, var))
            continue;
        int index = static_cast<int>(var) - aig.num_inputs - aig.num_latches - 1;
        if (index < 0 || index >= static_cast<int>(aig.Aiger_ands.size()))
            continue;
        work.push(lit_var(aig.Aiger_ands[index].i1));
        work.push(lit_var(aig.Aiger_ands[index].i2));
    }
    return cone;
}

bool select_xor(
    XorSelectionPolicy policy,
    unsigned var,
    const std::vector<char> &next_cone,
    const std::vector<char> &bad_cone,
    const std::vector<int> &depths,
    const std::vector<int> &fanouts,
    int deep_threshold,
    int min_fanout,
    double sample_fraction,
    unsigned sample_seed
) {
    bool in_next = var < next_cone.size() && next_cone[var];
    bool in_bad = var < bad_cone.size() && bad_cone[var];
    int fanout = var < fanouts.size() ? fanouts[var] : 0;
    switch (policy) {
    case XorSelectionPolicy::All:
        return true;
    case XorSelectionPolicy::NextCone:
        return in_next;
    case XorSelectionPolicy::BadCone:
        return in_bad;
    case XorSelectionPolicy::SharedCone:
        return in_next && in_bad;
    case XorSelectionPolicy::NextOnly:
        return in_next && !in_bad;
    case XorSelectionPolicy::BadOnly:
        return in_bad && !in_next;
    case XorSelectionPolicy::EitherCone:
        return in_next || in_bad;
    case XorSelectionPolicy::DeepCone:
        return (in_next || in_bad) && var < depths.size() && depths[var] >= deep_threshold;
    case XorSelectionPolicy::ShallowCone:
        return (in_next || in_bad) && var < depths.size() && depths[var] < deep_threshold;
    case XorSelectionPolicy::HighFanout:
        return fanout >= min_fanout;
    case XorSelectionPolicy::LowFanout:
        return fanout < min_fanout;
    case XorSelectionPolicy::NextLowFanout:
        return in_next && fanout < min_fanout;
    case XorSelectionPolicy::BadLowFanout:
        return in_bad && fanout < min_fanout;
    case XorSelectionPolicy::SharedLowFanout:
        return in_next && in_bad && fanout < min_fanout;
    case XorSelectionPolicy::EitherLowFanout:
        return (in_next || in_bad) && fanout < min_fanout;
    case XorSelectionPolicy::HashSample: {
        if (sample_fraction <= 0.0)
            return false;
        if (sample_fraction >= 1.0)
            return true;
        unsigned hash = var ^ sample_seed ^ 0x9e3779b9U;
        hash ^= hash >> 16;
        hash *= 0x7feb352dU;
        hash ^= hash >> 15;
        hash *= 0x846ca68bU;
        hash ^= hash >> 16;
        double unit = static_cast<double>(hash)
            / static_cast<double>(0xffffffffU);
        return unit < sample_fraction;
    }
    }
    return false;
}

} // namespace

const char *xor_selection_policy_name(XorSelectionPolicy policy) {
    switch (policy) {
    case XorSelectionPolicy::All:
        return "all";
    case XorSelectionPolicy::NextCone:
        return "next";
    case XorSelectionPolicy::BadCone:
        return "bad";
    case XorSelectionPolicy::SharedCone:
        return "shared";
    case XorSelectionPolicy::NextOnly:
        return "next-only";
    case XorSelectionPolicy::BadOnly:
        return "bad-only";
    case XorSelectionPolicy::EitherCone:
        return "cone";
    case XorSelectionPolicy::DeepCone:
        return "deep";
    case XorSelectionPolicy::ShallowCone:
        return "shallow";
    case XorSelectionPolicy::HighFanout:
        return "high-fanout";
    case XorSelectionPolicy::LowFanout:
        return "low-fanout";
    case XorSelectionPolicy::NextLowFanout:
        return "next-low-fanout";
    case XorSelectionPolicy::BadLowFanout:
        return "bad-low-fanout";
    case XorSelectionPolicy::SharedLowFanout:
        return "shared-low-fanout";
    case XorSelectionPolicy::EitherLowFanout:
        return "cone-low-fanout";
    case XorSelectionPolicy::HashSample:
        return "sample";
    }
    return "all";
}

bool parse_xor_selection_policy(const std::string &name, XorSelectionPolicy &policy) {
    if (name == "all")
        policy = XorSelectionPolicy::All;
    else if (name == "next")
        policy = XorSelectionPolicy::NextCone;
    else if (name == "bad")
        policy = XorSelectionPolicy::BadCone;
    else if (name == "shared")
        policy = XorSelectionPolicy::SharedCone;
    else if (name == "next-only")
        policy = XorSelectionPolicy::NextOnly;
    else if (name == "bad-only")
        policy = XorSelectionPolicy::BadOnly;
    else if (name == "cone")
        policy = XorSelectionPolicy::EitherCone;
    else if (name == "deep")
        policy = XorSelectionPolicy::DeepCone;
    else if (name == "shallow")
        policy = XorSelectionPolicy::ShallowCone;
    else if (name == "high-fanout")
        policy = XorSelectionPolicy::HighFanout;
    else if (name == "low-fanout")
        policy = XorSelectionPolicy::LowFanout;
    else if (name == "next-low-fanout")
        policy = XorSelectionPolicy::NextLowFanout;
    else if (name == "bad-low-fanout")
        policy = XorSelectionPolicy::BadLowFanout;
    else if (name == "shared-low-fanout")
        policy = XorSelectionPolicy::SharedLowFanout;
    else if (name == "cone-low-fanout")
        policy = XorSelectionPolicy::EitherLowFanout;
    else if (name == "sample")
        policy = XorSelectionPolicy::HashSample;
    else
        return false;
    return true;
}

ConvertResult convert(const Aiger &aig, const ConvertOptions &options) {
    ConvertResult result;
    result.stats.original_inputs = aig.num_inputs;
    result.stats.original_latches = aig.num_latches;
    result.stats.original_ands = aig.num_ands;

    std::vector<RawGate> raw(aig.max_var + 1);
    std::vector<unsigned> next_roots;
    std::vector<unsigned> bad_roots;
    next_roots.reserve(aig.Aiger_latches.size());
    for (const Aiger_latch &latch : aig.Aiger_latches)
        next_roots.push_back(latch.next);
    if (aig.Aiger_bads.empty())
        bad_roots.insert(bad_roots.end(), aig.Aiger_outputs.begin(), aig.Aiger_outputs.end());
    else
        bad_roots.insert(bad_roots.end(), aig.Aiger_bads.begin(), aig.Aiger_bads.end());
    bad_roots.insert(bad_roots.end(), aig.Aiger_constraints.begin(), aig.Aiger_constraints.end());
    std::vector<char> next_cone = backward_cone(aig, next_roots);
    std::vector<char> bad_cone = backward_cone(aig, bad_roots);
    std::vector<int> depths(aig.max_var + 1, 0);
    std::vector<int> fanouts(aig.max_var + 1, 0);
    for (const Aiger_and &gate : aig.Aiger_ands) {
        unsigned i0 = lit_var(gate.i1);
        unsigned i1 = lit_var(gate.i2);
        if (i0 < fanouts.size())
            ++fanouts[i0];
        if (i1 < fanouts.size())
            ++fanouts[i1];
    }
    for (const Aiger_latch &latch : aig.Aiger_latches) {
        unsigned var = lit_var(latch.next);
        if (var < fanouts.size())
            ++fanouts[var];
    }
    for (unsigned lit : aig.Aiger_outputs) {
        unsigned var = lit_var(lit);
        if (var < fanouts.size())
            ++fanouts[var];
    }
    for (unsigned lit : aig.Aiger_bads) {
        unsigned var = lit_var(lit);
        if (var < fanouts.size())
            ++fanouts[var];
    }
    for (unsigned lit : aig.Aiger_constraints) {
        unsigned var = lit_var(lit);
        if (var < fanouts.size())
            ++fanouts[var];
    }
    for (const Aiger_and &gate : aig.Aiger_ands) {
        unsigned var = lit_var(gate.o);
        depths[var] = 1 + std::max(depths[lit_var(gate.i1)], depths[lit_var(gate.i2)]);
    }
    int root_depth = 0;
    for (unsigned lit : next_roots)
        root_depth = std::max(root_depth, depths[lit_var(lit)]);
    for (unsigned lit : bad_roots)
        root_depth = std::max(root_depth, depths[lit_var(lit)]);
    int deep_threshold = static_cast<int>(std::ceil(root_depth * options.deep_xor_fraction));

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

        if (options.recognize_xors && is_xor_output(aig, gate, lit0, lit1)) {
            result.stats.candidate_xors++;
            bool selected = select_xor(
                    options.xor_policy, var, next_cone, bad_cone, depths, fanouts,
                    deep_threshold, options.min_xor_fanout,
                    options.xor_sample_fraction,
                    options.xor_sample_seed);
            if (options.restrict_xors_to_allowlist
                && options.xor_allowlist.find(var) == options.xor_allowlist.end())
                selected = false;
            if (selected) {
                raw[var].type = XAG_XOR;
                raw[var].fanin0 = lit0;
                raw[var].fanin1 = lit1;
                result.stats.recognized_xors++;
            }
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
    for (int i = 0; i < aig.num_latches; ++i) {
        mark_root(raw, aig.Aiger_latches[i].next);
        unsigned reset = aig.Aiger_latches[i].default_val;
        if (reset > 1 && reset != aig.Aiger_latches[i].l)
            mark_root(raw, reset);
    }

    for (int i = 0; i < aig.num_ands; ++i) {
        unsigned var = lit_var(aig.Aiger_ands[i].o);
        if (raw[var].type != XAG_AND && raw[var].type != XAG_XOR)
            continue;
        add_fanout(raw, raw[var].fanin0, var);
        add_fanout(raw, raw[var].fanin1, var);
    }

    if (options.sweep_unused_gates) {
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
        if (raw[orig_var].type == XAG_XOR
            && (options.lower_xors_to_ands || options.stable_xor_slots)) {
            // Reserve two canonical child ANDs before the original XOR output.
            // The original output mapping remains stable for every downstream gate.
            next_var += 2;
        }
        xag.orig_to_xag_var[orig_var] = next_var++;
    }

    for (int i = 0; i < aig.num_latches; ++i) {
        XagLatch latch;
        latch.original_lit = aig.Aiger_latches[i].l;
        latch.lit = remap_lit(xag, aig.Aiger_latches[i].l);
        latch.next = remap_lit(xag, aig.Aiger_latches[i].next);
        latch.default_val = remap_lit(xag, aig.Aiger_latches[i].default_val);
        xag.latches.push_back(latch);
    }

    for (int i = 0; i < aig.num_ands; ++i) {
        unsigned orig_var = lit_var(aig.Aiger_ands[i].o);
        if (raw[orig_var].deleted)
            continue;
        if (raw[orig_var].type != XAG_AND && raw[orig_var].type != XAG_XOR)
            continue;

        unsigned out = remap_lit(xag, aig.Aiger_ands[i].o);
        unsigned fanin0 = remap_lit(xag, raw[orig_var].fanin0);
        unsigned fanin1 = remap_lit(xag, raw[orig_var].fanin1);
        if (raw[orig_var].type == XAG_XOR && options.lower_xors_to_ands) {
            unsigned out_var = lit_var(out);
            unsigned negative_pair = (out_var - 2) << 1;
            unsigned positive_pair = (out_var - 1) << 1;
            XagGate negative_gate;
            negative_gate.type = XAG_AND;
            negative_gate.out = negative_pair;
            negative_gate.fanin0 = invert_lit(fanin0);
            negative_gate.fanin1 = invert_lit(fanin1);
            xag.gates.push_back(negative_gate);

            XagGate positive_gate;
            positive_gate.type = XAG_AND;
            positive_gate.out = positive_pair;
            positive_gate.fanin0 = fanin0;
            positive_gate.fanin1 = fanin1;
            xag.gates.push_back(positive_gate);

            XagGate output_gate;
            output_gate.type = XAG_AND;
            output_gate.out = out;
            output_gate.fanin0 = invert_lit(negative_pair);
            output_gate.fanin1 = invert_lit(positive_pair);
            output_gate.original_out = aig.Aiger_ands[i].o;
            xag.gates.push_back(output_gate);
            xag.num_ands += 3;
        } else {
            if (raw[orig_var].type == XAG_XOR && options.stable_xor_slots) {
                unsigned out_var = lit_var(out);
                XagGate unused0;
                unused0.type = XAG_UNUSED;
                unused0.out = (out_var - 2) << 1;
                xag.gates.push_back(unused0);

                XagGate unused1;
                unused1.type = XAG_UNUSED;
                unused1.out = (out_var - 1) << 1;
                xag.gates.push_back(unused1);
            }
            XagGate gate;
            gate.type = raw[orig_var].type;
            gate.original_out = aig.Aiger_ands[i].o;
            gate.out = out;
            gate.fanin0 = fanin0;
            gate.fanin1 = fanin1;
            xag.gates.push_back(gate);

            if (gate.type == XAG_XOR)
                xag.num_xors++;
            else
                xag.num_ands++;
        }
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

ConvertResult convert(const Aiger &aig, bool sweep_unused_gates) {
    ConvertOptions options;
    options.sweep_unused_gates = sweep_unused_gates;
    return convert(aig, options);
}

AutoSelectResult select_for_pdr(
    const Aiger &aig,
    int min_next_depth,
    double min_estimated_and_reduction
) {
    AutoSelectResult result;
    std::vector<int> depths(aig.max_var + 1, 0);

    for (const Aiger_and &gate : aig.Aiger_ands) {
        unsigned out_var = lit_var(gate.o);
        unsigned fanin0_var = lit_var(gate.i1);
        unsigned fanin1_var = lit_var(gate.i2);
        depths[out_var] = 1 + std::max(depths[fanin0_var], depths[fanin1_var]);
    }

    for (const Aiger_latch &latch : aig.Aiger_latches) {
        unsigned next_var = lit_var(latch.next);
        if (next_var < depths.size())
            result.next_depth = std::max(result.next_depth, depths[next_var]);
    }

    for (const Aiger_and &gate : aig.Aiger_ands) {
        unsigned lit0 = 0;
        unsigned lit1 = 0;
        if (is_xor_output(aig, gate, lit0, lit1))
            ++result.recognized_xors;
    }

    if (aig.num_ands > 0) {
        result.estimated_and_reduction = std::min(
            1.0,
            3.0 * static_cast<double>(result.recognized_xors)
                / static_cast<double>(aig.num_ands));
    }
    result.use_xag = result.next_depth >= min_next_depth
        && result.estimated_and_reduction >= min_estimated_and_reduction;
    return result;
}

} // namespace aig2xag
