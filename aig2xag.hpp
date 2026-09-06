#pragma once

#include "aig.hpp"

#include <unordered_set>
#include <vector>

namespace aig2xag {

enum XagGateType {
    XAG_INPUT,
    XAG_LATCH,
    XAG_AND,
    XAG_XOR,
    XAG_OR,
    XAG_UNUSED
};

enum class XorSelectionPolicy {
    All,
    NextCone,
    BadCone,
    SharedCone,
    NextOnly,
    BadOnly,
    EitherCone,
    DeepCone,
    ShallowCone,
    HighFanout,
    LowFanout,
    NextLowFanout,
    BadLowFanout,
    SharedLowFanout,
    EitherLowFanout,
    HashSample
};

struct XagGate {
    XagGateType type = XAG_UNUSED;
    unsigned out = 0;
    unsigned fanin0 = 0;
    unsigned fanin1 = 0;
    unsigned original_out = 0;
};

struct XagLatch {
    unsigned lit = 0;
    unsigned next = 0;
    unsigned default_val = 0;
    unsigned original_lit = 0;
};

struct XagCircuit {
    int num_inputs = 0;
    int num_latches = 0;
    int num_ands = 0;
    int num_xors = 0;
    int num_ors = 0;

    std::vector<unsigned> inputs;
    std::vector<XagLatch> latches;
    std::vector<XagGate> gates;
    std::vector<unsigned> outputs;
    std::vector<unsigned> bads;
    std::vector<unsigned> constraints;

    // original AIG variable -> compact XAG variable. 0 is reserved for const.
    std::vector<unsigned> orig_to_xag_var;
};

struct ConvertStats {
    int original_inputs = 0;
    int original_latches = 0;
    int original_ands = 0;
    int candidate_xors = 0;
    int recognized_xors = 0;
    int recognized_ors = 0;
    int kept_ands = 0;
    int removed_ands = 0;
};

struct ConvertResult {
    XagCircuit xag;
    ConvertStats stats;
};

struct ConvertOptions {
    bool recognize_xors = true;
    bool sweep_unused_gates = true;
    bool lower_xors_to_ands = false;
    bool stable_xor_slots = false;
    XorSelectionPolicy xor_policy = XorSelectionPolicy::All;
    double deep_xor_fraction = 0.5;
    int min_xor_fanout = 2;
    double xor_sample_fraction = 1.0;
    unsigned xor_sample_seed = 1;
    bool restrict_xors_to_allowlist = false;
    std::unordered_set<unsigned> xor_allowlist;
};

struct AutoSelectResult {
    bool use_xag = false;
    int next_depth = 0;
    int recognized_xors = 0;
    double estimated_and_reduction = 0.0;
};

ConvertResult convert(const Aiger &aig, const ConvertOptions &options);
ConvertResult convert(const Aiger &aig, bool sweep_unused_gates = true);
const char *xor_selection_policy_name(XorSelectionPolicy policy);
bool parse_xor_selection_policy(const std::string &name, XorSelectionPolicy &policy);
AutoSelectResult select_for_pdr(
    const Aiger &aig,
    int min_next_depth = 120,
    double min_estimated_and_reduction = 0.12);

} // namespace aig2xag
