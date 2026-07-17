#pragma once

#include "aig.hpp"

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
};

ConvertResult convert(const Aiger &aig, const ConvertOptions &options);
ConvertResult convert(const Aiger &aig, bool sweep_unused_gates = true);

} // namespace aig2xag
