#include "pdr_perturb.hpp"

#include "aig.hpp"
#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <random>
#include <sstream>

namespace {
unsigned remap_lit(unsigned lit, const vector<unsigned> &var_map){
    unsigned var = lit >> 1;
    if(var == 0 || var >= var_map.size() || var_map[var] == 0 || var_map[var] == var)
        return lit;
    return (var_map[var] << 1) | (lit & 1);
}

void remap_aiger_refs(Aiger *aiger, const vector<unsigned> &var_map){
    for(auto &lit : aiger->Aiger_outputs)
        lit = remap_lit(lit, var_map);
    for(auto &lit : aiger->Aiger_bads)
        lit = remap_lit(lit, var_map);
    for(auto &lit : aiger->Aiger_constraints)
        lit = remap_lit(lit, var_map);
    for(auto &latch : aiger->Aiger_latches){
        latch.l = remap_lit(latch.l, var_map);
        latch.next = remap_lit(latch.next, var_map);
        if(latch.default_val > 1)
            latch.default_val = remap_lit(latch.default_val, var_map);
    }
    for(auto &gate : aiger->Aiger_ands){
        gate.o = remap_lit(gate.o, var_map);
        gate.i1 = remap_lit(gate.i1, var_map);
        gate.i2 = remap_lit(gate.i2, var_map);
    }
}

void print_var_map(const char *tag, unsigned seed, const vector<unsigned> &var_map, int first, int last){
    cout << "c " << tag << " seed=" << seed << " map=";
    bool first_item = true;
    for(int i=first; i<=last; ++i){
        if(i < 0 || i >= static_cast<int>(var_map.size()) || var_map[i] == 0 || var_map[i] == static_cast<unsigned>(i))
            continue;
        if(!first_item) cout << ",";
        cout << i << "->" << var_map[i];
        first_item = false;
    }
    cout << endl;
}

bool apply_input_var_map(Aiger *aiger, const vector<unsigned> &input_var_map, const char *tag, unsigned seed){
    bool changed = false;
    for(int i=1; i<=aiger->num_inputs; ++i)
        changed = changed || input_var_map[i] != static_cast<unsigned>(i);
    if(!changed)
        return false;

    remap_aiger_refs(aiger, input_var_map);
    print_var_map(tag, seed, input_var_map, 1, aiger->num_inputs);
    return true;
}

bool perturb_input_variables(Aiger *aiger, unsigned seed){
    if(aiger == nullptr || aiger->num_inputs <= 1)
        return false;

    vector<unsigned> vars;
    vars.reserve(aiger->num_inputs);
    for(int i=1; i<=aiger->num_inputs; ++i)
        vars.push_back(i);

    std::mt19937 rng(seed);
    std::shuffle(vars.begin(), vars.end(), rng);

    vector<unsigned> input_var_map(aiger->num_inputs + 1, 0);
    for(int i=1; i<=aiger->num_inputs; ++i)
        input_var_map[i] = vars[i-1];

    return apply_input_var_map(aiger, input_var_map, "INPUT_PERMUTE", seed);
}

void score_input_lit(unsigned lit, vector<int> &score, int weight){
    unsigned var = lit >> 1;
    if(var > 0 && var < score.size())
        score[var] += weight;
}

bool perturb_input_by_score(Aiger *aiger, bool reverse, unsigned seed){
    if(aiger == nullptr || aiger->num_inputs <= 1)
        return false;

    vector<int> score(aiger->num_inputs + 1, 0);
    for(const auto &gate : aiger->Aiger_ands){
        score_input_lit(gate.i1, score, 1);
        score_input_lit(gate.i2, score, 1);
    }
    for(const auto &latch : aiger->Aiger_latches)
        score_input_lit(latch.next, score, 4);
    for(auto lit : aiger->Aiger_outputs)
        score_input_lit(lit, score, 8);
    for(auto lit : aiger->Aiger_bads)
        score_input_lit(lit, score, 8);
    for(auto lit : aiger->Aiger_constraints)
        score_input_lit(lit, score, 8);

    vector<unsigned> ordered;
    ordered.reserve(aiger->num_inputs);
    for(int i=1; i<=aiger->num_inputs; ++i)
        ordered.push_back(i);

    std::mt19937 rng(seed);
    std::shuffle(ordered.begin(), ordered.end(), rng);
    std::stable_sort(ordered.begin(), ordered.end(), [&](unsigned a, unsigned b){
        if(score[a] != score[b])
            return reverse ? score[a] < score[b] : score[a] > score[b];
        return a < b;
    });

    vector<unsigned> input_var_map(aiger->num_inputs + 1, 0);
    for(size_t i=0; i<ordered.size(); ++i)
        input_var_map[ordered[i]] = static_cast<unsigned>(i + 1);

    return apply_input_var_map(
        aiger,
        input_var_map,
        reverse ? "INPUT_SCORE_ASC" : "INPUT_SCORE_DESC",
        seed);
}

bool perturb_input_swap(Aiger *aiger, unsigned seed){
    if(aiger == nullptr || aiger->num_inputs <= 1)
        return false;

    unsigned pairs = static_cast<unsigned>(aiger->num_inputs * (aiger->num_inputs - 1) / 2);
    unsigned selected = pairs == 0 ? 0 : seed % pairs;
    unsigned count = 0;
    int left = 1, right = 2;
    for(int i=1; i<=aiger->num_inputs; ++i){
        for(int j=i+1; j<=aiger->num_inputs; ++j){
            if(count == selected){
                left = i;
                right = j;
            }
            ++count;
        }
    }

    vector<unsigned> input_var_map(aiger->num_inputs + 1, 0);
    for(int i=1; i<=aiger->num_inputs; ++i)
        input_var_map[i] = i;
    input_var_map[left] = right;
    input_var_map[right] = left;

    return apply_input_var_map(aiger, input_var_map, "INPUT_SWAP", seed);
}

bool perturb_latch_variables(Aiger *aiger, unsigned seed){
    if(aiger == nullptr || aiger->num_latches <= 1)
        return false;

    vector<unsigned> vars;
    vars.reserve(aiger->num_latches);
    for(int i=1; i<=aiger->num_latches; ++i)
        vars.push_back(aiger->num_inputs + i);

    std::mt19937 rng(seed);
    std::shuffle(vars.begin(), vars.end(), rng);

    bool changed = false;
    vector<unsigned> var_map(aiger->max_var + 1, 0);
    for(int i=0; i<=aiger->max_var; ++i)
        var_map[i] = i;
    for(int i=1; i<=aiger->num_latches; ++i){
        unsigned old_var = aiger->num_inputs + i;
        var_map[old_var] = vars[i-1];
        changed = changed || var_map[old_var] != old_var;
    }
    if(!changed)
        return false;

    remap_aiger_refs(aiger, var_map);
    std::sort(aiger->Aiger_latches.begin(), aiger->Aiger_latches.end(),
        [](const Aiger_latch &a, const Aiger_latch &b){ return a.l < b.l; });
    print_var_map("LATCH_PERMUTE", seed, var_map, aiger->num_inputs + 1, aiger->num_inputs + aiger->num_latches);
    return true;
}

bool perturb_gate_runs(Aiger *aiger, unsigned seed){
    if(aiger == nullptr || aiger->num_ands <= 1)
        return false;

    vector<int> depth(aiger->max_var + 1, 0);
    for(int i=0; i<aiger->num_ands; ++i){
        const Aiger_and &gate = aiger->Aiger_ands[i];
        unsigned out_var = gate.o >> 1;
        unsigned i1_var = gate.i1 >> 1;
        unsigned i2_var = gate.i2 >> 1;
        int d1 = i1_var < depth.size() ? depth[i1_var] : 0;
        int d2 = i2_var < depth.size() ? depth[i2_var] : 0;
        depth[out_var] = std::max(d1, d2) + 1;
    }

    vector<unsigned> var_map(aiger->max_var + 1, 0);
    for(int i=0; i<=aiger->max_var; ++i)
        var_map[i] = i;

    std::mt19937 rng(seed);
    bool changed = false;
    int start = 0;
    while(start < aiger->num_ands){
        int end = start + 1;
        unsigned start_var = aiger->Aiger_ands[start].o >> 1;
        int run_depth = depth[start_var];
        while(end < aiger->num_ands){
            unsigned v = aiger->Aiger_ands[end].o >> 1;
            if(depth[v] != run_depth)
                break;
            ++end;
        }
        if(end - start > 1){
            vector<unsigned> positions;
            positions.reserve(end - start);
            for(int i=start; i<end; ++i)
                positions.push_back(aiger->Aiger_ands[i].o >> 1);
            vector<unsigned> shuffled = positions;
            std::shuffle(shuffled.begin(), shuffled.end(), rng);
            for(size_t i=0; i<positions.size(); ++i){
                var_map[positions[i]] = shuffled[i];
                changed = changed || positions[i] != shuffled[i];
            }
        }
        start = end;
    }
    if(!changed)
        return false;

    remap_aiger_refs(aiger, var_map);
    std::sort(aiger->Aiger_ands.begin(), aiger->Aiger_ands.end(),
        [](const Aiger_and &a, const Aiger_and &b){ return a.o < b.o; });
    print_var_map("GATE_RUN_PERMUTE", seed, var_map, aiger->num_inputs + aiger->num_latches + 1, aiger->max_var);
    return true;
}

bool perturb_has_mode(const string &spec, const string &mode){
    if(spec.empty())
        return false;
    std::stringstream ss(spec);
    string item;
    while(std::getline(ss, item, ',')){
        if(item == mode || item == "all")
            return true;
    }
    return false;
}
}

void apply_pdr_perturbations(Aiger *aiger, const std::string &modes, unsigned seed){
    if(modes.empty())
        return;
    bool any = false;
    if(perturb_has_mode(modes, "input"))
        any = perturb_input_variables(aiger, seed) || any;
    if(perturb_has_mode(modes, "input-swap"))
        any = perturb_input_swap(aiger, seed) || any;
    if(perturb_has_mode(modes, "input-fanout"))
        any = perturb_input_by_score(aiger, false, seed) || any;
    if(perturb_has_mode(modes, "input-fanout-rev"))
        any = perturb_input_by_score(aiger, true, seed) || any;
    if(perturb_has_mode(modes, "latch"))
        any = perturb_latch_variables(aiger, seed + 0x9e3779b9U) || any;
    if(perturb_has_mode(modes, "gate-run"))
        any = perturb_gate_runs(aiger, seed + 0x3c6ef372U) || any;
    if(any)
        cout << "c PDR_PERTURB modes=" << modes << " seed=" << seed << endl;
}
