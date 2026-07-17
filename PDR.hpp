#pragma once

#include <chrono>
#include <algorithm>
#include <random>
#include <set>
#include "aig.hpp"
#include "aig2xag.hpp"
#include "lemma_exchange.hpp"
#include "sat_solver.hpp"
//#include <atomic>

// Cone: constraints, bad, latches
// Real_Init: latches_default /\ constraints
// Real_Bad: bad \/ not constraints
// State: inputs + latches (must meet constraints)
// Obligation: State + frame_k
// Cubes: only latches
// Frame: Cubes
// F0(I), F1, F2, F3, ..., Foo(blocked by all)
// Ri = Fi + ... + Foo

// Invaints:
// R0 = I; Ri -> Ri+1; Ri -> -Bad

class State{
public:
    vector<int> latches, inputs;
    vector<int> witness_latches;
    bool has_witness_latches = false;
    State * next = nullptr;
    unsigned long long index;
    int failed;
    int failed_depth;
    State(){
        state_count++;
        index =  state_count;
        failed = 0;
        failed_depth = 0;
    }
    State(vector<int> l, vector<int> i):latches(l),inputs(i),witness_latches(l),has_witness_latches(true){
        state_count++;
        index =  state_count;
        failed = 0;
        failed_depth = 0;
    }
    void clear(){
        latches.clear();
        inputs.clear();
        witness_latches.clear();
        has_witness_latches = false;
        next = nullptr;
    }
    void set_witness_latches(const vector<int> &values){
        witness_latches = values;
        has_witness_latches = true;
    }
    const vector<int> &trace_latches() const{
        return has_witness_latches ? witness_latches : latches;
    }
};

class Obligation{
public:
    State *state = nullptr;
    int frame_k;
    int depth;
    int thread_index;
    Obligation(State *s, int k, int d, int t):state(s),frame_k(k),depth(d){
        if(t > 0)
            thread_index = t;
        else 
            thread_index = 1;
    }
    bool operator<(const Obligation &b) const{
        if (frame_k < b.frame_k) return true;       // prefer lower levels (required)
        if (frame_k > b.frame_k) return false;
        if (depth < b.depth) return true;           // prefer deeper (heuristic)
        if (depth > b.depth) return false;
        return ((state->index) < ((b.state)->index));
    }
};

class Lit_CMP{
public:
    bool operator()(const int &a, const int &b) const{
        if(abs(a) == abs(b))
            return a < b;
        else
            return abs(a) < abs(b);
    }
};
class heuristic_Lit_CMP{
public:
    vector<float> counts;
    bool operator()(const int &a, const int &b) const{
        if (abs(b) > counts.size()-1){
            cout << "heuristic bug found";
            return false;
        } 
        if (abs(a) > counts.size()-1){
            cout << "heuristic bug found";
            return true;
        } 
        return (counts[abs(a)] < counts[abs(b)]);
    }
};

typedef vector<int> Cube; // the lits in the cube must be sorted

enum class PDRDirection{
    Forward,
    Reverse
};

enum class PDRRepresentation{
    Default = -1,
    Aig = 0,
    Xag = 1,
    CompactAig = 2,
    LoweredXag = 3
};

struct TraceFrame{
    vector<int> latches;
    vector<int> inputs;
};

struct BridgeCandidate{
    TraceFrame left;
    TraceFrame right;
};

class Cube_CMP{
public:
    bool operator()(const Cube &a, const Cube &b) const{
        if(a.size() != b.size())
            return a.size() < b.size();
        else{
            for(int i=0; i<a.size(); ++i){
                if(a[i] != b[i])
                    return a[i] < b[i];
            }
        }
        return false;
    }
};

class Frame{
public:
    set<Cube, Cube_CMP> cubes;
    SATSolver *solver = nullptr;
    Frame();
};


class PDR : public Aiger
{
    Aiger *uaiger;
    
    // the interal data structure for Aiger (in CNF dimacs format).
    int thread_index;
    
    // for IC3
    minisatSimp *satelite = nullptr;
    minisatSimp *satelite2 = nullptr;
    SATSolver *lift = nullptr;
    SATSolver *init = nullptr;
    SATSolver *checker = nullptr;
    SATSolver *inductive_solver = nullptr;
    //minisatCore *lift = nullptr;
    // minisatCore *init = nullptr;
    int notInvConstraints, restart_depth;
    bool satelite_unsat, use_pr, use_acc, use_plusone_count;
    PDRDirection direction;
    PDRRepresentation representation = PDRRepresentation::Xag;
    bool cooperative_mode = false;
    bool engine_started = false;
    int engine_result = 0;
    std::atomic<bool> *cancel_requested = nullptr;
    unsigned cfg_random_seed = 1;
    bool cfg_random_seed_explicit = false;
    bool randomize_lane_seed = false;
    unsigned active_random_seed = 1;
    std::mt19937 random_engine;
    LemmaExchange *lemma_exchange = nullptr;
    std::uint64_t lemma_cursor = 0;
    set<Cube, Cube_CMP> inductive_cubes;
    set<Cube, Cube_CMP> inductive_attempted_cubes;
    std::uint64_t shared_published = 0;
    std::uint64_t shared_received = 0;
    std::uint64_t shared_imported = 0;
    std::uint64_t shared_rejected = 0;
    std::uint64_t shared_certified = 0;
    std::uint64_t shared_not_inductive = 0;
    bool reverse_lifting_enabled = true;
    bool reverse_lift_restart_requested = false;
    bool counterexample_requires_init = true;
    int nReverseLiftAttempt = 0;
    int nReverseLiftSuccess = 0;
    int nReverseLiftFallback = 0;
    int nReverseLiftRestart = 0;
    int conversion_original_ands = 0;
    int conversion_recognized_xors = 0;
    int conversion_removed_ands = 0;
    long long nEncodedGates = 0;
    long long nEncodedClauses = 0;

    State *cex_state_idx = nullptr;
    bool find_cex = false;
    vector<State *> states, cex_states;

    int nPush, nUnpush, nCore, nCorelen, nCube, nCubelen, nProp, nkCore, nkobl, nobl;

    static bool abs_compare(int a, int b) {
        return abs(a) < std::abs(b);
    }

public:
    // Frame & Cubes
    vector<Frame> frames;
    set<Obligation> obligation_queue;
    Cube core;
    bool top_frame_cannot_reach_bad;

    // Parameters & statistics
    std::chrono::_V2::steady_clock::time_point start_time;
    const int option_mic_tries = 3;
    const int option_ctg_tries = 3;
    const int option_ctg_max_depth = 0;
    const int option_max_joins = 1<<20;
    bool cfg_use_xag, cfg_use_heuristic, cfg_use_punishment, cfg_use_earliest_strengthened_frame;
    bool cfg_assumption_allsort, cfg_stats;
    int cfg_option_ctg_tries, cfg_option_ctg_max_depth, cfg_option_max_joins;
    int cfg_share_inductive_budget;
    int share_inductive_budget_remaining = 0;
    int nQuery, nInductive, nCTI, nCTG, nmic, nCoreReduced, nAbortJoin, nAbortMic;
    int nBlock, nGeneralize, nExtract, nPre;
    double tBlock, tInductive, tGeneralize, tCTG, tPropagate, tExtract, tPre;

    heuristic_Lit_CMP* heuristic_lit_cmp = nullptr;
    int earliest_strengthened_frame;

    // for incremental check
    bool first_incremental_check;

    PDR(Aiger *aiger, int Thread_index, bool acc, bool pr, bool ao,
        PDRDirection direction = PDRDirection::Forward,
        PDRRepresentation representation_override = PDRRepresentation::Default);
    ~PDR(){
        release_frames();
        if(satelite != nullptr) delete satelite;
        if(lift != nullptr) delete lift;
        if(init != nullptr) delete init;
        if(checker != nullptr) delete checker;
        if(inductive_solver != nullptr) delete inductive_solver;
    }

    // Aiger
    void use_xag_for_pdr();
    void use_converted_for_pdr(const aig2xag::ConvertOptions &options);
    void simplify_aiger();
    void initialize(); 
    void translate_to_dimacs();
    void show_uaiger();

    // auxiliary functions
    int prime_var(int var);
    int prime_lit(int lit);


    // Main IC3/PDR framework
    bool is_source(const vector<int> &latches);
    bool is_inductive(SATSolver *solver, const Cube &cube, bool gen_core = false, bool reverse_assumption = true);
    void new_frame();
    bool rec_block_cube();
    bool propagate();    
    bool get_pre_of_target(State *s);
    void extract_state_from_sat(SATSolver *sat, State *s, State *succ, int findex);
    void mic(Cube &cube, int k, int depth);
    bool CTG_down(Cube &cube, int k, int depth, set<int> &required);
    void generalize(Cube &cube, int level);
    bool check_BMC0();
    bool check_BMC1();
    int start(bool cooperative = false);
    int step();
    void finish(int result);
    void set_cancel_flag(std::atomic<bool> *flag);
    void set_lemma_exchange(LemmaExchange *exchange);
    void set_randomized_seed(bool enabled){ randomize_lane_seed = enabled; }
    int check();
    void print_stats(int result);
    bool block_exact_state(const TraceFrame &state, int level, vector<TraceFrame> &trace);
    bool find_bridge(PDR &reverse_pdr, BridgeCandidate &bridge);
    vector<TraceFrame> counterexample_trace() const;
    void set_counterexample_trace(const vector<TraceFrame> &trace);
    bool validate_trace(const vector<TraceFrame> &trace, bool require_init = true) const;
    bool map_trace_from(const PDR &source, const TraceFrame &source_frame,
                        TraceFrame &mapped_frame) const;

    void encode_init_condition(SATSolver *s);   // I
    void encode_bad_state(SATSolver *s);        // Bad cone, used for test SAT?[I/\-B]
    void encode_source_condition(SATSolver *s);
    void encode_target_condition(SATSolver *s, bool primed);
    void encode_not_target_clause(SATSolver *s, bool primed);
    void assume_target(SATSolver *s, bool primed);
    void encode_translation(SATSolver *s, bool cons = true);      // Latches' Cone + Bad' cone, -Bad must hold
    void encode_lift(SATSolver *s);
    void encode_gate(SATSolver *s, const And &g, int gate_type);
    void encode_gate_cone(SATSolver *s, set<int> &lit_set);
    void encode_gate_cone_with_prime(SATSolver *s, set<int> &lit_set, set<int> &prime_lit_set);

    void clear_po();
    void release_frames();
    void add_cube(Cube &cube, int k, bool to_all=true, bool ispropagate = false,
                  int prtimes = 0);
    int  depth(){return frames.size() - 2;}
    bool cube_is_null(Cube &c){return c.size() == 0;}
    bool state_is_null(State *s){return s->latches.size() == 0;}
    double get_runtime();
    bool is_reverse() const { return direction == PDRDirection::Reverse; }
    const char *direction_name() const { return is_reverse() ? "reverse" : "forward"; }
    const char *representation_name() const;
    bool cancellation_pending() const;

    // log
    void show_aag();
    void show_state(State *s);
    string return_state(State *s);
    string return_input(State *s);
    string return_latch(State *s);
    void show_witness();
    void log_witness();
    void show_PO();
    void show_variables();
    void show_lit(int l) const;
    void show_litvec(vector<int> &lv) const;
    string return_litvec(vector<int> &lv) const;
    void show_frames();

    //heuristic function
    void initialize_heuristic();
    void restart_heuristic();
    void updateLitOrder(Cube &cube, int level);

private:
    static int terminate_solver(void *state);
    void configure_solver(SATSolver *solver);
    bool cube_to_canonical(const Cube &cube, Cube &canonical) const;
    bool cube_from_canonical(const Cube &canonical, Cube &cube) const;
    void ensure_inductive_solver();
    bool maybe_certify_inductive_cube(Cube cube);
    bool certify_inductive_cube(Cube cube);
    bool install_inductive_cube(Cube cube, bool publish);
    void publish_inductive_cube(const Cube &cube);
    void import_shared_lemmas();
    bool finalize_counterexample();
    void restart_search_frames();
};
