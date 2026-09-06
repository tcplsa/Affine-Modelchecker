#pragma once

#include <chrono>
#include <algorithm>
#include <fstream>
#include <random>
#include <set>
#include <unordered_map>
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
    double priority;
    Obligation(State *s, int k, int d, int t, double p = 0.0):
        state(s),frame_k(k),depth(d),priority(p){
        if(t > 0)
            thread_index = t;
        else 
            thread_index = 1;
    }
    bool operator<(const Obligation &b) const{
        if (frame_k < b.frame_k) return true;       // prefer lower levels (required)
        if (frame_k > b.frame_k) return false;
        if (priority < b.priority) return true;
        if (priority > b.priority) return false;
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
    LoweredXag = 3,
    Auto = 4
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
    struct GuardedAffineMode {
        vector<int> guard;
        vector<int> support;
        char rhs = 0;
    };

    struct AffineIslandSummary {
        int root = 0;
        vector<int> support;
        vector<int> xor_variables;
        char rhs = 0;
        int xor_nodes = 0;
    };

    struct AffineParityInvariant {
        vector<int> guard;
        vector<int> support;
        char rhs = 0;
    };

    Aiger *uaiger;
    
    // the interal data structure for Aiger (in CNF dimacs format).
    int thread_index;
    
    // for IC3
    CNFSimplifier *satelite = nullptr;
    CNFSimplifier *satelite2 = nullptr;
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
    PDRRepresentation requested_representation = PDRRepresentation::Xag;
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
    std::uint64_t early_certify_attempted = 0;
    std::uint64_t early_certify_succeeded = 0;
    string invariant_import_path;
    string invariant_export_path;
    string invariant_snapshot_path;
    std::uint64_t invariant_import_read = 0;
    std::uint64_t invariant_import_installed = 0;
    std::uint64_t invariant_import_rejected = 0;
    std::uint64_t invariant_import_pruned = 0;
    std::uint64_t invariant_exported = 0;
    std::uint64_t invariant_snapshot_exported = 0;
    bool invariant_proves_target = false;
    bool invariant_same_transition = false;
    bool reverse_lifting_enabled = true;
    bool reverse_lift_restart_requested = false;
    bool counterexample_requires_init = true;
    int nReverseLiftAttempt = 0;
    int nReverseLiftSuccess = 0;
    int nReverseLiftFallback = 0;
    int nReverseLiftRestart = 0;
    int conversion_original_ands = 0;
    int conversion_candidate_xors = 0;
    int conversion_recognized_xors = 0;
    int conversion_removed_ands = 0;
    string conversion_xag_policy = "none";
    double conversion_xag_fraction = 1.0;
    unsigned conversion_xag_seed = 1;
    double conversion_xag_deep_fraction = 0.5;
    int conversion_xag_min_fanout = 2;
    bool conversion_xag_allowlist = false;
    int conversion_xag_allowlist_size = 0;
    double conversion_runtime = 0.0;
    bool auto_selector_active = false;
    bool auto_selector_use_xag = false;
    int auto_selector_next_depth = 0;
    int auto_selector_recognized_xors = 0;
    int auto_selector_min_next_depth = 120;
    double auto_selector_and_reduction = 0.0;
    double auto_selector_min_and_reduction = 0.12;
    int affine_next_count = 0;
    int affine_next_rank = 0;
    long long affine_support_sum = 0;
    int affine_support_max = 0;
    bool affine_summary_enabled = false;
    vector<vector<int> > affine_next_supports;
    vector<char> affine_next_valid;
    vector<char> affine_next_rhs;
    long long affine_summary_equations = 0;
    long long affine_summary_literals = 0;
    bool affine_island_summary_enabled = false;
    bool affine_island_replace_enabled = false;
    bool affine_island_dag_enabled = false;
    bool affine_island_validation_attempted = false;
    bool affine_island_validation_passed = false;
    double affine_island_validation_seconds = 0.0;
    int affine_island_min_xors = 4;
    int affine_island_max_support = 512;
    vector<AffineIslandSummary> affine_island_summaries;
    long long affine_island_xor_nodes = 0;
    long long affine_island_support_sum = 0;
    int affine_island_support_max = 0;
    long long affine_island_encoded_equations = 0;
    long long affine_island_encoded_literals = 0;
    long long affine_island_replaced_gates = 0;
    bool cmsat_boundary_bve_enabled = false;
    vector<int> cmsat_translation_bve_cnf;
    vector<int> cmsat_lift_bve_cnf;
    long long cmsat_boundary_bve_runs = 0;
    long long cmsat_boundary_bve_candidates = 0;
    long long cmsat_boundary_bve_eliminated = 0;
    long long cmsat_boundary_bve_raw_clauses = 0;
    long long cmsat_boundary_bve_simplified_clauses = 0;
    bool guarded_affine_enabled = false;
    bool guarded_affine_auto_enabled = false;
    double guarded_affine_auto_min_coverage = 0.75;
    int guarded_affine_max_controls = 2;
    vector<int> guarded_affine_controls;
    vector<vector<GuardedAffineMode> > guarded_affine_next_modes;
    vector<char> guarded_affine_next_valid;
    int guarded_affine_next_count = 0;
    long long guarded_affine_modes = 0;
    long long guarded_affine_support_sum = 0;
    int guarded_affine_support_max = 0;
    int guarded_affine_selection_gain = 0;
    int guarded_affine_selection_next_roots = 0;
    int guarded_affine_selection_property_roots = 0;
    long long guarded_affine_encoded_modes = 0;
    long long guarded_affine_guard_clauses = 0;
    bool guarded_affine_validation_attempted = false;
    bool guarded_affine_validation_passed = false;
    bool affine_invariants_enabled = false;
    bool affine_invariants_direct_check = false;
    // Keep guarded rows opt-in: each replayed row adds an auxiliary XOR to
    // every incremental CMSat query.
    bool affine_invariants_conditioned_feedback = false;
    // Zero keeps all verified rows.  A positive budget keeps short rows first.
    int affine_invariants_conditioned_feedback_max_rows = 0;
    // Guard discovery is combinatorial.  Only attempt it automatically when
    // the unguarded affine pass already explains most next-state latches.
    double affine_invariants_guarded_min_coverage = 0.75;
    int affine_invariants_max_width = 32;
    bool affine_invariants_model_validated = false;
    bool affine_invariants_prove_target = false;
    bool affine_invariants_guarded = false;
    bool affine_invariants_conditioned = false;
    bool affine_invariants_partial = false;
    int affine_invariants_modes = 0;
    int affine_invariants_tracked_latches = 0;
    int affine_invariants_abstracted_latches = 0;
    int affine_invariants_reachable_rank = 0;
    int affine_invariants_closure_rounds = 0;
    int affine_invariants_reachable_modes = 0;
    long long affine_invariants_support_sum = 0;
    int affine_invariants_support_max = 0;
    long long affine_invariants_encoded = 0;
    long long affine_invariants_conditioned_encoded = 0;
    long long affine_invariants_conditioned_clauses = 0;
    int affine_invariants_conditioned_feedback_selected = 0;
    int affine_invariants_selected = 0;
    double affine_invariants_seconds = 0.0;
    vector<AffineParityInvariant> affine_parity_invariants;
    bool cadical_affine_hints_enabled = false;
    long long cadical_affine_hint_equations = 0;
    long long cadical_affine_hint_clauses = 0;
    bool affine_auto_enabled = false;
    int affine_auto_cadical_max_support = 32;
    string affine_auto_solver;
    string affine_auto_choice = "fallback";
    int cmsat_gauss_disable_depth = -1;
    bool cmsat_gauss_auto_gate = false;
    bool cmsat_gauss_telemetry = false;
    int cmsat_gauss_auto_min_depth = 4;
    std::uint64_t cmsat_gauss_auto_min_checks = 10000;
    int cmsat_gauss_auto_max_useful_ppm = 1000;
    std::uint64_t cmsat_gauss_auto_max_avg_matrix_cells = 1000000;
    int cmsat_gauss_auto_min_row_xors_per_useful = 0;
    int cmsat_gauss_auto_patience = 2;
    int cmsat_gauss_auto_low_windows = 0;
    SATGaussStats cmsat_gauss_previous;
    SATGaussStats cmsat_gauss_final;
    bool cmsat_gauss_disabled = false;
    int cmsat_gauss_disabled_at_depth = -1;
    std::uint64_t cmsat_gauss_disabled_solvers = 0;
    long long nEncodedGates = 0;
    long long nEncodedClauses = 0;
    bool cfg_phase_stats = false;
    int trace_solver_sequence = 0;
    double tTranslationBuild = 0.0;
    double tTranslationSimplify = 0.0;
    double tTranslationInject = 0.0;
    double tLiftBuild = 0.0;
    double tLiftSimplify = 0.0;
    double tLiftInject = 0.0;
    double tBmc0Solve = 0.0;
    double tFirstPreSolve = 0.0;
    double tFirstLiftSolve = 0.0;
    int translationRawVars = 0;
    int translationRawClauses = 0;
    int translationSimplifiedVars = 0;
    int translationSimplifiedClauses = 0;
    long long translationSimplifiedLiterals = 0;
    string minisat_freeze_policy = "none";
    int minisat_freeze_fanout = 4;
    string cnf_preprocessor = "minisat";
    int minisat_grow = 0;
    int minisat_clause_limit = 20;
    string minisat_elim_order = "legacy";
    string minisat_translation_elim_order = "legacy";
    string minisat_lift_elim_order = "legacy";
    int minisat_width_weight = 0;
    int minisat_translation_width_weight = 0;
    int minisat_lift_width_weight = 0;
    bool minisat_asymm = false;
    bool minisat_rcheck = false;
    int cadical_pre_rounds = 3;
    int cadical_elimprod = 1;
    int cadical_elimsum = 1;
    int translationFrozenGateVars = 0;
    int liftRawVars = 0;
    int liftRawClauses = 0;
    int liftSimplifiedVars = 0;
    int liftSimplifiedClauses = 0;
    long long liftSimplifiedLiterals = 0;
    int liftFrozenGateVars = 0;
    std::ofstream semantic_trace;
    std::uint64_t semantic_sequence = 0;
    std::uint64_t semantic_query_sequence = 0;
    std::uint64_t semantic_max_events = 0;
    std::unordered_map<SATSolver *, std::uint64_t> semantic_last_query;
    std::ofstream decision_trace;
    std::uint64_t decision_sequence = 0;
    std::uint64_t decision_max_events = 0;
    bool decision_trace_lemmas = true;
    int decision_distance_max_depth = 32;
    vector<int> latch_bad_distance;
    vector<int> latch_bad_comb_distance;
    vector<int> latch_init_value;
    vector<std::uint64_t> latch_mic_attempts;
    vector<std::uint64_t> latch_mic_successes;
    vector<std::uint64_t> latch_mic_failures;
    vector<std::uint64_t> latch_mic_query_sum;
    vector<double> latch_mic_elapsed_sum;
    vector<std::uint64_t> latch_lemma_occurrences;
    vector<std::uint64_t> latch_push_occurrences;
    vector<std::uint64_t> latch_push_distance_sum;
    string first_pre_phase_mode = "default";
    unsigned first_pre_phase_seed = 1;
    string predecessor_phase_mode = "default";
    unsigned predecessor_phase_seed = 1;
    std::uint64_t predecessor_phase_queries = 0;
    string mic_order_mode = "legacy";
    string mic_effective_order_mode = "legacy";
    string obligation_order_mode = "legacy";
    double mic_feedback_weight = 1.0;
    int distance_bad_support_latches = 0;
    int distance_reached_latches = 0;
    int distance_max_observed = -1;
    bool distance_truncated = false;
    int progress_stats_seconds = 0;
    std::chrono::_V2::steady_clock::time_point next_progress_stats;
    string active_query_role = "idle";

    void maybe_print_progress_stats(const char *query_role);
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
    const int option_ctg_max_depth = 1;
    const int option_max_joins = 1<<20;
    bool cfg_use_xag, cfg_use_heuristic, cfg_use_punishment, cfg_use_earliest_strengthened_frame;
    bool cfg_assumption_allsort, cfg_stats;
    int cfg_option_ctg_tries, cfg_option_ctg_max_depth, cfg_option_max_joins;
    int cfg_share_inductive_budget;
    bool cfg_certify_early = false;
    int cfg_certify_early_max_cube = 12;
    int cfg_certify_early_min_push = 2;
    int share_inductive_budget_remaining = 0;
    int nQuery, nInductive, nCTI, nCTG, nmic, nCoreReduced, nAbortJoin, nAbortMic;
    int nBlock, nGeneralize, nExtract, nPre;
    std::uint64_t nLemmaAdded, nLemmaLiterals;
    std::uint64_t nBlockLemmaAdded, nBlockLemmaLiterals;
    std::uint64_t nPushLemmaAdded, nPushLemmaLiterals;
    std::uint64_t nFrameCore, nFrameCoreInputLiterals, nFrameCoreLiterals;
    std::uint64_t nLiftCore, nLiftCoreInputLiterals, nLiftCoreLiterals;
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
        if(satelite2 != nullptr) delete satelite2;
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
    bool is_source(const vector<int> &latches, const vector<int> &inputs);
    bool is_inductive(SATSolver *solver, const Cube &cube, bool gen_core = false,
                      bool reverse_assumption = true,
                      const char *query_kind = "inductive",
                      int query_frame = -1, int query_depth = -1);
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
    void probe_preprocessing();
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
    void analyze_affine_transition();
    void analyze_affine_islands();
    bool validate_affine_islands();
    void analyze_guarded_affine_transition();
    bool validate_guarded_affine_transition();
    void analyze_affine_invariants();
    void encode_affine_parity_invariants(SATSolver *s, bool current,
                                         bool primed);
    bool encode_affine_next_summary(SATSolver *s, int latch_index);
    void encode_affine_hints_cnf(SATSolver *s);
    void maybe_disable_cmsat_gauss(int next_frame);
    SATGaussStats aggregate_cmsat_gauss_stats() const;
    void encode_xor_cnf(SATSolver *s, const vector<int> &equation, bool rhs);
    void encode_affine_island_summaries(SATSolver *s, const set<int> &cone,
                                        bool primed);
    void encode_gate_cone(SATSolver *s, set<int> &lit_set);
    void encode_gate_cone_with_prime(SATSolver *s, set<int> &lit_set, set<int> &prime_lit_set);
    void encode_gate_cone_with_prime_boundary_bve(
        SATSolver *s, set<int> &lit_set, set<int> &prime_lit_set,
        vector<int> &cached_cnf);
    int freeze_structural_variables(CNFSimplifier *s, const set<int> &lit_set,
                                    const set<int> &prime_lit_set);

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
    void configure_solver(SATSolver *solver, const string &role = "solver");
    bool cube_to_canonical(const Cube &cube, Cube &canonical) const;
    bool cube_from_canonical(const Cube &canonical, Cube &cube) const;
    void ensure_inductive_solver();
    vector<int> build_cadical_variable_order(const vector<int> &cnf,
                                              const char *phase) const;
    string cadical_variable_order_mode(const char *phase) const;
    void apply_cadical_variable_order(SATSolver *solver, const vector<int> &cnf,
                                      const char *phase) const;
    vector<int> first_pre_phase_literals() const;
    vector<int> predecessor_phase_literals(const Cube *target,
                                            std::uint64_t query) const;
    bool maybe_certify_inductive_cube(Cube cube);
    bool certify_inductive_cube(Cube cube);
    bool install_inductive_cube(Cube cube, bool publish);
    void publish_inductive_cube(const Cube &cube);
    void import_shared_lemmas();
    bool import_external_invariant();
    void export_fixed_point(int empty_frame);
    void export_inductive_snapshot();
    bool finalize_counterexample();
    void restart_search_frames();
    std::uint64_t semantic_hash(const vector<int> &literals) const;
    void semantic_event(const char *event, std::uint64_t query_id,
                        const char *role, const char *kind,
                        int frame, int depth, const vector<int> *literals,
                        int output_size, int result,
                        const SATSearchStats &before = SATSearchStats(),
                        const SATSearchStats &after = SATSearchStats());
    std::uint64_t semantic_query(SATSolver *solver, const char *role,
                                 const char *kind, int frame, int depth,
                                 const vector<int> &literals, int result,
                                 const SATSearchStats &before,
                                 const SATSearchStats &after);
    int latch_index_from_literal(int literal) const;
    double obligation_priority(const State *state) const;
    Obligation make_obligation(State *state, int frame, int depth) const;
    void initialize_distance_metadata();
    void decision_event(const char *event, int frame, int recursion_depth,
                        int literal, int cube_before, int cube_after,
                        int result, double elapsed_seconds,
                        int query_delta, int ctg_delta);
};
