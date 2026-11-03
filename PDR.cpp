#include "PDR.hpp"
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <limits>
#include <memory>
#include <queue>
#include <functional>
#include <stdexcept>
#include <tuple>
#include <unordered_map>
#include <unordered_set>

namespace {
bool env_bool(const char *name, bool default_value){
    const char *value = std::getenv(name);
    if(value == nullptr)
        return default_value;
    string s(value);
    return !(s == "0" || s == "false" || s == "FALSE" || s == "off" || s == "OFF");
}

int env_int(const char *name, int default_value){
    const char *value = std::getenv(name);
    if(value == nullptr)
        return default_value;
    return std::atoi(value);
}

double env_double(const char *name, double default_value){
    const char *value = std::getenv(name);
    if(value == nullptr)
        return default_value;
    return std::atof(value);
}

string env_lane_value(const char *name, int lane, const string &default_value){
    const char *value = std::getenv(name);
    if(value == nullptr || lane < 0)
        return default_value;
    std::stringstream stream(value);
    string item;
    for(int index = 0; std::getline(stream, item, ','); ++index){
        if(index == lane)
            return item.empty() ? default_value : item;
    }
    return default_value;
}

bool env_is(const char *name, const char *expected){
    const char *value = std::getenv(name);
    if(value == nullptr)
        return false;
    return string(value) == expected;
}

thread_local string active_pdr_solver;

SATSolver *new_pdr_solver(){
    const string backend = active_pdr_solver.empty()
        ? (std::getenv("MC_PDR_SOLVER") == nullptr ? "cadical"
                                                     : std::getenv("MC_PDR_SOLVER"))
        : active_pdr_solver;
    if(backend == "minisat")
        return new minisatCore();
    if(backend == "cmsat")
        return new CMSatSolver();
    return new CaDiCaL();
}

unsigned random_process_seed(){
    static const unsigned seed = []{
        std::random_device device;
        std::uint64_t ticks = static_cast<std::uint64_t>(
            std::chrono::high_resolution_clock::now().time_since_epoch().count());
        unsigned mixed = device() ^ static_cast<unsigned>(ticks)
                         ^ static_cast<unsigned>(ticks >> 32);
        return mixed == 0 ? 1u : mixed;
    }();
    return seed;
}

struct ScopedTimer{
    double *target;
    std::chrono::steady_clock::time_point start;
    ScopedTimer(double *target): target(target), start(std::chrono::steady_clock::now()) {}
    ~ScopedTimer(){
        if(target == nullptr)
            return;
        std::chrono::duration<double> elapsed = std::chrono::steady_clock::now() - start;
        *target += elapsed.count();
    }
};
}

Frame::Frame(){
    solver = new_pdr_solver();
    cubes.clear();
}

PDR::PDR(Aiger *aiger, int Thread_index, bool acc, bool pr, bool ao,
         PDRDirection search_direction, PDRRepresentation representation_override):
    Aiger(*aiger),
    thread_index(Thread_index),
    use_acc(acc),
    use_pr(pr),
    use_plusone_count(ao),
    direction(search_direction){
    const bool constructor_trace = env_bool("MC_PDR_CONSTRUCTOR_TRACE", false);
    auto trace_constructor = [&](const char *phase,
                                 const std::chrono::steady_clock::time_point &start){
        if(!constructor_trace)
            return;
        const double elapsed = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - start).count();
        cerr << "c PDR_CONSTRUCTOR phase=" << phase
             << " elapsed=" << elapsed << endl;
    };
    auto conversion_start = std::chrono::steady_clock::now();
    conversion_original_ands = aiger->num_ands;
    requested_representation = representation_override == PDRRepresentation::Default
        ? (env_bool("MC_PDR_XAG", aiger->use_xag_for_pdr)
            ? PDRRepresentation::Xag : PDRRepresentation::Aig)
        : representation_override;
    representation = requested_representation;
    if(representation == PDRRepresentation::Auto){
        auto_selector_active = true;
        auto_selector_min_next_depth = env_int(
            "MC_PDR_AUTO_MIN_NEXT_DEPTH", auto_selector_min_next_depth);
        auto_selector_min_and_reduction = env_double(
            "MC_PDR_AUTO_MIN_AND_REDUCTION", auto_selector_min_and_reduction);
        aig2xag::AutoSelectResult selection = aig2xag::select_for_pdr(
            *this, auto_selector_min_next_depth, auto_selector_min_and_reduction);
        auto_selector_use_xag = selection.use_xag;
        auto_selector_next_depth = selection.next_depth;
        auto_selector_recognized_xors = selection.recognized_xors;
        auto_selector_and_reduction = selection.estimated_and_reduction;
        representation = selection.use_xag
            ? PDRRepresentation::Xag : PDRRepresentation::Aig;
    }
    cfg_use_xag = representation == PDRRepresentation::Xag
        || representation == PDRRepresentation::LoweredXag;
    if(representation == PDRRepresentation::Xag){
        use_xag_for_pdr();
    }else if(representation == PDRRepresentation::CompactAig){
        aig2xag::ConvertOptions options;
        options.recognize_xors = false;
        use_converted_for_pdr(options);
    }else if(representation == PDRRepresentation::LoweredXag){
        aig2xag::ConvertOptions options;
        options.lower_xors_to_ands = true;
        use_converted_for_pdr(options);
    }
    conversion_runtime = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - conversion_start).count();
    trace_constructor("representation", conversion_start);
    affine_island_summary_enabled = env_bool(
        "MC_PDR_AFFINE_ISLAND_SUMMARY", false);
    affine_island_replace_enabled = env_bool(
        "MC_PDR_AFFINE_ISLAND_REPLACE", false);
    affine_island_dag_enabled = env_bool(
        "MC_PDR_AFFINE_ISLAND_DAG", false);
    cmsat_boundary_bve_enabled = env_bool(
        "MC_PDR_CMSAT_BOUNDARY_BVE", false);
    if(affine_island_replace_enabled)
        affine_island_summary_enabled = true;
    affine_island_min_xors = std::max(2, env_int(
        "MC_PDR_AFFINE_ISLAND_MIN_XORS", affine_island_min_xors));
    affine_island_max_support = std::max(3, env_int(
        "MC_PDR_AFFINE_ISLAND_MAX_SUPPORT", affine_island_max_support));
    auto affine_transition_start = std::chrono::steady_clock::now();
    analyze_affine_transition();
    trace_constructor("affine-transition", affine_transition_start);
    auto affine_island_start = std::chrono::steady_clock::now();
    const bool affine_island_telemetry = env_bool(
        "MC_PDR_AFFINE_ISLAND_TELEMETRY", false);
    if(affine_island_summary_enabled || affine_island_telemetry)
        analyze_affine_islands();
    trace_constructor("affine-islands", affine_island_start);
    if(affine_island_summary_enabled
       && env_bool("MC_PDR_AFFINE_ISLAND_VALIDATE", false)){
        affine_island_validation_attempted = true;
        const auto validation_start = std::chrono::steady_clock::now();
        affine_island_validation_passed = validate_affine_islands();
        affine_island_validation_seconds = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - validation_start).count();
        if(!affine_island_validation_passed){
            cerr << "Warning: affine-island validation failed; disabling "
                 << "island summaries." << endl;
            affine_island_summary_enabled = false;
            affine_island_replace_enabled = false;
        }
    }
    affine_summary_enabled = env_bool("MC_PDR_AFFINE_SUMMARY", false);
    guarded_affine_enabled = env_bool("MC_PDR_GUARDED_AFFINE", false);
    affine_invariants_enabled = env_bool(
        "MC_PDR_AFFINE_INVARIANTS", false);
    affine_invariants_direct_check = env_bool(
        "MC_PDR_AFFINE_INVARIANT_DIRECT_CHECK", false);
    affine_invariants_conditioned_feedback = env_bool(
        "MC_PDR_AFFINE_INVARIANT_CONDITIONED_FEEDBACK", false);
    affine_invariants_conditioned_feedback_max_rows = std::max(0, env_int(
        "MC_PDR_AFFINE_INVARIANT_CONDITIONED_FEEDBACK_MAX_ROWS",
        affine_invariants_conditioned_feedback_max_rows));
    affine_invariants_guarded_min_coverage = std::max(0.0, std::min(1.0,
        env_double("MC_PDR_AFFINE_INVARIANT_GUARDED_MIN_COVERAGE",
                   affine_invariants_guarded_min_coverage)));
    affine_invariants_max_width = std::max(1, env_int(
        "MC_PDR_AFFINE_INVARIANT_MAX_WIDTH", affine_invariants_max_width));
    guarded_affine_auto_enabled = env_bool(
        "MC_PDR_GUARDED_AFFINE_AUTO", false);
    guarded_affine_auto_min_coverage = env_double(
        "MC_PDR_GUARDED_AFFINE_AUTO_MIN_COVERAGE",
        guarded_affine_auto_min_coverage);
    guarded_affine_max_controls = env_int(
        "MC_PDR_GUARDED_AFFINE_MAX_CONTROLS",
        guarded_affine_max_controls);
    const double plain_affine_coverage = num_latches == 0 ? 0.0
        : static_cast<double>(affine_next_count) / num_latches;
    const bool invariant_guard_search = affine_invariants_enabled
        && affine_next_count < num_latches
        && plain_affine_coverage >= affine_invariants_guarded_min_coverage;
    if(guarded_affine_enabled || guarded_affine_auto_enabled
       || invariant_guard_search){
        auto guarded_affine_start = std::chrono::steady_clock::now();
        if(guarded_affine_enabled)
            affine_summary_enabled = true;
        analyze_guarded_affine_transition();
        trace_constructor("guarded-affine", guarded_affine_start);
    }
    cadical_affine_hints_enabled = env_bool(
        "MC_PDR_CADICAL_AFFINE_HINTS", false);
    affine_auto_enabled = env_bool("MC_PDR_AFFINE_AUTO", false);
    affine_auto_cadical_max_support = env_int(
        "MC_PDR_AFFINE_CADICAL_MAX_SUPPORT",
        affine_auto_cadical_max_support);
    if(affine_auto_enabled && num_latches > 0
       && affine_next_count == num_latches
       && affine_next_rank == num_latches){
        const double average_support = static_cast<double>(affine_support_sum)
            / affine_next_count;
        if(average_support <= affine_auto_cadical_max_support){
            affine_auto_solver = "cadical";
            affine_auto_choice = "cadical-hints";
            cadical_affine_hints_enabled = true;
            affine_summary_enabled = false;
        }else{
            affine_auto_solver = "cmsat";
            affine_auto_choice = "cmsat-gauss-summary";
            affine_summary_enabled = true;
            cadical_affine_hints_enabled = false;
        }
    }
    if(guarded_affine_auto_enabled && affine_auto_solver.empty()
       && num_latches > 0
       && static_cast<double>(guarded_affine_next_count) / num_latches
            >= guarded_affine_auto_min_coverage){
        guarded_affine_enabled = true;
        affine_summary_enabled = true;
        affine_auto_solver = "cmsat";
        affine_auto_choice = "cmsat-gauss-guarded-summary";
        cadical_affine_hints_enabled = false;
    }
    if(guarded_affine_enabled
       && env_bool("MC_PDR_GUARDED_AFFINE_VALIDATE", false)){
        auto guarded_validation_start = std::chrono::steady_clock::now();
        guarded_affine_validation_attempted = true;
        guarded_affine_validation_passed = validate_guarded_affine_transition();
        if(!guarded_affine_validation_passed){
            cerr << "Warning: guarded-affine transition validation failed; "
                 << "falling back to the gate-level encoding." << endl;
            guarded_affine_enabled = false;
            affine_summary_enabled = env_bool("MC_PDR_AFFINE_SUMMARY", false);
        }
        trace_constructor("guarded-validation", guarded_validation_start);
    }
    if(affine_invariants_enabled)
        analyze_affine_invariants();
    cmsat_gauss_disable_depth = env_int(
        "MC_PDR_CMSAT_GAUSS_DISABLE_DEPTH", cmsat_gauss_disable_depth);
    cmsat_gauss_auto_gate = env_bool(
        "MC_PDR_CMSAT_GAUSS_AUTO_GATE", cmsat_gauss_auto_gate);
    cmsat_gauss_telemetry = env_bool(
        "MC_PDR_CMSAT_GAUSS_TELEMETRY", cmsat_gauss_auto_gate);
    cmsat_gauss_auto_min_depth = env_int(
        "MC_PDR_CMSAT_GAUSS_AUTO_MIN_DEPTH", cmsat_gauss_auto_min_depth);
    cmsat_gauss_auto_min_checks = static_cast<std::uint64_t>(std::max(0,
        env_int("MC_PDR_CMSAT_GAUSS_AUTO_MIN_CHECKS",
                static_cast<int>(cmsat_gauss_auto_min_checks))));
    cmsat_gauss_auto_max_useful_ppm = env_int(
        "MC_PDR_CMSAT_GAUSS_AUTO_MAX_USEFUL_PPM",
        cmsat_gauss_auto_max_useful_ppm);
    cmsat_gauss_auto_max_avg_matrix_cells = static_cast<std::uint64_t>(
        std::max(0, env_int("MC_PDR_CMSAT_GAUSS_AUTO_MAX_AVG_MATRIX_CELLS",
            static_cast<int>(cmsat_gauss_auto_max_avg_matrix_cells))));
    cmsat_gauss_auto_min_row_xors_per_useful = env_int(
        "MC_PDR_CMSAT_GAUSS_AUTO_MIN_ROW_XORS_PER_USEFUL",
        cmsat_gauss_auto_min_row_xors_per_useful);
    cmsat_gauss_auto_patience = std::max(1, env_int(
        "MC_PDR_CMSAT_GAUSS_AUTO_PATIENCE", cmsat_gauss_auto_patience));
    cfg_use_heuristic = env_bool("MC_PDR_HEURISTIC", false);
    if(const char *value = std::getenv("MC_PDR_MIC_ORDER"))
        mic_order_mode = value;
    mic_order_mode = env_lane_value(
        "MC_PDR_MIC_ORDER_LANES", thread_index, mic_order_mode);
    static const std::set<string> mic_order_modes = {
        "legacy", "distance-near", "distance-far", "feedback",
        "distance-feedback", "structure-auto"
    };
    if(mic_order_modes.find(mic_order_mode) == mic_order_modes.end()){
        cerr << "Warning: unknown MC_PDR_MIC_ORDER='" << mic_order_mode
             << "'; using legacy." << endl;
        mic_order_mode = "legacy";
    }
    mic_effective_order_mode = mic_order_mode;
    if(const char *value = std::getenv("MC_PDR_OBLIGATION_ORDER"))
        obligation_order_mode = value;
    obligation_order_mode = env_lane_value(
        "MC_PDR_OBLIGATION_ORDER_LANES", thread_index,
        obligation_order_mode);
    static const std::set<string> obligation_order_modes = {
        "legacy", "source-near", "source-far"
    };
    if(obligation_order_modes.find(obligation_order_mode)
       == obligation_order_modes.end()){
        cerr << "Warning: unknown MC_PDR_OBLIGATION_ORDER='"
             << obligation_order_mode << "'; using legacy." << endl;
        obligation_order_mode = "legacy";
    }
    mic_feedback_weight = std::max(
        0.0, env_double("MC_PDR_MIC_FEEDBACK_WEIGHT", mic_feedback_weight));
    decision_distance_max_depth = std::max(
        0, env_int("MC_PDR_DISTANCE_MAX_DEPTH",
                   decision_distance_max_depth));
    cfg_use_punishment = env_bool("MC_PDR_PUNISHMENT", use_punishment);
    cfg_use_earliest_strengthened_frame = env_bool("MC_PDR_EARLIEST", use_earliest_strengthened_frame);
    cfg_assumption_allsort = env_bool("MC_PDR_ASSUMPTION_ALLSORT", assumption_allsort);
    cfg_stats = env_bool("MC_PDR_STATS", false)
        || env_bool("MC_PDR_PREPROCESS_ONLY", false);
    cfg_phase_stats = env_bool("MC_PDR_PHASE_STATS", false);
    cfg_random_seed_explicit = std::getenv("MC_PDR_SEED") != nullptr;
    cfg_random_seed = static_cast<unsigned>(env_int("MC_PDR_SEED", 1));
    const char *first_pre_phase = std::getenv("MC_PDR_FIRST_PRE_PHASE");
    if(first_pre_phase != nullptr && first_pre_phase[0] != '\0')
        first_pre_phase_mode = first_pre_phase;
    first_pre_phase_mode = env_lane_value(
        "MC_PDR_FIRST_PRE_PHASE_LANES", thread_index, first_pre_phase_mode);
    first_pre_phase_seed = static_cast<unsigned>(
        env_int("MC_PDR_FIRST_PRE_PHASE_SEED", cfg_random_seed));
    string lane_phase_seed = env_lane_value(
        "MC_PDR_FIRST_PRE_PHASE_SEEDS", thread_index, "");
    if(!lane_phase_seed.empty())
        first_pre_phase_seed = static_cast<unsigned>(
            std::strtoul(lane_phase_seed.c_str(), nullptr, 10));
    static const std::set<string> first_pre_phase_modes = {
        "default", "zero", "one", "init", "random"
    };
    if(first_pre_phase_modes.find(first_pre_phase_mode) == first_pre_phase_modes.end()){
        cerr << "Warning: unknown MC_PDR_FIRST_PRE_PHASE='" << first_pre_phase_mode
             << "'; using default." << endl;
        first_pre_phase_mode = "default";
    }
    const char *predecessor_phase = std::getenv("MC_PDR_PRE_PHASE");
    if(predecessor_phase != nullptr && predecessor_phase[0] != '\0')
        predecessor_phase_mode = predecessor_phase;
    predecessor_phase_mode = env_lane_value(
        "MC_PDR_PRE_PHASE_LANES", thread_index, predecessor_phase_mode);
    predecessor_phase_seed = static_cast<unsigned>(
        env_int("MC_PDR_PRE_PHASE_SEED", cfg_random_seed));
    string lane_predecessor_seed = env_lane_value(
        "MC_PDR_PRE_PHASE_SEEDS", thread_index, "");
    if(!lane_predecessor_seed.empty())
        predecessor_phase_seed = static_cast<unsigned>(
            std::strtoul(lane_predecessor_seed.c_str(), nullptr, 10));
    static const std::set<string> predecessor_phase_modes = {
        "default", "zero", "one", "init", "target", "opposite",
        "random-static", "random-query"
    };
    if(predecessor_phase_modes.find(predecessor_phase_mode)
       == predecessor_phase_modes.end()){
        cerr << "Warning: unknown MC_PDR_PRE_PHASE='" << predecessor_phase_mode
             << "'; using default." << endl;
        predecessor_phase_mode = "default";
    }
    cfg_option_ctg_tries = env_int("MC_PDR_CTG_TRIES", option_ctg_tries);
    cfg_option_ctg_max_depth = env_int("MC_PDR_CTG_DEPTH", option_ctg_max_depth);
    cfg_option_max_joins = env_int("MC_PDR_MAX_JOINS", option_max_joins);
    const char *freeze_policy = std::getenv("MC_PDR_MINISAT_FREEZE_POLICY");
    if(freeze_policy != nullptr && freeze_policy[0] != '\0')
        minisat_freeze_policy = freeze_policy;
    minisat_freeze_fanout = std::max(
        1, env_int("MC_PDR_MINISAT_FREEZE_FANOUT", minisat_freeze_fanout));
    static const std::set<string> freeze_policies = {
        "none", "all", "high-fanout", "shared", "bad", "next", "xor", "hybrid"
    };
    if(freeze_policies.find(minisat_freeze_policy) == freeze_policies.end()){
        cerr << "Warning: unknown MC_PDR_MINISAT_FREEZE_POLICY='"
             << minisat_freeze_policy << "'; using none." << endl;
        minisat_freeze_policy = "none";
    }
    const char *preprocessor = std::getenv("MC_PDR_PREPROCESSOR");
    if(preprocessor != nullptr && preprocessor[0] != '\0')
        cnf_preprocessor = preprocessor;
    if(cnf_preprocessor != "minisat" && cnf_preprocessor != "cadical"){
        cerr << "Warning: unknown MC_PDR_PREPROCESSOR='" << cnf_preprocessor
             << "'; using minisat." << endl;
        cnf_preprocessor = "minisat";
    }
    minisat_grow = env_int("MC_PDR_MINISAT_GROW", minisat_grow);
    minisat_clause_limit = env_int(
        "MC_PDR_MINISAT_CLAUSE_LIMIT", minisat_clause_limit);
    if(const char *value = std::getenv("MC_PDR_MINISAT_ELIM_ORDER"))
        minisat_elim_order = value;
    minisat_elim_order = env_lane_value(
        "MC_PDR_MINISAT_ELIM_ORDER_LANES", thread_index, minisat_elim_order);
    auto valid_elim_order = [](const string &order){
        return order == "legacy" || order == "low" || order == "high"
            || order == "sum-low" || order == "sum-high";
    };
    if(!valid_elim_order(minisat_elim_order)){
        cerr << "Warning: unknown MC_PDR_MINISAT_ELIM_ORDER='"
             << minisat_elim_order << "'; using legacy." << endl;
        minisat_elim_order = "legacy";
    }
    minisat_translation_elim_order = minisat_elim_order;
    if(const char *value = std::getenv("MC_PDR_MINISAT_TRANSLATION_ELIM_ORDER"))
        minisat_translation_elim_order = value;
    minisat_translation_elim_order = env_lane_value(
        "MC_PDR_MINISAT_TRANSLATION_ELIM_ORDER_LANES", thread_index,
        minisat_translation_elim_order);
    if(!valid_elim_order(minisat_translation_elim_order)){
        cerr << "Warning: unknown MC_PDR_MINISAT_TRANSLATION_ELIM_ORDER='"
             << minisat_translation_elim_order << "'; using "
             << minisat_elim_order << "." << endl;
        minisat_translation_elim_order = minisat_elim_order;
    }
    minisat_lift_elim_order = minisat_elim_order;
    if(const char *value = std::getenv("MC_PDR_MINISAT_LIFT_ELIM_ORDER"))
        minisat_lift_elim_order = value;
    minisat_lift_elim_order = env_lane_value(
        "MC_PDR_MINISAT_LIFT_ELIM_ORDER_LANES", thread_index,
        minisat_lift_elim_order);
    if(!valid_elim_order(minisat_lift_elim_order)){
        cerr << "Warning: unknown MC_PDR_MINISAT_LIFT_ELIM_ORDER='"
             << minisat_lift_elim_order << "'; using "
             << minisat_elim_order << "." << endl;
        minisat_lift_elim_order = minisat_elim_order;
    }
    minisat_width_weight = std::max(
        0, env_int("MC_PDR_MINISAT_WIDTH_WEIGHT", minisat_width_weight));
    minisat_translation_width_weight = std::max(
        0, env_int("MC_PDR_MINISAT_TRANSLATION_WIDTH_WEIGHT", minisat_width_weight));
    minisat_lift_width_weight = std::max(
        0, env_int("MC_PDR_MINISAT_LIFT_WIDTH_WEIGHT", minisat_width_weight));
    minisat_asymm = env_bool("MC_PDR_MINISAT_ASYMM", minisat_asymm);
    minisat_rcheck = env_bool("MC_PDR_MINISAT_RCHECK", minisat_rcheck);
    cadical_pre_rounds = std::max(
        0, env_int("MC_PDR_CADICAL_PRE_ROUNDS", cadical_pre_rounds));
    cadical_elimprod = env_int("MC_PDR_CADICAL_ELIMPROD", cadical_elimprod);
    cadical_elimsum = env_int("MC_PDR_CADICAL_ELIMSUM", cadical_elimsum);
    cfg_share_inductive_budget = env_int("MC_PDR_SHARE_INDUCTIVE_BUDGET", 8);
    cfg_certify_early = env_bool("MC_PDR_CERTIFY_EARLY", false);
    string certify_early_lane = env_lane_value(
        "MC_PDR_CERTIFY_EARLY_LANES", thread_index,
        cfg_certify_early ? "1" : "0");
    cfg_certify_early = !(certify_early_lane == "0"
        || certify_early_lane == "false" || certify_early_lane == "off");
    cfg_certify_early_max_cube = std::max(
        1, env_int("MC_PDR_CERTIFY_EARLY_MAX_CUBE",
                   cfg_certify_early_max_cube));
    cfg_certify_early_min_push = std::max(
        0, env_int("MC_PDR_CERTIFY_EARLY_MIN_PUSH",
                   cfg_certify_early_min_push));
    if(const char *value = std::getenv("MC_PDR_INVARIANT_IMPORT"))
        invariant_import_path = value;
    if(const char *value = std::getenv("MC_PDR_INVARIANT_EXPORT"))
        invariant_export_path = value;
    if(const char *value = std::getenv("MC_PDR_INVARIANT_SNAPSHOT"))
        invariant_snapshot_path = value;
    invariant_same_transition = env_bool(
        "MC_PDR_INVARIANT_SAME_TRANSITION", false);
    reverse_lifting_enabled = env_bool("MC_PDR_REVERSE_LIFT", true);
    random_engine.seed(cfg_random_seed);
    use_pr = env_bool("MC_PDR_PR", pr);
    use_acc = env_bool("MC_PDR_ACC", acc);
    start_time = std::chrono::steady_clock::now();
    progress_stats_seconds = std::max(
        0, env_int("MC_PDR_PROGRESS_SECONDS", progress_stats_seconds));
    next_progress_stats = start_time;
    nPush = nUnpush = nCore = nCorelen = nCube = nCubelen = nProp = nkCore = nkobl = nobl = 0;
    first_incremental_check = 1;
    satelite_unsat = 0;
    restart_depth = 5;
    const char *semantic_dir = std::getenv("MC_PDR_SEMANTIC_TRACE_DIR");
    if(semantic_dir != nullptr && semantic_dir[0] != '\0'){
        std::ostringstream path;
        path << semantic_dir << "/thread-" << thread_index
             << "-" << direction_name() << "-" << representation_name()
             << ".semantic.tsv";
        semantic_trace.open(path.str().c_str(), std::ios::out | std::ios::trunc);
        if(semantic_trace){
            semantic_max_events = static_cast<std::uint64_t>(std::max(
                1, env_int("MC_PDR_SEMANTIC_TRACE_MAX_EVENTS", 20000)));
            semantic_trace
                << "seq\tevent\tquery_id\trole\tkind\tframe\tdepth"
                << "\tinput_size\toutput_size\tliteral_hash\tresult"
                << "\tconflicts\tdecisions\tpropagations\trestarts\tqueue_size\n";
            semantic_trace.flush();
        }
    }
    const char *decision_dir = std::getenv("MC_PDR_DECISION_TRACE_DIR");
    if(decision_dir != nullptr && decision_dir[0] != '\0'){
        std::ostringstream path;
        path << decision_dir << "/thread-" << thread_index
             << "-" << direction_name() << "-" << representation_name()
             << ".decision.tsv";
        decision_trace.open(path.str().c_str(), std::ios::out | std::ios::trunc);
        if(decision_trace){
            decision_max_events = static_cast<std::uint64_t>(std::max(
                1, env_int("MC_PDR_DECISION_TRACE_MAX_EVENTS", 250000)));
            decision_trace_lemmas = env_bool(
                "MC_PDR_DECISION_TRACE_LEMMAS", decision_trace_lemmas);
            decision_trace
                << "seq\tevent\tframe\trecursion_depth\tliteral\tvariable"
                << "\tlatch_index\tpolarity\tcube_before\tcube_after"
                << "\tbad_distance\tbad_comb_distance\tinit_value"
                << "\tprior_attempts\tprior_successes\tprior_failures"
                << "\tlemma_occurrences\tpush_occurrences"
                << "\tpush_distance_sum\tresult\telapsed_seconds"
                << "\tquery_delta\tctg_delta\tqueue_size\n";
            decision_trace.flush();
        }
    }
}

int PDR::latch_index_from_literal(int literal) const{
    const int first_latch = unprimed_first_dimacs + num_inputs;
    const int index = abs(literal) - first_latch;
    return index >= 0 && index < num_latches ? index : -1;
}

double PDR::obligation_priority(const State *state) const{
    if(state == nullptr || obligation_order_mode == "legacy")
        return 0.0;
    double mismatch = 0.0;
    double total_weight = 0.0;
    for(int literal : state->latches){
        const int index = latch_index_from_literal(literal);
        if(index < 0 || latch_init_value[index] < 0)
            continue;
        const int distance = latch_bad_distance[index];
        if(distance < 0)
            continue;
        const double weight = 1.0 / static_cast<double>(distance + 1);
        total_weight += weight;
        const int value = literal > 0 ? 1 : 0;
        if(value != latch_init_value[index])
            mismatch += weight;
    }
    if(total_weight <= 0.0)
        return 0.0;
    const double normalized = mismatch / total_weight;
    return obligation_order_mode == "source-far" ? -normalized : normalized;
}

Obligation PDR::make_obligation(State *state, int frame, int depth) const{
    return Obligation(
        state, frame, depth, thread_index, obligation_priority(state));
}

void PDR::initialize_distance_metadata(){
    latch_bad_distance.assign(num_latches, -1);
    latch_bad_comb_distance.assign(num_latches, -1);
    latch_init_value.assign(num_latches, -1);
    latch_mic_attempts.assign(num_latches, 0);
    latch_mic_successes.assign(num_latches, 0);
    latch_mic_failures.assign(num_latches, 0);
    latch_mic_query_sum.assign(num_latches, 0);
    latch_mic_elapsed_sum.assign(num_latches, 0.0);
    latch_lemma_occurrences.assign(num_latches, 0);
    latch_push_occurrences.assign(num_latches, 0);
    latch_push_distance_sum.assign(num_latches, 0);

    if((!decision_trace && mic_order_mode == "legacy"
        && obligation_order_mode == "legacy") || num_latches == 0)
        return;

    const int first_latch = unprimed_first_dimacs + num_inputs;
    for(int literal : init_state){
        const int index = latch_index_from_literal(literal);
        if(index >= 0)
            latch_init_value[index] = literal > 0 ? 1 : 0;
    }

    std::unordered_map<int, And> gate_by_output;
    gate_by_output.reserve(ands.size() + xors.size() + ors.size());
    for(const And &gate : ands) gate_by_output.emplace(gate.o, gate);
    for(const And &gate : xors) gate_by_output.emplace(gate.o, gate);
    for(const And &gate : ors) gate_by_output.emplace(gate.o, gate);

    auto collect_latches = [&](const vector<int> &roots,
                               vector<int> *comb_distance){
        vector<pair<int, int> > pending;
        pending.reserve(roots.size());
        for(int literal : roots)
            pending.push_back(make_pair(abs(literal), 0));
        std::unordered_map<int, int> best_gate_depth;
        std::unordered_map<int, int> best_latch_depth;
        while(!pending.empty()){
            const pair<int, int> item = pending.back();
            pending.pop_back();
            const int variable = item.first;
            const int gate_depth = item.second;
            if(variable >= first_latch && variable < first_latch + num_latches){
                const int index = variable - first_latch;
                auto found = best_latch_depth.find(index);
                if(found == best_latch_depth.end() || gate_depth < found->second)
                    best_latch_depth[index] = gate_depth;
                continue;
            }
            auto gate = gate_by_output.find(variable);
            if(gate == gate_by_output.end())
                continue;
            auto seen = best_gate_depth.find(variable);
            if(seen != best_gate_depth.end() && seen->second <= gate_depth)
                continue;
            best_gate_depth[variable] = gate_depth;
            pending.push_back(make_pair(abs(gate->second.i1), gate_depth + 1));
            pending.push_back(make_pair(abs(gate->second.i2), gate_depth + 1));
        }
        vector<int> result;
        result.reserve(best_latch_depth.size());
        for(const auto &entry : best_latch_depth){
            result.push_back(entry.first);
            if(comb_distance != nullptr){
                int &current = (*comb_distance)[entry.first];
                if(current < 0 || entry.second < current)
                    current = entry.second;
            }
        }
        return result;
    };

    vector<int> bad_roots(1, bad);
    vector<int> frontier = collect_latches(bad_roots, &latch_bad_comb_distance);
    for(int index : frontier)
        latch_bad_distance[index] = 0;
    distance_bad_support_latches = static_cast<int>(frontier.size());
    distance_max_observed = frontier.empty() ? -1 : 0;

    for(int distance = 1;
        distance <= decision_distance_max_depth && !frontier.empty(); ++distance){
        vector<int> roots;
        roots.reserve(frontier.size());
        for(int index : frontier)
            roots.push_back(nexts[index]);
        vector<int> support = collect_latches(roots, nullptr);
        vector<int> next_frontier;
        for(int index : support){
            if(latch_bad_distance[index] >= 0)
                continue;
            latch_bad_distance[index] = distance;
            next_frontier.push_back(index);
        }
        if(!next_frontier.empty())
            distance_max_observed = distance;
        frontier.swap(next_frontier);
    }
    distance_truncated = !frontier.empty();
    distance_reached_latches = static_cast<int>(std::count_if(
        latch_bad_distance.begin(), latch_bad_distance.end(),
        [](int distance){ return distance >= 0; }));

    if(mic_order_mode == "structure-auto"){
        const int direct_limit = std::max(2, num_latches / 100);
        if(distance_bad_support_latches <= direct_limit)
            mic_effective_order_mode = "feedback";
        else if(3 * distance_bad_support_latches >= num_latches)
            mic_effective_order_mode = "distance-near";
        else if(distance_truncated)
            mic_effective_order_mode = "distance-far";
        else
            mic_effective_order_mode = "distance-feedback";
    }
}

void PDR::decision_event(const char *event, int frame, int recursion_depth,
                         int literal, int cube_before, int cube_after,
                         int result, double elapsed_seconds,
                         int query_delta, int ctg_delta){
    if(!decision_trace || decision_sequence >= decision_max_events)
        return;
    const int index = latch_index_from_literal(literal);
    const std::uint64_t zero = 0;
    const int unknown = -1;
    ++decision_sequence;
    decision_trace << decision_sequence << '\t' << event
                   << '\t' << frame << '\t' << recursion_depth
                   << '\t' << literal << '\t' << abs(literal)
                   << '\t' << index << '\t' << (literal >= 0 ? 1 : 0)
                   << '\t' << cube_before << '\t' << cube_after
                   << '\t' << (index >= 0 ? latch_bad_distance[index] : unknown)
                   << '\t' << (index >= 0 ? latch_bad_comb_distance[index] : unknown)
                   << '\t' << (index >= 0 ? latch_init_value[index] : unknown)
                   << '\t' << (index >= 0 ? latch_mic_attempts[index] : zero)
                   << '\t' << (index >= 0 ? latch_mic_successes[index] : zero)
                   << '\t' << (index >= 0 ? latch_mic_failures[index] : zero)
                   << '\t' << (index >= 0 ? latch_lemma_occurrences[index] : zero)
                   << '\t' << (index >= 0 ? latch_push_occurrences[index] : zero)
                   << '\t' << (index >= 0 ? latch_push_distance_sum[index] : zero)
                   << '\t' << result << '\t' << std::setprecision(9)
                   << elapsed_seconds << '\t' << query_delta
                   << '\t' << ctg_delta << '\t' << obligation_queue.size()
                   << '\n';
    if(decision_max_events <= 64 || (decision_sequence & 63u) == 0)
        decision_trace.flush();
}

std::uint64_t PDR::semantic_hash(const vector<int> &literals) const{
    std::uint64_t hash = 1469598103934665603ULL;
    for(int literal : literals){
        std::uint32_t value = static_cast<std::uint32_t>(literal);
        for(int shift = 0; shift < 32; shift += 8){
            hash ^= static_cast<unsigned char>((value >> shift) & 0xffu);
            hash *= 1099511628211ULL;
        }
    }
    return hash;
}

void PDR::semantic_event(const char *event, std::uint64_t query_id,
                         const char *role, const char *kind,
                         int frame, int event_depth, const vector<int> *literals,
                         int output_size, int result,
                         const SATSearchStats &before, const SATSearchStats &after){
    if(!semantic_trace || semantic_sequence >= semantic_max_events)
        return;
    ++semantic_sequence;
    semantic_trace << semantic_sequence << '\t' << event << '\t' << query_id
                   << '\t' << role << '\t' << kind
                   << '\t' << frame << '\t' << event_depth
                   << '\t' << (literals == nullptr ? 0 : literals->size())
                   << '\t' << output_size
                   << '\t' << (literals == nullptr ? 0 : semantic_hash(*literals))
                   << '\t' << result
                   << '\t' << (after.conflicts - before.conflicts)
                   << '\t' << (after.decisions - before.decisions)
                   << '\t' << (after.propagations - before.propagations)
                   << '\t' << (after.restarts - before.restarts)
                   << '\t' << obligation_queue.size() << '\n';
    if(semantic_max_events <= 16 || (semantic_sequence & 15u) == 0)
        semantic_trace.flush();
}

std::uint64_t PDR::semantic_query(SATSolver *solver, const char *role,
                                  const char *kind, int frame, int event_depth,
                                  const vector<int> &literals, int result,
                                  const SATSearchStats &before,
                                  const SATSearchStats &after){
    if(!semantic_trace)
        return 0;
    std::uint64_t query_id = ++semantic_query_sequence;
    semantic_last_query[solver] = query_id;
    semantic_event("query", query_id, role, kind, frame, event_depth,
                   &literals, -1, result, before, after);
    return query_id;
}

int PDR::terminate_solver(void *state){
    std::atomic<bool> *flag = static_cast<std::atomic<bool> *>(state);
    return flag != nullptr && flag->load(std::memory_order_relaxed);
}

void PDR::configure_solver(SATSolver *solver, const string &role){
    if(solver == nullptr)
        return;
    if(cmsat_gauss_disabled && solver->disable_gauss())
        ++cmsat_gauss_disabled_solvers;
    if(cancel_requested != nullptr)
        solver->set_terminate(cancel_requested, terminate_solver);
    const char *trace_dir = std::getenv("MC_PDR_QUERY_TRACE_DIR");
    if(trace_dir != nullptr && trace_dir[0] != '\0' && !solver->trace_enabled()){
        std::ostringstream path;
        path << trace_dir << "/thread-" << thread_index
             << "-" << direction_name()
             << "-" << representation_name()
             << "-" << trace_solver_sequence++
             << "-" << role << ".mcpdrq";
        solver->set_trace_file(path.str());
    }
}

SATGaussStats PDR::aggregate_cmsat_gauss_stats() const{
    SATGaussStats total;
    std::unordered_set<const SATSolver *> seen;
    auto add = [&](const SATSolver *solver){
        if(solver == nullptr || !seen.insert(solver).second)
            return;
        SATGaussStats value = solver->gauss_stats();
        total.checks += value.checks;
        total.row_xors += value.row_xors;
        total.propagations += value.propagations;
        total.conflicts += value.conflicts;
        total.matrices += value.matrices;
        total.rows += value.rows;
        total.columns += value.columns;
    };
    for(const Frame &frame : frames)
        add(frame.solver);
    add(lift);
    add(init);
    add(checker);
    add(inductive_solver);
    return total;
}

void PDR::maybe_disable_cmsat_gauss(int next_frame){
    if(cmsat_gauss_disabled)
        return;

    const SATGaussStats current = aggregate_cmsat_gauss_stats();
    auto delta = [](std::uint64_t now, std::uint64_t before){
        return now >= before ? now - before : now;
    };
    const std::uint64_t checks = delta(current.checks,
                                       cmsat_gauss_previous.checks);
    const std::uint64_t row_xors = delta(current.row_xors,
                                         cmsat_gauss_previous.row_xors);
    const std::uint64_t propagations = delta(current.propagations,
                                             cmsat_gauss_previous.propagations);
    const std::uint64_t conflicts = delta(current.conflicts,
                                          cmsat_gauss_previous.conflicts);
    const std::uint64_t useful = propagations + conflicts;
    cmsat_gauss_previous = current;

    const std::uint64_t avg_matrix_cells = current.matrices == 0 ? 0
        : (current.rows / current.matrices)
            * (current.columns / current.matrices);
    const bool oversized_matrix = cmsat_gauss_auto_max_avg_matrix_cells > 0
        && avg_matrix_cells >= cmsat_gauss_auto_max_avg_matrix_cells;
    bool low_value_window = false;
    if(cmsat_gauss_auto_gate
       && next_frame >= cmsat_gauss_auto_min_depth
       && checks >= cmsat_gauss_auto_min_checks){
        const bool low_usefulness = useful * 1000000ULL
            <= checks * static_cast<std::uint64_t>(
                std::max(0, cmsat_gauss_auto_max_useful_ppm));
        const bool enough_row_cost =
            cmsat_gauss_auto_min_row_xors_per_useful <= 0
            || row_xors >= static_cast<std::uint64_t>(
                cmsat_gauss_auto_min_row_xors_per_useful)
                * std::max<std::uint64_t>(1, useful);
        low_value_window = (low_usefulness && enough_row_cost)
            || oversized_matrix;
        cmsat_gauss_auto_low_windows = low_value_window
            ? cmsat_gauss_auto_low_windows + 1 : 0;
    }

    if(cmsat_gauss_telemetry && (checks > 0 || current.matrices > 0)){
        cout << "c CMSAT_GAUSS_WINDOW frame=" << next_frame
             << " checks=" << checks
             << " row_xors=" << row_xors
             << " propagations=" << propagations
             << " conflicts=" << conflicts
             << " useful_ppm="
             << (checks == 0 ? 0 : useful * 1000000ULL / checks)
             << " matrices=" << current.matrices
             << " rows=" << current.rows
             << " columns=" << current.columns
             << " avg_matrix_cells=" << avg_matrix_cells
             << " oversized=" << (oversized_matrix ? 1 : 0)
             << " low_value=" << (low_value_window ? 1 : 0)
             << " low_windows=" << cmsat_gauss_auto_low_windows << endl;
    }

    const bool fixed_depth_due = cmsat_gauss_disable_depth >= 0
        && next_frame >= cmsat_gauss_disable_depth;
    const bool auto_due = cmsat_gauss_auto_gate
        && cmsat_gauss_auto_low_windows >= cmsat_gauss_auto_patience;
    if(!fixed_depth_due && !auto_due)
        return;

    cmsat_gauss_final = current;

    std::uint64_t disabled = 0;
    auto disable = [&](SATSolver *solver){
        if(solver != nullptr && solver->disable_gauss())
            ++disabled;
    };
    for(Frame &frame : frames)
        disable(frame.solver);
    disable(lift);
    disable(init);
    disable(checker);
    disable(inductive_solver);

    // Set the flag even if no matrix has been created yet.  configure_solver
    // will then keep Gaussian disabled for every solver created afterwards.
    cmsat_gauss_disabled = true;
    cmsat_gauss_disabled_at_depth = next_frame;
    cmsat_gauss_disabled_solvers += disabled;
    if(cmsat_gauss_telemetry)
        cout << "c CMSAT_GAUSS_DISABLED frame=" << next_frame
             << " reason=" << (auto_due ? "low-value" : "fixed-depth")
             << " solvers=" << disabled << endl;
}

string PDR::cadical_variable_order_mode(const char *phase) const{
    const char *value = nullptr;
    if(phase != nullptr && string(phase) == "translation")
        value = std::getenv("MC_PDR_CADICAL_ORDER_TRANSLATION");
    else if(phase != nullptr && string(phase) == "lift")
        value = std::getenv("MC_PDR_CADICAL_ORDER_LIFT");
    if(value == nullptr || value[0] == '\0')
        value = std::getenv("MC_PDR_CADICAL_VAR_ORDER");
    return value == nullptr || value[0] == '\0' ? "first" : string(value);
}

vector<int> PDR::build_cadical_variable_order(const vector<int> &cnf,
                                               const char *phase) const{
    string mode = cadical_variable_order_mode(phase);
    vector<int> occurrence;
    std::unordered_set<int> present;
    for(int literal : cnf){
        int var = abs(literal);
        if(var != 0 && present.insert(var).second)
            occurrence.push_back(var);
    }
    if(mode.empty() || mode == "first")
        return occurrence;

    std::unordered_map<int, And> gate_by_output;
    std::unordered_set<int> xor_outputs;
    for(const And &gate : ands)
        gate_by_output.emplace(gate.o, gate);
    for(const And &gate : xors){
        gate_by_output.emplace(gate.o, gate);
        xor_outputs.insert(gate.o);
    }
    for(const And &gate : ors)
        gate_by_output.emplace(gate.o, gate);

    auto cone_distances = [&](const vector<int> &roots){
        std::unordered_map<int, int> distance;
        std::queue<pair<int, int>> pending;
        for(int literal : roots)
            pending.push(make_pair(abs(literal), 0));
        while(!pending.empty()){
            int var = pending.front().first;
            int depth = pending.front().second;
            pending.pop();
            auto known = distance.find(var);
            if(known != distance.end() && known->second <= depth)
                continue;
            distance[var] = depth;
            auto gate = gate_by_output.find(var);
            if(gate == gate_by_output.end())
                continue;
            pending.push(make_pair(abs(gate->second.i1), depth + 1));
            pending.push(make_pair(abs(gate->second.i2), depth + 1));
        }
        return distance;
    };

    vector<int> bad_roots = {bad};
    bad_roots.insert(bad_roots.end(), constraints.begin(), constraints.end());
    vector<int> next_roots = nexts;
    next_roots.insert(next_roots.end(), constraints.begin(), constraints.end());
    const auto bad_distance = cone_distances(bad_roots);
    const auto next_distance = cone_distances(next_roots);

    auto unprime = [&](int var){
        if(var >= primed_first_dimacs
           && var < primed_first_dimacs + num_inputs + num_latches)
            return unprimed_first_dimacs + var - primed_first_dimacs;
        auto found = map_to_unprime.find(var);
        return found == map_to_unprime.end() ? var : found->second;
    };
    auto distance = [](const std::unordered_map<int, int> &distances, int var){
        auto found = distances.find(var);
        return found == distances.end() ? std::numeric_limits<int>::max() : found->second;
    };
    auto role = [&](int var){
        const int base = unprime(var);
        const bool input = base >= unprimed_first_dimacs
            && base < unprimed_first_dimacs + num_inputs;
        const bool latch = base >= unprimed_first_dimacs + num_inputs
            && base < unprimed_first_dimacs + num_inputs + num_latches;
        const int db = distance(bad_distance, base);
        const int dn = distance(next_distance, base);
        const bool in_bad = db != std::numeric_limits<int>::max();
        const bool in_next = dn != std::numeric_limits<int>::max();
        const bool is_xor = xor_outputs.find(base) != xor_outputs.end();
        return std::make_tuple(base, input, latch, db, dn, in_bad, in_next, is_xor);
    };

    std::unordered_map<int, size_t> rank;
    for(size_t i = 0; i < occurrence.size(); ++i)
        rank[occurrence[i]] = i;
    const std::unordered_set<string> supported_modes = {
        "occurrence-reverse", "numeric", "state-first", "state-last",
        "root-first", "leaf-first", "bad-first", "next-first",
        "shared-first", "xor-first", "xor-last", "constraint-first"
    };
    if(supported_modes.find(mode) == supported_modes.end()){
        cerr << "Warning: unknown MC_PDR_CADICAL_VAR_ORDER='" << mode
             << "'; using first occurrence order." << endl;
        return occurrence;
    }
    auto key = [&](int var){
        const auto roles = role(var);
        const int base = std::get<0>(roles);
        const bool input = std::get<1>(roles);
        const bool latch = std::get<2>(roles);
        const int db = std::get<3>(roles);
        const int dn = std::get<4>(roles);
        const bool in_bad = std::get<5>(roles);
        const bool in_next = std::get<6>(roles);
        const bool is_xor = std::get<7>(roles);
        const int inf = std::numeric_limits<int>::max();
        int group = 0;
        int depth = 0;
        if(mode == "occurrence-reverse")
            return std::make_tuple(0, 0, occurrence.size() - 1 - rank[var], base);
        if(mode == "numeric")
            return std::make_tuple(0, 0, static_cast<size_t>(base), base);
        if(mode == "state-first")
            group = latch ? 0 : (input ? 1 : 2);
        else if(mode == "state-last")
            group = (!input && !latch) ? 0 : (input ? 1 : 2);
        else if(mode == "root-first"){
            depth = std::min(db, dn);
            group = depth == inf ? 1 : 0;
            if(depth == inf) depth = 0;
        }else if(mode == "leaf-first"){
            depth = std::min(db, dn);
            group = depth == inf ? 1 : 0;
            if(depth == inf) depth = 0;
            else depth = -depth;
        }else if(mode == "bad-first")
            group = in_bad ? 0 : 1;
        else if(mode == "next-first")
            group = in_next ? 0 : 1;
        else if(mode == "shared-first")
            group = in_bad && in_next ? 0 : 1;
        else if(mode == "xor-first")
            group = is_xor ? 0 : 1;
        else if(mode == "xor-last")
            group = is_xor ? 1 : 0;
        else if(mode == "constraint-first"){
            bool in_constraint = false;
            for(int literal : constraints)
                if(abs(literal) == base){ in_constraint = true; break; }
            group = in_constraint ? 0 : 1;
        }
        return std::make_tuple(group, depth, rank[var], base);
    };
    std::stable_sort(occurrence.begin(), occurrence.end(), [&](int left, int right){
        return key(left) < key(right);
    });
    return occurrence;
}

void PDR::apply_cadical_variable_order(SATSolver *solver, const vector<int> &cnf,
                                       const char *phase) const{
    vector<int> order = build_cadical_variable_order(cnf, phase);
    solver->set_variable_order(order);
    if(cfg_phase_stats){
        cout << "c PDR_VAR_ORDER thread=" << thread_index
             << " phase=" << phase
             << " mode=" << cadical_variable_order_mode(phase)
             << " present=" << order.size() << endl;
    }
}

vector<int> PDR::first_pre_phase_literals() const{
    vector<int> literals;
    if(first_pre_phase_mode == "default")
        return literals;

    std::unordered_map<int, int> initial_sign;
    for(int literal : init_state)
        initial_sign[abs(literal)] = literal < 0 ? -1 : 1;

    std::mt19937 phase_random(first_pre_phase_seed ^ 0x9e3779b9u);
    std::uniform_int_distribution<int> bit(0, 1);
    const int distance = primed_first_dimacs - unprimed_first_dimacs;
    const int state_variables = num_inputs + num_latches;
    literals.reserve(state_variables);
    for(int offset = 0; offset < state_variables; ++offset){
        const int unprimed = unprimed_first_dimacs + offset;
        const int primed = unprimed + distance;
        int sign = -1;
        if(first_pre_phase_mode == "one")
            sign = 1;
        else if(first_pre_phase_mode == "random")
            sign = bit(phase_random) ? 1 : -1;
        else if(first_pre_phase_mode == "init" && offset >= num_inputs){
            auto found = initial_sign.find(unprimed);
            if(found != initial_sign.end())
                sign = found->second;
        }
        literals.push_back(sign * primed);
    }
    return literals;
}

vector<int> PDR::predecessor_phase_literals(const Cube *target,
                                            std::uint64_t query) const{
    vector<int> literals;
    if(predecessor_phase_mode == "default")
        return literals;

    std::unordered_map<int, int> target_sign;
    if(target != nullptr){
        for(int literal : *target)
            target_sign[abs(literal)] = literal < 0 ? -1 : 1;
    }
    std::unordered_map<int, int> initial_sign;
    for(int literal : init_state)
        initial_sign[abs(literal)] = literal < 0 ? -1 : 1;

    std::uint64_t mixed_seed = predecessor_phase_seed ^ 0x9e3779b9u;
    if(predecessor_phase_mode == "random-query"){
        mixed_seed ^= query + 0x9e3779b97f4a7c15ULL
                      + (mixed_seed << 6) + (mixed_seed >> 2);
    }
    std::mt19937 phase_random(static_cast<unsigned>(mixed_seed ^ (mixed_seed >> 32)));
    std::uniform_int_distribution<int> bit(0, 1);
    const int state_variables = num_inputs + num_latches;
    literals.reserve(state_variables);
    for(int offset = 0; offset < state_variables; ++offset){
        const int variable = unprimed_first_dimacs + offset;
        int sign = -1;
        if(predecessor_phase_mode == "one"){
            sign = 1;
        }else if(predecessor_phase_mode == "init" && offset >= num_inputs){
            auto found = initial_sign.find(variable);
            if(found != initial_sign.end())
                sign = found->second;
        }else if(predecessor_phase_mode == "target"
                 || predecessor_phase_mode == "opposite"){
            auto found = target_sign.find(variable);
            if(found == target_sign.end())
                continue;
            sign = predecessor_phase_mode == "target" ? found->second : -found->second;
        }else if(predecessor_phase_mode == "random-static"
                 || predecessor_phase_mode == "random-query"){
            sign = bit(phase_random) ? 1 : -1;
        }
        literals.push_back(sign * variable);
    }
    return literals;
}

void PDR::set_cancel_flag(std::atomic<bool> *flag){
    cancel_requested = flag;
    for(Frame &frame : frames)
        configure_solver(frame.solver, "frame");
    configure_solver(lift, "lift");
    configure_solver(init, "source");
    configure_solver(checker, "checker");
    configure_solver(inductive_solver, "inductive");
}

void PDR::set_lemma_exchange(LemmaExchange *exchange){
    lemma_exchange = exchange;
    if(lemma_exchange != nullptr)
        lemma_cursor = lemma_exchange->subscribe(is_reverse());
}

bool PDR::cancellation_pending() const{
    return cancel_requested != nullptr && cancel_requested->load(std::memory_order_relaxed);
}

//  Log functions
// --------------------------------------------
void PDR::show_state(State *s){
    vector<char> a(num_inputs + num_latches + 2, 'x');
    for(int i : s->inputs)
        a[abs(i)] = (i<0?'0':'1');
    for(int l : s->latches)
        a[abs(l)] = (l<0?'0':'1');

    cout<<'[';
    for(int i=1; i<=num_inputs; ++i)
        cout<<a[1+i];
    cout<<'|';
    for(int l=1; l<=num_latches; ++l)
        cout<<a[1+num_inputs+l];
    cout<<']';
    cout<<endl;
}

string PDR::return_state(State *s){
    vector<char> a(num_inputs + num_latches + 2, 'x');
    for(int i : s->inputs)
        a[abs(i)] = (i<0?'0':'1');
    for(int l : s->trace_latches())
        a[abs(l)] = (l<0?'0':'1');

    string str="";
    str.push_back('[');
    for(int i=1; i<=num_inputs; ++i)
        str.push_back(a[1+i]);
    str.push_back('|');
    for(int l=1; l<=num_latches; ++l)
        str.push_back(a[1+num_inputs+l]);
    str.push_back(']');
    return str;
}

string PDR::return_input(State *s){
    vector<char> a(num_inputs + num_latches + 2, 'x');
    for(int i : s->inputs)
        a[abs(i)] = (i<0?'0':'1');
    for(int l : s->latches)
        a[abs(l)] = (l<0?'0':'1');
    string str="";
    for(int i=1; i<=num_inputs; ++i)
        str.push_back(a[1+i]);
    return str;
}

string PDR::return_latch(State *s){
    vector<char> a(num_inputs + num_latches + 2, 'x');
    for(int i : s->inputs)
        a[abs(i)] = (i<0?'0':'1');
    for(int l : s->trace_latches())
        a[abs(l)] = (l<0?'0':'1');
    string str="";
    for(int l=1; l<=num_latches; ++l)
        str.push_back(a[1+num_inputs+l]);
    return str;
}

void PDR::show_lit(int l) const{
    cout<<(l<0?"-":"")<<variables[abs(l)].name;
}

void PDR::show_litvec(vector<int> &lv) const{
    for(int l:lv){
        show_lit(l);
        cout<<" ";
    }cout<<endl;
}

string PDR::return_litvec(vector<int> &lv) const{
    string str = "";
    for(int l:lv){
        str.append(l<0?"-":"");
        str.append(variables[abs(l)].name);
        str.push_back(' ');
    }
    return str;
}

double PDR::get_runtime(){
    auto stop_time = std::chrono::steady_clock::now();
    std::chrono::duration<double> elapsed_seconds = stop_time - start_time;
    return elapsed_seconds.count();
}

void PDR::maybe_print_progress_stats(const char *query_role){
    if(progress_stats_seconds <= 0
       || (!cfg_stats && invariant_snapshot_path.empty()))
        return;
    auto now = std::chrono::steady_clock::now();
    if(now < next_progress_stats)
        return;
    active_query_role = query_role == nullptr ? "unknown" : query_role;
    print_stats(0);
    export_inductive_snapshot();
    next_progress_stats = now + std::chrono::seconds(progress_stats_seconds);
}

const char *PDR::representation_name() const{
    switch(representation){
    case PDRRepresentation::Aig:
        return "aig";
    case PDRRepresentation::CompactAig:
        return "aig-compact";
    case PDRRepresentation::LoweredXag:
        return "xag-lowered";
    case PDRRepresentation::Auto:
        return "auto";
    case PDRRepresentation::Xag:
    case PDRRepresentation::Default:
        return "xag";
    }
    return "unknown";
}

void PDR::print_stats(int result){
    if(!cfg_stats)
        return;

    static std::mutex stats_output_mutex;
    std::lock_guard<std::mutex> stats_output_lock(stats_output_mutex);
    int saved_precision = cout.precision();
    ios::fmtflags saved_flags = cout.flags();
    cout << fixed << setprecision(6);
    cout << "c PDR_STATS thread=" << thread_index
         << " direction=" << direction_name()
         << " representation=" << representation_name()
         << " result=" << (result == 20 ? "safe" : (result == 10 ? "unsafe" : "unknown"))
         << " active_query=" << active_query_role
         << " depth=" << depth()
         << " runtime=" << get_runtime() << endl;
    cout << "c PDR_CONFIG heuristic=" << cfg_use_heuristic
         << " xag=" << cfg_use_xag
         << " ctg_depth=" << cfg_option_ctg_max_depth
         << " ctg_tries=" << cfg_option_ctg_tries
         << " punishment=" << cfg_use_punishment
         << " pr=" << use_pr
         << " earliest=" << cfg_use_earliest_strengthened_frame
         << " assumption_allsort=" << cfg_assumption_allsort
         << " mic_order=" << mic_order_mode
         << " mic_effective_order=" << mic_effective_order_mode
         << " mic_feedback_weight=" << mic_feedback_weight
         << " obligation_order=" << obligation_order_mode
         << " certify_early=" << cfg_certify_early
         << " certify_early_max_cube=" << cfg_certify_early_max_cube
         << " certify_early_min_push=" << cfg_certify_early_min_push
         << " distance_max_depth=" << decision_distance_max_depth
         << " distance_bad_support_latches=" << distance_bad_support_latches
         << " distance_reached_latches=" << distance_reached_latches
         << " distance_max_observed=" << distance_max_observed
         << " distance_truncated=" << distance_truncated
         << " first_pre_phase=" << first_pre_phase_mode
         << " first_pre_phase_seed=" << first_pre_phase_seed
         << " predecessor_phase=" << predecessor_phase_mode
         << " predecessor_phase_seed=" << predecessor_phase_seed
         << " predecessor_phase_queries=" << predecessor_phase_queries
         << " minisat_freeze_policy=" << minisat_freeze_policy
         << " minisat_freeze_fanout=" << minisat_freeze_fanout
         << " preprocessor=" << cnf_preprocessor
         << " minisat_grow=" << minisat_grow
         << " minisat_clause_limit=" << minisat_clause_limit
         << " minisat_elim_order=" << minisat_elim_order
         << " minisat_translation_elim_order=" << minisat_translation_elim_order
         << " minisat_lift_elim_order=" << minisat_lift_elim_order
         << " minisat_width_weight=" << minisat_width_weight
         << " minisat_translation_width_weight=" << minisat_translation_width_weight
         << " minisat_lift_width_weight=" << minisat_lift_width_weight
         << " minisat_asymm=" << minisat_asymm
         << " minisat_rcheck=" << minisat_rcheck
         << " cadical_pre_rounds=" << cadical_pre_rounds
         << " cadical_elimprod=" << cadical_elimprod
         << " cadical_elimsum=" << cadical_elimsum
         << " seed=" << active_random_seed
         << " seed_mode=" << ((!randomize_lane_seed || cfg_random_seed_explicit)
                                  ? "fixed" : "random") << endl;
    long long structural_clauses = 3LL * ands.size() + 4LL * xors.size()
                                   + 3LL * ors.size();
    cout << "c PDR_REPRESENTATION mode=" << representation_name()
         << " original_ands=" << conversion_original_ands
         << " candidate_xors=" << conversion_candidate_xors
         << " recognized_xors=" << conversion_recognized_xors
         << " removed_ands=" << conversion_removed_ands
         << " xag_policy=" << conversion_xag_policy
         << " xag_fraction=" << conversion_xag_fraction
         << " xag_seed=" << conversion_xag_seed
         << " xag_deep_fraction=" << conversion_xag_deep_fraction
         << " xag_min_fanout=" << conversion_xag_min_fanout
         << " xag_allowlist=" << conversion_xag_allowlist
         << " xag_allowlist_size=" << conversion_xag_allowlist_size
         << " input_order=" << input_order
         << " input_order_seed=" << input_order_seed
         << " input_order_runtime=" << input_order_runtime
         << " perturb_modes=" << perturb_modes
         << " perturb_seed=" << perturb_seed
         << " conversion_runtime=" << conversion_runtime
         << " reset_functions=" << init_equalities.size()
         << " structural_gate_vars=" << (ands.size() + xors.size() + ors.size())
         << " structural_gate_clauses=" << structural_clauses
         << " encoded_gate_instances=" << nEncodedGates
         << " encoded_gate_clauses=" << nEncodedClauses << endl;
    if(auto_selector_active){
        cout << "c PDR_SELECTOR auto_choice="
             << (auto_selector_use_xag ? "xag" : "aig")
             << " auto_next_depth=" << auto_selector_next_depth
             << " auto_recognized_xors=" << auto_selector_recognized_xors
             << " auto_and_reduction=" << auto_selector_and_reduction
             << " auto_min_next_depth=" << auto_selector_min_next_depth
             << " auto_min_and_reduction=" << auto_selector_min_and_reduction
             << endl;
    }
    cout << "c PDR_SHARE published=" << shared_published
         << " received=" << shared_received
         << " imported=" << shared_imported
         << " rejected=" << shared_rejected
         << " certified=" << shared_certified
         << " not_inductive=" << shared_not_inductive
         << " early_attempted=" << early_certify_attempted
         << " early_succeeded=" << early_certify_succeeded
         << " permanent=" << inductive_cubes.size()
         << " attempted=" << inductive_attempted_cubes.size() << endl;
    cout << "c PDR_INVARIANT_TRANSFER import_read=" << invariant_import_read
         << " import_installed=" << invariant_import_installed
         << " import_rejected=" << invariant_import_rejected
         << " import_pruned=" << invariant_import_pruned
         << " import_proves_target=" << (invariant_proves_target ? 1 : 0)
         << " exported=" << invariant_exported
         << " snapshot_exported=" << invariant_snapshot_exported << endl;
    cout << "c PDR_REVERSE_LIFT attempted=" << nReverseLiftAttempt
         << " succeeded=" << nReverseLiftSuccess
         << " fallback=" << nReverseLiftFallback
         << " restarts=" << nReverseLiftRestart
         << " enabled=" << reverse_lifting_enabled << endl;
    cout << "c XAG_STATS inputs=" << num_inputs
         << " latches=" << num_latches
         << " ands=" << ands.size()
         << " xors=" << xors.size()
         << " ors=" << ors.size() << endl;
    cout << "c PDR_AFFINE next_count=" << affine_next_count
         << " next_total=" << num_latches
         << " rank=" << affine_next_rank
         << " support_sum=" << affine_support_sum
         << " support_max=" << affine_support_max
         << " support_avg="
         << (affine_next_count == 0 ? 0.0
             : static_cast<double>(affine_support_sum) / affine_next_count)
         << " summary_enabled=" << (affine_summary_enabled ? 1 : 0)
         << " summary_equations=" << affine_summary_equations
         << " summary_literals=" << affine_summary_literals
         << " island_enabled=" << (affine_island_summary_enabled ? 1 : 0)
         << " island_replace=" << (affine_island_replace_enabled ? 1 : 0)
         << " island_dag=" << (affine_island_dag_enabled ? 1 : 0)
         << " island_min_xors=" << affine_island_min_xors
         << " island_max_support_limit=" << affine_island_max_support
         << " island_count=" << affine_island_summaries.size()
         << " island_xor_nodes=" << affine_island_xor_nodes
         << " island_support_sum=" << affine_island_support_sum
         << " island_support_max=" << affine_island_support_max
         << " island_encoded_equations=" << affine_island_encoded_equations
         << " island_encoded_literals=" << affine_island_encoded_literals
         << " island_replaced_gates=" << affine_island_replaced_gates
         << " cmsat_boundary_bve=" << (cmsat_boundary_bve_enabled ? 1 : 0)
         << " cmsat_boundary_bve_runs=" << cmsat_boundary_bve_runs
         << " cmsat_boundary_bve_candidates=" << cmsat_boundary_bve_candidates
         << " cmsat_boundary_bve_eliminated=" << cmsat_boundary_bve_eliminated
         << " cmsat_boundary_bve_raw_clauses=" << cmsat_boundary_bve_raw_clauses
         << " cmsat_boundary_bve_simplified_clauses="
         << cmsat_boundary_bve_simplified_clauses
         << " island_validation_attempted="
         << (affine_island_validation_attempted ? 1 : 0)
         << " island_validation_passed="
         << (affine_island_validation_passed ? 1 : 0)
         << " island_validation_seconds=" << affine_island_validation_seconds
         << " guarded_enabled=" << (guarded_affine_enabled ? 1 : 0)
         << " guarded_auto_enabled="
         << (guarded_affine_auto_enabled ? 1 : 0)
         << " guarded_auto_min_coverage="
         << guarded_affine_auto_min_coverage
         << " guarded_controls=" << guarded_affine_controls.size()
         << " guarded_next_count=" << guarded_affine_next_count
         << " guarded_modes=" << guarded_affine_modes
         << " guarded_support_sum=" << guarded_affine_support_sum
         << " guarded_support_max=" << guarded_affine_support_max
         << " guarded_selection_gain=" << guarded_affine_selection_gain
         << " guarded_selection_next_roots="
         << guarded_affine_selection_next_roots
         << " guarded_selection_property_roots="
         << guarded_affine_selection_property_roots
         << " guarded_encoded_modes=" << guarded_affine_encoded_modes
         << " guarded_guard_clauses=" << guarded_affine_guard_clauses
         << " guarded_validation_attempted="
         << (guarded_affine_validation_attempted ? 1 : 0)
         << " guarded_validation_passed="
         << (guarded_affine_validation_passed ? 1 : 0)
         << " invariant_enabled=" << (affine_invariants_enabled ? 1 : 0)
         << " invariant_direct_check="
         << (affine_invariants_direct_check ? 1 : 0)
         << " invariant_conditioned_feedback="
         << (affine_invariants_conditioned_feedback ? 1 : 0)
         << " invariant_conditioned_feedback_max_rows="
         << affine_invariants_conditioned_feedback_max_rows
         << " invariant_guarded_min_coverage="
         << affine_invariants_guarded_min_coverage
         << " invariant_model_validated="
         << (affine_invariants_model_validated ? 1 : 0)
         << " invariant_guarded=" << (affine_invariants_guarded ? 1 : 0)
         << " invariant_conditioned="
         << (affine_invariants_conditioned ? 1 : 0)
         << " invariant_partial=" << (affine_invariants_partial ? 1 : 0)
         << " invariant_modes=" << affine_invariants_modes
         << " invariant_tracked_latches="
         << affine_invariants_tracked_latches
         << " invariant_abstracted_latches="
         << affine_invariants_abstracted_latches
         << " invariant_reachable_modes="
         << affine_invariants_reachable_modes
         << " invariant_reachable_rank="
         << affine_invariants_reachable_rank
         << " invariant_count=" << affine_parity_invariants.size()
         << " invariant_support_sum=" << affine_invariants_support_sum
         << " invariant_support_max=" << affine_invariants_support_max
         << " invariant_max_width=" << affine_invariants_max_width
         << " invariant_selected=" << affine_invariants_selected
         << " invariant_closure_rounds="
         << affine_invariants_closure_rounds
         << " invariant_encoded=" << affine_invariants_encoded
         << " invariant_conditioned_encoded="
         << affine_invariants_conditioned_encoded
         << " invariant_conditioned_clauses="
         << affine_invariants_conditioned_clauses
         << " invariant_conditioned_feedback_selected="
         << affine_invariants_conditioned_feedback_selected
         << " invariant_proves_target="
         << (affine_invariants_prove_target ? 1 : 0)
         << " invariant_seconds=" << affine_invariants_seconds
         << " cadical_hints=" << (cadical_affine_hints_enabled ? 1 : 0)
         << " cadical_hint_equations=" << cadical_affine_hint_equations
         << " cadical_hint_clauses=" << cadical_affine_hint_clauses
         << " auto_enabled=" << (affine_auto_enabled ? 1 : 0)
         << " auto_choice=" << affine_auto_choice
         << " auto_cadical_max_support=" << affine_auto_cadical_max_support
         << " gauss_disable_depth=" << cmsat_gauss_disable_depth
         << " gauss_auto_gate=" << (cmsat_gauss_auto_gate ? 1 : 0)
         << " gauss_auto_min_depth=" << cmsat_gauss_auto_min_depth
         << " gauss_auto_min_checks=" << cmsat_gauss_auto_min_checks
         << " gauss_auto_max_useful_ppm="
         << cmsat_gauss_auto_max_useful_ppm
         << " gauss_auto_max_avg_matrix_cells="
         << cmsat_gauss_auto_max_avg_matrix_cells
         << " gauss_auto_patience=" << cmsat_gauss_auto_patience
         << " gauss_disabled=" << (cmsat_gauss_disabled ? 1 : 0)
         << " gauss_disabled_at_depth=" << cmsat_gauss_disabled_at_depth
         << " gauss_disabled_solvers=" << cmsat_gauss_disabled_solvers
         << endl;
    if(!guarded_affine_controls.empty()){
        cout << "c PDR_AFFINE_CONTROLS variables=";
        for(size_t index = 0; index < guarded_affine_controls.size(); ++index){
            if(index)
                cout << ',';
            cout << guarded_affine_controls[index];
        }
        cout << " kinds=";
        const int first_latch = unprimed_first_dimacs + num_inputs;
        const int after_latch = first_latch + num_latches;
        for(size_t index = 0; index < guarded_affine_controls.size(); ++index){
            if(index)
                cout << ',';
            const int variable = guarded_affine_controls[index];
            if(variable >= unprimed_first_dimacs && variable < first_latch)
                cout << "input";
            else if(variable >= first_latch && variable < after_latch)
                cout << "latch";
            else
                cout << "gate";
        }
        cout << endl;
    }
    SATGaussStats gauss_stats = cmsat_gauss_disabled
        ? cmsat_gauss_final : aggregate_cmsat_gauss_stats();
    cout << "c CMSAT_GAUSS_TOTAL checks=" << gauss_stats.checks
         << " row_xors=" << gauss_stats.row_xors
         << " propagations=" << gauss_stats.propagations
         << " conflicts=" << gauss_stats.conflicts
         << " matrices=" << gauss_stats.matrices
         << " rows=" << gauss_stats.rows
         << " columns=" << gauss_stats.columns << endl;
    cout << "c PDR_COUNTERS queries=" << nQuery
         << " inductive=" << nInductive
         << " cti=" << nCTI
         << " ctg=" << nCTG
         << " mic=" << nmic
         << " block=" << nBlock
         << " generalize=" << nGeneralize
         << " extract=" << nExtract
         << " pre=" << nPre
         << " propagate=" << nProp
         << " push=" << nPush
         << " unpush=" << nUnpush
         << " core_reduced=" << nCoreReduced
         << " lemma_added=" << nLemmaAdded
         << " lemma_literals=" << nLemmaLiterals
         << " block_lemma_added=" << nBlockLemmaAdded
         << " block_lemma_literals=" << nBlockLemmaLiterals
         << " push_lemma_added=" << nPushLemmaAdded
         << " push_lemma_literals=" << nPushLemmaLiterals
         << " frame_core=" << nFrameCore
         << " frame_core_input_literals=" << nFrameCoreInputLiterals
         << " frame_core_literals=" << nFrameCoreLiterals
         << " lift_core=" << nLiftCore
         << " lift_core_input_literals=" << nLiftCoreInputLiterals
         << " lift_core_literals=" << nLiftCoreLiterals
         << " abort_join=" << nAbortJoin
         << " abort_mic=" << nAbortMic << endl;
    auto avg = [](double total, int count) -> double {
        return count > 0 ? total / count : 0.0;
    };
    auto add_search_stats = [](SATSearchStats &sum, const SATSearchStats &value) {
        sum.conflicts += value.conflicts;
        sum.decisions += value.decisions;
        sum.propagations += value.propagations;
        sum.restarts += value.restarts;
    };
    SATSearchStats frame_search;
    for(const Frame &frame : frames)
        if(frame.solver != nullptr)
            add_search_stats(frame_search, frame.solver->search_stats());
    SATSearchStats lift_search = lift == nullptr ? SATSearchStats() : lift->search_stats();
    SATSearchStats init_search = init == nullptr ? SATSearchStats() : init->search_stats();
    SATSearchStats checker_search;
    if(checker != nullptr)
        add_search_stats(checker_search, checker->search_stats());
    if(inductive_solver != nullptr)
        add_search_stats(checker_search, inductive_solver->search_stats());
    struct CNFShape {
        long long binary = 0;
        long long ternary = 0;
        long long long_clauses = 0;
        long long max_size = 0;
    };
    auto cnf_shape = [](const CNFSimplifier *simplifier) {
        CNFShape shape;
        if(simplifier == nullptr)
            return shape;
        long long size = 0;
        for(int literal : simplifier->simplified_cnf){
            if(literal != 0){
                ++size;
                continue;
            }
            if(size == 2)
                ++shape.binary;
            else if(size == 3)
                ++shape.ternary;
            else if(size > 3)
                ++shape.long_clauses;
            shape.max_size = std::max(shape.max_size, size);
            size = 0;
        }
        return shape;
    };
    CNFShape translation_shape = cnf_shape(satelite);
    CNFShape lift_shape = cnf_shape(satelite2);
    cout << "c PDR_TIMES block=" << tBlock
         << " inductive=" << tInductive << " avg_inductive=" << avg(tInductive, nInductive)
         << " generalize=" << tGeneralize << " avg_generalize=" << avg(tGeneralize, nGeneralize)
         << " ctg=" << tCTG
         << " propagate=" << tPropagate
         << " extract=" << tExtract << " avg_extract=" << avg(tExtract, nExtract)
         << " pre=" << tPre << " avg_pre=" << avg(tPre, nPre) << endl;
    cout << "c PDR_PHASE_TIMES thread=" << thread_index
         << " translation_build=" << tTranslationBuild
         << " translation_simplify=" << tTranslationSimplify
         << " translation_inject=" << tTranslationInject
         << " lift_build=" << tLiftBuild
         << " lift_simplify=" << tLiftSimplify
         << " lift_inject=" << tLiftInject
         << " bmc0_solve=" << tBmc0Solve
         << " first_pre_solve=" << tFirstPreSolve
         << " first_lift_solve=" << tFirstLiftSolve << endl;
    cout << "c PDR_PHASE_CNF thread=" << thread_index
         << " translation_raw_vars=" << translationRawVars
         << " translation_raw_clauses=" << translationRawClauses
         << " translation_simplified_vars=" << translationSimplifiedVars
         << " translation_simplified_clauses=" << translationSimplifiedClauses
         << " translation_simplified_literals=" << translationSimplifiedLiterals
         << " translation_binary_clauses=" << translation_shape.binary
         << " translation_ternary_clauses=" << translation_shape.ternary
         << " translation_long_clauses=" << translation_shape.long_clauses
         << " translation_max_clause_size=" << translation_shape.max_size
         << " translation_frozen_gate_vars=" << translationFrozenGateVars
         << " lift_raw_vars=" << liftRawVars
         << " lift_raw_clauses=" << liftRawClauses
         << " lift_simplified_vars=" << liftSimplifiedVars
         << " lift_simplified_clauses=" << liftSimplifiedClauses
         << " lift_simplified_literals=" << liftSimplifiedLiterals
         << " lift_binary_clauses=" << lift_shape.binary
         << " lift_ternary_clauses=" << lift_shape.ternary
         << " lift_long_clauses=" << lift_shape.long_clauses
         << " lift_max_clause_size=" << lift_shape.max_size
         << " lift_frozen_gate_vars=" << liftFrozenGateVars << endl;
    CNFSimplificationStats translation_bve = satelite == nullptr
        ? CNFSimplificationStats() : satelite->simplification_stats();
    CNFSimplificationStats lift_bve = satelite2 == nullptr
        ? CNFSimplificationStats() : satelite2->simplification_stats();
    cout << "c PDR_PHASE_BVE thread=" << thread_index
         << " translation_bve_attempted=" << translation_bve.attempted_vars
         << " translation_bve_eliminated=" << translation_bve.eliminated_vars
         << " translation_bve_rejected_growth=" << translation_bve.rejected_growth
         << " translation_bve_rejected_clause_limit=" << translation_bve.rejected_clause_limit
         << " translation_bve_removed_clauses=" << translation_bve.removed_clauses
         << " translation_bve_resolvents=" << translation_bve.resolvents
         << " translation_bve_resolvent_literals=" << translation_bve.resolvent_literals
         << " translation_bve_positive_occurrences=" << translation_bve.positive_occurrences
         << " translation_bve_negative_occurrences=" << translation_bve.negative_occurrences
         << " translation_bve_max_resolvent_size=" << translation_bve.max_resolvent_size
         << " translation_bve_merge_checks=" << translation_bve.merge_checks
         << " lift_bve_attempted=" << lift_bve.attempted_vars
         << " lift_bve_eliminated=" << lift_bve.eliminated_vars
         << " lift_bve_rejected_growth=" << lift_bve.rejected_growth
         << " lift_bve_rejected_clause_limit=" << lift_bve.rejected_clause_limit
         << " lift_bve_removed_clauses=" << lift_bve.removed_clauses
         << " lift_bve_resolvents=" << lift_bve.resolvents
         << " lift_bve_resolvent_literals=" << lift_bve.resolvent_literals
         << " lift_bve_positive_occurrences=" << lift_bve.positive_occurrences
         << " lift_bve_negative_occurrences=" << lift_bve.negative_occurrences
         << " lift_bve_max_resolvent_size=" << lift_bve.max_resolvent_size
         << " lift_bve_merge_checks=" << lift_bve.merge_checks << endl;
    cout << "c PDR_SAT_ROLE thread=" << thread_index
         << " frame_sat_conflicts=" << frame_search.conflicts
         << " frame_sat_decisions=" << frame_search.decisions
         << " frame_sat_propagations=" << frame_search.propagations
         << " frame_sat_restarts=" << frame_search.restarts
         << " lift_sat_conflicts=" << lift_search.conflicts
         << " lift_sat_decisions=" << lift_search.decisions
         << " lift_sat_propagations=" << lift_search.propagations
         << " lift_sat_restarts=" << lift_search.restarts
         << " init_sat_conflicts=" << init_search.conflicts
         << " init_sat_decisions=" << init_search.decisions
         << " init_sat_propagations=" << init_search.propagations
         << " init_sat_restarts=" << init_search.restarts
         << " checker_sat_conflicts=" << checker_search.conflicts
         << " checker_sat_decisions=" << checker_search.decisions
         << " checker_sat_propagations=" << checker_search.propagations
         << " checker_sat_restarts=" << checker_search.restarts << endl;
    cout.flags(saved_flags);
    cout.precision(saved_precision);
}

void PDR::log_witness(){
    cex_states.clear();
    State* p = cex_state_idx;
    set<State *> ss;
    while(p != nullptr){
        cex_states.push_back(p);
        ss.insert(p);
        p = p->next;
    }
    if(is_reverse())
        reverse(cex_states.begin(), cex_states.end());
    for(auto q : states){
        if(ss.find(q) == ss.end()){
            delete q;
        }
    }
}

bool PDR::finalize_counterexample(){
    log_witness();
    if(!is_reverse() || validate_trace(counterexample_trace(), counterexample_requires_init))
        return true;

    find_cex = false;
    cex_state_idx = nullptr;
    cex_states.clear();
    obligation_queue.clear();
    if(reverse_lifting_enabled){
        reverse_lifting_enabled = false;
        reverse_lift_restart_requested = true;
        ++nReverseLiftRestart;
        return false;
    }

    cerr << "Error: exact reverse PDR produced an invalid counterexample trace." << endl;
    engine_result = -1;
    return false;
}

void PDR::show_witness(){
    assert(find_cex);
    //cout <<"AIGER witness:\n";
    if(!output_witness) return;
    cout << "1\n";
    cout << "b0\n";
    int initial_state = 1;
    for(auto s : cex_states){
        if(initial_state){
            cout << return_latch(s) + "\n";
            initial_state = 0;
        }
        cout << return_input(s) + "\n";
    }
    cout << ".\n";

    if(!output_witness_with_latch) return;
    cout << "witness with transition:\n";
    for(auto s : cex_states){
        cout << return_state(s) + "\n";
        delete s;
    }
}

void PDR::show_variables(){
    int ct = 1;
    for(int i=1; i<variables.size(); ++i){
        Variable &v = variables[i];
        // assert(i == v.dimacs_var);
        cout << "v" << v.dimacs_var << "(" << v.name << ")    \t";
        if(ct++ % 20 == 0 || (i+1<variables.size() && variables[i+1].name[0] != v.name[0])){
            cout << endl;
            ct = 1;
        }
    }
    cout << endl;
}

void PDR::show_PO(){
    cout<<" + -----"<<endl;

    for(Obligation o : obligation_queue){
        cout<<"L"<<o.frame_k<<" d"<<o.depth<<" S: ";
        show_litvec(o.state->latches);
        // show_state(o.state);
    }

    cout<<" + ====="<<endl;
}

void PDR::show_frames(){
    int k=0, safe=0;
    cout<<endl;
    for(Frame & f: frames){
        cout << "Level " << k++ <<" (cubeCount = " << f.cubes.size();
        cout<<" varCount =  "<<f.solver->max_var()<<" ";
        cout << ") :" << endl;
        if(k == 1) continue;
        if(f.cubes.size() == 0) {
            safe=1;continue;
        }
        if(safe==0) continue;
        
        for(const Cube &c : f.cubes){
            Cube cc = c;
            show_litvec(cc);
        }
        safe=0;
    }
    cout<<"\n * ======="<<endl;
}

void PDR::show_aag(){
    std::ofstream file("certificate.aag");
    if (!file.is_open()) {
        cerr << "Error: Could not open file " << "certificate.aag" << " for writing.\n";
        return;
    }    
    file << "aag " << (num_inputs + num_latches + num_ands) << " " << num_inputs << " " << num_latches << " 0 " << num_ands << " 1";
    
    if(constraints.size()>0)
        file << " " << constraints.size();
    file << std::endl;

    for(int i = 1; i <= num_inputs; ++i) 
        file << 2 * i << std::endl;

    for(int i = 1; i <= num_latches; ++i) {
        file << 2 * (num_inputs + i) << " " << dimacs_to_aiger(nexts[i-1]);
        if(Aiger_latches[i-1].default_val != 0) {
            file << " " << Aiger_latches[i-1].default_val;
        }
        file << std::endl;
    }

    file << dimacs_to_aiger(bad) << std::endl;

    for(int i = 0; i < constraints.size(); ++i) 
        file << dimacs_to_aiger(constraints[i]) << std::endl;

    for(int i = 0; i < ands.size(); ++i) {
        file << dimacs_to_aiger(ands[i].o) << " ";
        file << dimacs_to_aiger(ands[i].i1) << " ";
        file << dimacs_to_aiger(ands[i].i2) << std::endl;
    }
    file.close(); 
    std::string command = "./aigtoaig certificate.aag certificate.aig";
    int result = system(command.c_str());
}

int PDR::prime_var(int var){
    assert(var >= 1);
    if(var > 1){
        if(var <= 1 + num_inputs + num_latches){
            return primed_first_dimacs + var - 2;
        }else{
            if(map_to_prime.find(var) == map_to_prime.end()){
                int unprimed_var = var;
                int primed_var = variables.size();
                map_to_prime[unprimed_var] = primed_var;
                map_to_unprime[primed_var] = unprimed_var;
                string new_name = variables[unprimed_var].name + string("'");
                variables.push_back(Variable(primed_var, new_name));
                return primed_var;
            }else{
                return map_to_prime[var];
            }
        }
    }else{
        // use const True/False
        return var;
    }
}

int PDR::prime_lit(int lit){
    if(lit >= 0){
        return prime_var(lit);
    }else{
        return -prime_var(-lit);
    }
}

void PDR::use_xag_for_pdr(){
    aig2xag::ConvertOptions options;
    const char *policy_value = std::getenv("MC_PDR_XAG_POLICY");
    if(policy_value != nullptr
       && !aig2xag::parse_xor_selection_policy(policy_value, options.xor_policy)){
        cerr << "Warning: invalid MC_PDR_XAG_POLICY='" << policy_value
             << "'; using all." << endl;
        options.xor_policy = aig2xag::XorSelectionPolicy::All;
    }
    options.xor_sample_fraction = env_double(
        "MC_PDR_XAG_FRACTION", options.xor_sample_fraction);
    options.deep_xor_fraction = env_double(
        "MC_PDR_XAG_DEEP_FRACTION", options.deep_xor_fraction);
    options.min_xor_fanout = env_int(
        "MC_PDR_XAG_MIN_FANOUT", options.min_xor_fanout);
    options.stable_xor_slots = env_bool(
        "MC_PDR_XAG_STABLE_SLOTS", options.stable_xor_slots);
    if(const char *seed_value = std::getenv("MC_PDR_XAG_SEED"))
        options.xor_sample_seed = static_cast<unsigned>(
            std::strtoul(seed_value, nullptr, 10));
    if(options.xor_sample_fraction < 0.0 || options.xor_sample_fraction > 1.0){
        cerr << "Warning: MC_PDR_XAG_FRACTION must be between 0 and 1; "
                "clamping it." << endl;
        options.xor_sample_fraction = std::max(
            0.0, std::min(1.0, options.xor_sample_fraction));
    }
    if(options.deep_xor_fraction < 0.0 || options.deep_xor_fraction > 1.0){
        cerr << "Warning: MC_PDR_XAG_DEEP_FRACTION must be between 0 and 1; "
                "clamping it." << endl;
        options.deep_xor_fraction = std::max(
            0.0, std::min(1.0, options.deep_xor_fraction));
    }
    if(options.min_xor_fanout < 1){
        cerr << "Warning: MC_PDR_XAG_MIN_FANOUT must be positive; using 1."
             << endl;
        options.min_xor_fanout = 1;
    }
    if(const char *allowlist_path = std::getenv("MC_PDR_XAG_ALLOWLIST_FILE")){
        std::ifstream input(allowlist_path);
        if(!input)
            throw std::runtime_error(
                string("cannot open MC_PDR_XAG_ALLOWLIST_FILE: ")
                + allowlist_path);
        options.restrict_xors_to_allowlist = true;
        unsigned var = 0;
        while(input >> var){
            if(var > 0)
                options.xor_allowlist.insert(var);
        }
        if(!input.eof())
            throw std::runtime_error(
                string("invalid XOR variable in allowlist: ") + allowlist_path);
    }
    use_converted_for_pdr(options);
}

void PDR::use_converted_for_pdr(const aig2xag::ConvertOptions &options){
    aig2xag::ConvertResult converted = aig2xag::convert(*this, options);
    const aig2xag::XagCircuit &xag = converted.xag;
    conversion_original_ands = converted.stats.original_ands;
    conversion_candidate_xors = converted.stats.candidate_xors;
    conversion_recognized_xors = converted.stats.recognized_xors;
    conversion_removed_ands = converted.stats.removed_ands;
    conversion_xag_policy = options.recognize_xors
        ? aig2xag::xor_selection_policy_name(options.xor_policy) : "none";
    conversion_xag_fraction = options.xor_sample_fraction;
    conversion_xag_seed = options.xor_sample_seed;
    conversion_xag_deep_fraction = options.deep_xor_fraction;
    conversion_xag_min_fanout = options.min_xor_fanout;
    conversion_xag_allowlist = options.restrict_xors_to_allowlist;
    conversion_xag_allowlist_size = static_cast<int>(options.xor_allowlist.size());

    num_inputs = xag.num_inputs;
    num_latches = xag.num_latches;
    num_ands = xag.num_ands;
    max_var = xag.num_inputs + xag.num_latches + static_cast<int>(xag.gates.size());

    Aiger_inputs = xag.inputs;
    Aiger_latches.clear();
    for(size_t i=0; i<xag.latches.size(); ++i)
        Aiger_latches.push_back(Aiger_latch(xag.latches[i].lit, xag.latches[i].next, xag.latches[i].default_val));
    Aiger_outputs = xag.outputs;
    Aiger_bads = xag.bads;
    Aiger_constraints = xag.constraints;
    Aiger_ands.clear();

    variables.clear();
    ands.clear();
    xors.clear();
    ors.clear();
    nexts.clear();
    init_state.clear();
    init_equalities.clear();
    constraints.clear();
    constraints_prime.clear();
    allbad.clear();
    map_to_prime.clear();
    map_to_unprime.clear();

    variables.push_back(Variable(0, string("NULL")));
    variables.push_back(Variable(1, string("False")));

    for(int i=1; i<=num_inputs; ++i)
        variables.push_back(Variable(1 + i, 'i', i-1, false));

    for(int i=1; i<=num_latches; ++i)
        variables.push_back(Variable(1 + num_inputs + i, 'l', i-1, false));

    int and_index = 0, xor_index = 0, or_index = 0;
    for(size_t i=0; i<xag.gates.size(); ++i){
        const aig2xag::XagGate &g = xag.gates[i];
        int o = aiger_to_dimacs(g.out);
        if(g.type == aig2xag::XAG_UNUSED){
            // Variable metadata only accepts structural AIG/XAG kinds.  This
            // slot deliberately has no matching entry in any gate vector.
            variables.push_back(Variable(o, 'a', -1, false));
            continue;
        }
        int i1 = aiger_to_dimacs(g.fanin0);
        int i2 = aiger_to_dimacs(g.fanin1);
        char name_type = 'a';
        int type_index = and_index;

        if(g.type == aig2xag::XAG_XOR){
            xors.push_back(And(o, i1, i2));
            name_type = 'x';
            type_index = xor_index++;
        }else if(g.type == aig2xag::XAG_OR){
            ors.push_back(And(o, i1, i2));
            name_type = 'o';
            type_index = or_index++;
        }else{
            ands.push_back(And(o, i1, i2));
            and_index++;
        }
        variables.push_back(Variable(o, name_type, type_index, false));
    }

    for(int i=1; i<=num_latches; ++i){
        int l = 1 + num_inputs + i;
        Aiger_latch &al = Aiger_latches[i-1];
        nexts.push_back(aiger_to_dimacs(al.next));
        if(al.default_val == 0)
            init_state.push_back(-l);
        else if(al.default_val == 1)
            init_state.push_back(l);
        else if(al.default_val != al.l)
            init_equalities.push_back(
                make_pair(l, aiger_to_dimacs(al.default_val)));
    }

    for(size_t i=0; i<Aiger_constraints.size(); ++i)
        constraints.push_back(aiger_to_dimacs(Aiger_constraints[i]));

    if(num_bads > 0){
        if(num_bads <= propertyIndex){
            cerr << "Warning: property_index out of range (must be between 0 and " << num_bads - 1 << "). Setting to 0." << std::endl;
            propertyIndex = 0;
        }
        for(int i=0; i<num_bads; ++i)
            allbad.push_back(aiger_to_dimacs(Aiger_bads[i]));
        bad = allbad[propertyIndex];
        num_property = num_bads;
    }else if(num_outputs > 0){
        if(num_outputs <= propertyIndex){
            cerr << "Warning: property_index out of range (must be between 0 and " << num_outputs - 1 << "). Setting to 0." << std::endl;
            propertyIndex = 0;
        }
        for(int i=0; i<num_outputs; ++i)
            allbad.push_back(aiger_to_dimacs(Aiger_outputs[i]));
        bad = allbad[propertyIndex];
        num_property = num_outputs;
    }

    primed_first_dimacs = variables.size();
    assert(primed_first_dimacs == 1 + num_inputs + num_latches + static_cast<int>(xag.gates.size()) + 1);

    if(env_bool("MC_PDR_DUMP_REP", false)){
        cout << "c PDR_REP_DUMP mode=" << representation_name()
             << " bad=" << bad << " nexts=";
        for(int next : nexts) cout << next << ",";
        cout << endl;
        for(const And &gate : ands)
            cout << "c PDR_REP_GATE and " << gate.o << " " << gate.i1 << " " << gate.i2 << endl;
        for(const And &gate : xors)
            cout << "c PDR_REP_GATE xor " << gate.o << " " << gate.i1 << " " << gate.i2 << endl;
    }

    if(aig_veb){
        cout << "c aig2xag for PDR: ands " << converted.stats.original_ands
             << " -> ands " << ands.size()
             << ", xors " << xors.size()
             << ", ors " << ors.size()
             << ", removed " << converted.stats.removed_ands << endl;
    }
}

void PDR::encode_gate(SATSolver *s, const And &g, int gate_type){
    ++nEncodedGates;
    if(gate_type == 0){
        nEncodedClauses += 3;
        s->add(-g.o); s->add(g.i1);  s->add(0);
        s->add(-g.o); s->add(g.i2);  s->add(0);
        s->add(g.o);  s->add(-g.i1); s->add(-g.i2); s->add(0);
    }else if(gate_type == 1){
        if(s->supports_native_xor()){
            vector<int> equation;
            equation.push_back(g.o);
            equation.push_back(g.i1);
            equation.push_back(g.i2);
            // g.o = g.i1 XOR g.i2, including complemented inputs.
            s->add_xor_clause(equation, false);
            return;
        }
        nEncodedClauses += 4;
        s->add(-g.o); s->add(g.i1);  s->add(g.i2);  s->add(0);
        s->add(-g.o); s->add(-g.i1); s->add(-g.i2); s->add(0);
        s->add(g.o);  s->add(-g.i1); s->add(g.i2);  s->add(0);
        s->add(g.o);  s->add(g.i1);  s->add(-g.i2); s->add(0);
    }else{
        nEncodedClauses += 3;
        s->add(-g.o); s->add(g.i1);  s->add(g.i2); s->add(0);
        s->add(g.o);  s->add(-g.i1); s->add(0);
        s->add(g.o);  s->add(-g.i2); s->add(0);
    }
}

void PDR::analyze_affine_transition(){
    affine_next_count = 0;
    affine_next_rank = 0;
    affine_support_sum = 0;
    affine_support_max = 0;
    affine_next_supports.assign(num_latches, vector<int>());
    affine_next_valid.assign(num_latches, 0);
    affine_next_rhs.assign(num_latches, 0);

    // Complementation changes only an affine constant, so support and rank
    // can be computed by following pure XOR cones over inputs and latches.
    std::unordered_map<int, set<int> > expression;
    std::unordered_map<int, bool> expression_rhs;
    expression[1] = set<int>();
    expression_rhs[1] = false;
    for(int variable = 2; variable <= 1 + num_inputs + num_latches; ++variable){
        expression[variable].insert(variable);
        expression_rhs[variable] = false;
    }

    vector<And> ordered_xors = xors;
    sort(ordered_xors.begin(), ordered_xors.end(),
         [](const And &left, const And &right){
             return abs(left.o) < abs(right.o);
         });
    for(const And &gate : ordered_xors){
        auto left = expression.find(abs(gate.i1));
        auto right = expression.find(abs(gate.i2));
        if(left == expression.end() || right == expression.end())
            continue;
        set<int> support = left->second;
        for(int variable : right->second){
            auto found = support.find(variable);
            if(found == support.end())
                support.insert(variable);
            else
                support.erase(found);
        }
        expression[abs(gate.o)] = support;
        expression_rhs[abs(gate.o)] = expression_rhs[abs(gate.i1)]
            ^ (gate.i1 < 0) ^ expression_rhs[abs(gate.i2)] ^ (gate.i2 < 0);
    }

    std::map<int, set<int> > pivots;
    for(int latch_index = 0; latch_index < num_latches; ++latch_index){
        const int next = nexts[latch_index];
        auto found = expression.find(abs(next));
        if(found == expression.end())
            continue;
        affine_next_valid[latch_index] = 1;
        affine_next_supports[latch_index].assign(
            found->second.begin(), found->second.end());
        affine_next_rhs[latch_index] = static_cast<char>(
            expression_rhs[abs(next)] ^ (next < 0));
        ++affine_next_count;
        affine_support_sum += static_cast<long long>(found->second.size());
        affine_support_max = std::max(
            affine_support_max, static_cast<int>(found->second.size()));

        set<int> row = found->second;
        while(!row.empty()){
            const int pivot = *row.begin();
            auto existing = pivots.find(pivot);
            if(existing == pivots.end()){
                pivots[pivot] = row;
                ++affine_next_rank;
                break;
            }
            for(int variable : existing->second){
                auto present = row.find(variable);
                if(present == row.end())
                    row.insert(variable);
                else
                    row.erase(present);
            }
        }
    }
}

void PDR::analyze_affine_islands(){
    affine_island_summaries.clear();
    affine_island_xor_nodes = 0;
    affine_island_support_sum = 0;
    affine_island_support_max = 0;

    if(xors.empty())
        return;

    std::unordered_map<int, And> xor_by_output;
    std::unordered_map<int, int> xor_consumers;
    std::unordered_map<int, int> all_consumers;
    std::unordered_map<int, vector<int> > xor_consumer_outputs;
    std::unordered_set<int> external_xor_consumers;
    xor_by_output.reserve(xors.size());
    for(const And &gate : xors){
        xor_by_output.emplace(abs(gate.o), gate);
        ++xor_consumers[abs(gate.i1)];
        ++xor_consumers[abs(gate.i2)];
        xor_consumer_outputs[abs(gate.i1)].push_back(abs(gate.o));
        xor_consumer_outputs[abs(gate.i2)].push_back(abs(gate.o));
        ++all_consumers[abs(gate.i1)];
        ++all_consumers[abs(gate.i2)];
    }

    std::unordered_set<int> roots;
    auto mark_external_input = [&](int literal){
        const int variable = abs(literal);
        if(xor_by_output.find(variable) != xor_by_output.end()){
            roots.insert(variable);
            external_xor_consumers.insert(variable);
        }
    };
    for(const And &gate : ands){
        ++all_consumers[abs(gate.i1)];
        ++all_consumers[abs(gate.i2)];
        mark_external_input(gate.i1);
        mark_external_input(gate.i2);
    }
    for(const And &gate : ors){
        ++all_consumers[abs(gate.i1)];
        ++all_consumers[abs(gate.i2)];
        mark_external_input(gate.i1);
        mark_external_input(gate.i2);
    }
    for(int literal : nexts){
        ++all_consumers[abs(literal)];
        mark_external_input(literal);
    }
    ++all_consumers[abs(bad)];
    mark_external_input(bad);
    for(int literal : constraints){
        ++all_consumers[abs(literal)];
        mark_external_input(literal);
    }
    for(const And &gate : xors)
        if(xor_consumers[abs(gate.o)] == 0)
            roots.insert(abs(gate.o));

    struct Expression {
        set<int> support;
        set<int> xor_variables;
        bool rhs = false;
        int xor_nodes = 0;
    };

    vector<int> ordered_roots(roots.begin(), roots.end());
    sort(ordered_roots.begin(), ordered_roots.end());
    for(int root : ordered_roots){
        std::unordered_set<int> dag_cone;
        if(affine_island_dag_enabled){
            vector<int> pending(1, root);
            while(!pending.empty()){
                const int variable = pending.back();
                pending.pop_back();
                if(!dag_cone.insert(variable).second)
                    continue;
                auto gate_it = xor_by_output.find(variable);
                if(gate_it == xor_by_output.end())
                    continue;
                if(xor_by_output.find(abs(gate_it->second.i1)) != xor_by_output.end())
                    pending.push_back(abs(gate_it->second.i1));
                if(xor_by_output.find(abs(gate_it->second.i2)) != xor_by_output.end())
                    pending.push_back(abs(gate_it->second.i2));
            }
        }

        auto dag_private = [&](int variable){
            if(variable == root)
                return true;
            if(dag_cone.find(variable) == dag_cone.end()
               || external_xor_consumers.find(variable)
                    != external_xor_consumers.end())
                return false;
            auto consumers = xor_consumer_outputs.find(variable);
            if(consumers == xor_consumer_outputs.end())
                return false;
            for(int consumer : consumers->second)
                if(dag_cone.find(consumer) == dag_cone.end())
                    return false;
            return true;
        };

        Expression expression;
        std::function<void(int, bool)> expand_literal;
        expand_literal = [&](int literal, bool force_expand){
            const int variable = abs(literal);
            auto gate_it = xor_by_output.find(variable);
            const bool private_xor = gate_it != xor_by_output.end()
                && (force_expand
                    || (affine_island_dag_enabled
                        ? dag_private(variable)
                        : (all_consumers[variable] == 1
                           && xor_consumers[variable] == 1
                           && roots.find(variable) == roots.end())));
            if(!private_xor){
                auto present = expression.support.find(variable);
                if(present == expression.support.end())
                    expression.support.insert(variable);
                else
                    expression.support.erase(present);
                if(literal < 0)
                    expression.rhs = !expression.rhs;
                return;
            }
            if(expression.xor_variables.insert(variable).second)
                ++expression.xor_nodes;
            const And &gate = gate_it->second;
            expand_literal(gate.i1, false);
            expand_literal(gate.i2, false);
            if(literal < 0)
                expression.rhs = !expression.rhs;
        };
        expand_literal(root, true);
        const int support_size = static_cast<int>(expression.support.size());
        if(expression.xor_nodes < affine_island_min_xors
           || support_size < 3
           || support_size > affine_island_max_support)
            continue;
        AffineIslandSummary summary;
        summary.root = root;
        summary.support.assign(expression.support.begin(), expression.support.end());
        summary.xor_variables.assign(
            expression.xor_variables.begin(), expression.xor_variables.end());
        summary.rhs = static_cast<char>(expression.rhs);
        summary.xor_nodes = expression.xor_nodes;
        affine_island_summaries.push_back(summary);
        affine_island_xor_nodes += expression.xor_nodes;
        affine_island_support_sum += support_size;
        affine_island_support_max = std::max(
            affine_island_support_max, support_size);
    }
}

bool PDR::validate_affine_islands(){
    if(affine_island_summaries.empty())
        return true;

    CMSatSolver validator;
    validator.add(-1);
    validator.add(0);
    set<int> cone;
    for(const AffineIslandSummary &summary : affine_island_summaries)
        cone.insert(summary.root);

    // Encode the original gate network without using the equations that are
    // being validated, otherwise the check would be circular.
    const bool saved_summary = affine_island_summary_enabled;
    const bool saved_replace = affine_island_replace_enabled;
    const long long saved_encoded_gates = nEncodedGates;
    const long long saved_encoded_clauses = nEncodedClauses;
    affine_island_summary_enabled = false;
    affine_island_replace_enabled = false;
    encode_gate_cone(&validator, cone);
    affine_island_summary_enabled = saved_summary;
    affine_island_replace_enabled = saved_replace;
    nEncodedGates = saved_encoded_gates;
    nEncodedClauses = saved_encoded_clauses;

    validator.reserve_variables(2 * primed_first_dimacs + 2);
    vector<int> mismatches;
    for(const AffineIslandSummary &summary : affine_island_summaries){
        const int mismatch = validator.fresh_variable();
        vector<int> equation = summary.support;
        equation.push_back(summary.root);
        equation.push_back(mismatch);
        validator.add_xor_clause(equation, summary.rhs != 0);
        mismatches.push_back(mismatch);
    }
    // SAT would be a concrete assignment that violates at least one summary.
    for(int mismatch : mismatches)
        validator.add(mismatch);
    validator.add(0);
    return validator.solve() == UNSAT;
}

void PDR::analyze_guarded_affine_transition(){
    guarded_affine_controls.clear();
    guarded_affine_next_modes.assign(
        num_latches, vector<GuardedAffineMode>());
    guarded_affine_next_valid.assign(num_latches, 0);
    guarded_affine_next_count = 0;
    guarded_affine_modes = 0;
    guarded_affine_support_sum = 0;
    guarded_affine_support_max = 0;
    guarded_affine_selection_gain = 0;
    guarded_affine_selection_next_roots = 0;
    guarded_affine_selection_property_roots = 0;

    if(is_reverse() || guarded_affine_max_controls <= 0)
        return;
    guarded_affine_max_controls = std::min(guarded_affine_max_controls, 8);

    struct GateInfo {
        int type;
        And gate;
        GateInfo(int type, const And &gate): type(type), gate(gate) {}
    };
    std::unordered_map<int, GateInfo> gates;
    for(const And &gate : ands)
        gates.emplace(abs(gate.o), GateInfo(0, gate));
    for(const And &gate : xors)
        gates.emplace(abs(gate.o), GateInfo(1, gate));
    for(const And &gate : ors)
        gates.emplace(abs(gate.o), GateInfo(2, gate));

    const int leaf_last = 1 + num_inputs + num_latches;
    struct AffineExpression {
        bool valid = false;
        set<int> support;
        bool rhs = false;
    };

    struct GuardEvaluation {
        int valid_count = 0;
        vector<vector<GuardedAffineMode> > modes_by_latch;
        GuardEvaluation(int latches): modes_by_latch(latches) {}
    };
    auto evaluate_controls = [&](const vector<int> &controls){
        GuardEvaluation evaluation(num_latches);
        vector<char> valid_for_all_modes(num_latches, 1);
        const int mode_count = 1 << controls.size();
        for(int mode = 0; mode < mode_count; ++mode){
            std::unordered_map<int, bool> assignment;
            vector<int> guard;
            for(size_t index = 0; index < controls.size(); ++index){
                const int variable = controls[index];
                const bool value = (mode & (1 << index)) != 0;
                assignment[variable] = value;
                guard.push_back(value ? variable : -variable);
            }

            std::unordered_map<int, AffineExpression> cache;
            std::function<AffineExpression(int)> evaluate_literal;
            std::function<AffineExpression(int)> evaluate_variable;
            evaluate_variable = [&](int variable) -> AffineExpression {
                auto cached = cache.find(variable);
                if(cached != cache.end())
                    return cached->second;
                AffineExpression result;
                if(variable == 1){
                    result.valid = true;
                }else{
                    auto fixed = assignment.find(variable);
                    if(fixed != assignment.end()){
                        result.valid = true;
                        result.rhs = fixed->second;
                    }else if(variable <= leaf_last){
                        result.valid = true;
                        result.support.insert(variable);
                    }else{
                        auto found = gates.find(variable);
                        if(found == gates.end()){
                            cache[variable] = result;
                            return result;
                        }
                        AffineExpression left =
                            evaluate_literal(found->second.gate.i1);
                        AffineExpression right =
                            evaluate_literal(found->second.gate.i2);
                        if(!left.valid || !right.valid){
                            cache[variable] = result;
                            return result;
                        }
                        if(found->second.type == 1){
                            result = left;
                            result.rhs ^= right.rhs;
                            for(int support : right.support){
                                auto present = result.support.find(support);
                                if(present == result.support.end())
                                    result.support.insert(support);
                                else
                                    result.support.erase(present);
                            }
                        }else{
                            const bool left_constant = left.support.empty();
                            const bool right_constant = right.support.empty();
                            if(found->second.type == 0){
                                if(left_constant && !left.rhs)
                                    result = left;
                                else if(right_constant && !right.rhs)
                                    result = right;
                                else if(left_constant && left.rhs)
                                    result = right;
                                else if(right_constant && right.rhs)
                                    result = left;
                            }else{
                                if(left_constant && left.rhs)
                                    result = left;
                                else if(right_constant && right.rhs)
                                    result = right;
                                else if(left_constant && !left.rhs)
                                    result = right;
                                else if(right_constant && !right.rhs)
                                    result = left;
                            }
                        }
                    }
                }
                cache[variable] = result;
                return result;
            };
            evaluate_literal = [&](int literal) -> AffineExpression {
                AffineExpression result = evaluate_variable(abs(literal));
                if(result.valid && literal < 0)
                    result.rhs = !result.rhs;
                return result;
            };

            for(int latch_index = 0; latch_index < num_latches; ++latch_index){
                AffineExpression expression = evaluate_literal(nexts[latch_index]);
                if(!expression.valid){
                    valid_for_all_modes[latch_index] = 0;
                    continue;
                }
                GuardedAffineMode affine_mode;
                affine_mode.guard = guard;
                affine_mode.support.assign(
                    expression.support.begin(), expression.support.end());
                affine_mode.rhs = static_cast<char>(expression.rhs);
                evaluation.modes_by_latch[latch_index].push_back(affine_mode);
            }
        }
        for(int latch_index = 0; latch_index < num_latches; ++latch_index)
            if(valid_for_all_modes[latch_index]
               && static_cast<int>(evaluation.modes_by_latch[latch_index].size())
                    == mode_count)
                ++evaluation.valid_count;
        return evaluation;
    };

    // Candidate scoring needs many what-if evaluations.  Exact support sets
    // make that prohibitively expensive on wide CRC datapaths, so use two
    // deterministic XOR fingerprints here.  They preserve cancellation and
    // constant detection with negligible collision probability.  The chosen
    // controls are still recomputed exactly below before any equation is used.
    struct QuickExpression {
        bool valid = false;
        std::uint64_t first = 0;
        std::uint64_t second = 0;
        bool rhs = false;
    };
    auto mix64 = [](std::uint64_t value){
        value += 0x9e3779b97f4a7c15ULL;
        value = (value ^ (value >> 30)) * 0xbf58476d1ce4e5b9ULL;
        value = (value ^ (value >> 27)) * 0x94d049bb133111ebULL;
        return value ^ (value >> 31);
    };
    auto quick_affine_count = [&](const vector<int> &controls){
        vector<char> valid_for_all_modes(num_latches, 1);
        const int mode_count = 1 << controls.size();
        for(int mode = 0; mode < mode_count; ++mode){
            std::unordered_map<int, bool> assignment;
            for(size_t index = 0; index < controls.size(); ++index)
                assignment[controls[index]] = (mode & (1 << index)) != 0;
            std::unordered_map<int, QuickExpression> cache;
            std::function<QuickExpression(int)> evaluate_literal;
            std::function<QuickExpression(int)> evaluate_variable;
            evaluate_variable = [&](int variable) -> QuickExpression {
                auto cached = cache.find(variable);
                if(cached != cache.end())
                    return cached->second;
                QuickExpression result;
                if(variable == 1){
                    result.valid = true;
                }else{
                    auto fixed = assignment.find(variable);
                    if(fixed != assignment.end()){
                        result.valid = true;
                        result.rhs = fixed->second;
                    }else if(variable <= leaf_last){
                        result.valid = true;
                        result.first = mix64(static_cast<std::uint64_t>(variable));
                        result.second = mix64(
                            static_cast<std::uint64_t>(variable)
                            ^ 0xd6e8feb86659fd93ULL);
                    }else{
                        auto found = gates.find(variable);
                        if(found == gates.end()){
                            cache[variable] = result;
                            return result;
                        }
                        QuickExpression left =
                            evaluate_literal(found->second.gate.i1);
                        QuickExpression right =
                            evaluate_literal(found->second.gate.i2);
                        if(!left.valid || !right.valid){
                            cache[variable] = result;
                            return result;
                        }
                        if(found->second.type == 1){
                            result.valid = true;
                            result.first = left.first ^ right.first;
                            result.second = left.second ^ right.second;
                            result.rhs = left.rhs ^ right.rhs;
                        }else{
                            const bool left_constant =
                                left.first == 0 && left.second == 0;
                            const bool right_constant =
                                right.first == 0 && right.second == 0;
                            if(found->second.type == 0){
                                if(left_constant && !left.rhs)
                                    result = left;
                                else if(right_constant && !right.rhs)
                                    result = right;
                                else if(left_constant && left.rhs)
                                    result = right;
                                else if(right_constant && right.rhs)
                                    result = left;
                            }else{
                                if(left_constant && left.rhs)
                                    result = left;
                                else if(right_constant && right.rhs)
                                    result = right;
                                else if(left_constant && !left.rhs)
                                    result = right;
                                else if(right_constant && !right.rhs)
                                    result = left;
                            }
                        }
                    }
                }
                cache[variable] = result;
                return result;
            };
            evaluate_literal = [&](int literal) -> QuickExpression {
                QuickExpression result = evaluate_variable(abs(literal));
                if(result.valid && literal < 0)
                    result.rhs = !result.rhs;
                return result;
            };
            for(int latch_index = 0; latch_index < num_latches; ++latch_index)
                if(!evaluate_literal(nexts[latch_index]).valid)
                    valid_for_all_modes[latch_index] = 0;
        }
        int valid_count = 0;
        for(char valid : valid_for_all_modes)
            valid_count += valid != 0;
        return valid_count;
    };

    // Candidate occurrence is retained only as a cheap tie breaker.  The
    // primary structural signal is how many next/property roots are reachable
    // from the candidate, followed by the measured affine-coverage gain.
    std::unordered_map<int, int> occurrences;
    auto count_nonlinear_input = [&](int literal){
        const int variable = abs(literal);
        if(variable >= 2)
            ++occurrences[variable];
    };
    for(const And &gate : ands){
        count_nonlinear_input(gate.i1);
        count_nonlinear_input(gate.i2);
    }
    for(const And &gate : ors){
        count_nonlinear_input(gate.i1);
        count_nonlinear_input(gate.i2);
    }

    std::unordered_map<int, vector<int> > consumers;
    auto add_consumers = [&](const vector<And> &source){
        for(const And &gate : source){
            consumers[abs(gate.i1)].push_back(abs(gate.o));
            consumers[abs(gate.i2)].push_back(abs(gate.o));
        }
    };
    add_consumers(ands);
    add_consumers(xors);
    add_consumers(ors);
    std::unordered_map<int, int> next_root_multiplicity;
    for(int next : nexts)
        ++next_root_multiplicity[abs(next)];
    std::unordered_set<int> property_roots;
    if(abs(bad) >= 2)
        property_roots.insert(abs(bad));
    for(int constraint : constraints)
        if(abs(constraint) >= 2)
            property_roots.insert(abs(constraint));

    struct ConeCoverage {
        int next_roots = 0;
        int property_roots = 0;
    };
    std::unordered_map<int, ConeCoverage> cone_coverage;
    auto measure_cone = [&](int candidate){
        ConeCoverage coverage;
        std::unordered_set<int> visited;
        std::queue<int> pending;
        pending.push(candidate);
        while(!pending.empty()){
            const int variable = pending.front();
            pending.pop();
            if(!visited.insert(variable).second)
                continue;
            auto next_root = next_root_multiplicity.find(variable);
            if(next_root != next_root_multiplicity.end())
                coverage.next_roots += next_root->second;
            if(property_roots.find(variable) != property_roots.end())
                ++coverage.property_roots;
            auto found = consumers.find(variable);
            if(found != consumers.end())
                for(int output : found->second)
                    pending.push(output);
        }
        return coverage;
    };

    vector<int> cone_candidates;
    for(const auto &entry : occurrences){
        cone_coverage[entry.first] = measure_cone(entry.first);
        cone_candidates.push_back(entry.first);
    }
    sort(cone_candidates.begin(), cone_candidates.end(), [&](int left, int right){
        const ConeCoverage &a = cone_coverage[left];
        const ConeCoverage &b = cone_coverage[right];
        if(a.property_roots != b.property_roots)
            return a.property_roots > b.property_roots;
        if(a.next_roots != b.next_roots)
            return a.next_roots > b.next_roots;
        if(occurrences[left] != occurrences[right])
            return occurrences[left] > occurrences[right];
        return left < right;
    });
    vector<int> occurrence_candidates = cone_candidates;
    sort(occurrence_candidates.begin(), occurrence_candidates.end(),
         [&](int left, int right){
        if(occurrences[left] != occurrences[right])
            return occurrences[left] > occurrences[right];
        return left < right;
    });
    // Keep both structural views in the shortlist.  A large property cone can
    // contain many internal mux nodes and otherwise crowd its true mode input
    // out of a cone-only top-k list.
    const size_t candidates_per_view = 24;
    vector<int> candidates;
    std::unordered_set<int> shortlisted;
    auto append_candidates = [&](const vector<int> &source){
        const size_t limit = std::min(candidates_per_view, source.size());
        for(size_t index = 0; index < limit; ++index)
            if(shortlisted.insert(source[index]).second)
                candidates.push_back(source[index]);
    };
    append_candidates(cone_candidates);
    append_candidates(occurrence_candidates);

    int current_valid_count = quick_affine_count(guarded_affine_controls);
    // A nested mux often needs both mode inputs fixed before any datapath
    // latch becomes affine (for example, {start-of-frame, valid}).  Single-step
    // greedy gain cannot see that interaction, so perform a bounded pair
    // look-ahead among the strongest occurrence candidates.
    if(guarded_affine_max_controls >= 2){
        const size_t pair_limit = std::min<size_t>(3, occurrence_candidates.size());
        int best_pair_count = current_valid_count;
        int best_pair_first = -1;
        int best_pair_second = -1;
        for(size_t first = 0; first < pair_limit; ++first){
            for(size_t second = first + 1; second < pair_limit; ++second){
                vector<int> pair;
                pair.push_back(occurrence_candidates[first]);
                pair.push_back(occurrence_candidates[second]);
                const int count = quick_affine_count(pair);
                if(count > best_pair_count){
                    best_pair_count = count;
                    best_pair_first = pair[0];
                    best_pair_second = pair[1];
                }
            }
        }
        if(best_pair_first >= 0){
            guarded_affine_controls.push_back(best_pair_first);
            guarded_affine_controls.push_back(best_pair_second);
            const ConeCoverage first_coverage = cone_coverage[best_pair_first];
            const ConeCoverage second_coverage = cone_coverage[best_pair_second];
            guarded_affine_selection_next_roots +=
                first_coverage.next_roots + second_coverage.next_roots;
            guarded_affine_selection_property_roots +=
                first_coverage.property_roots + second_coverage.property_roots;
            current_valid_count = best_pair_count;
        }
    }
    while(static_cast<int>(guarded_affine_controls.size())
            < guarded_affine_max_controls){
        int best = -1;
        int best_gain = std::numeric_limits<int>::min();
        ConeCoverage best_cone;
        int best_occurrence = -1;
        for(int candidate : candidates){
            if(std::find(guarded_affine_controls.begin(),
                         guarded_affine_controls.end(), candidate)
                    != guarded_affine_controls.end())
                continue;
            vector<int> trial_controls = guarded_affine_controls;
            trial_controls.push_back(candidate);
            const int trial_valid_count = quick_affine_count(trial_controls);
            const int gain = trial_valid_count - current_valid_count;
            const ConeCoverage coverage = cone_coverage[candidate];
            const bool better = best < 0
                || gain > best_gain
                || (gain == best_gain
                    && coverage.property_roots > best_cone.property_roots)
                || (gain == best_gain
                    && coverage.property_roots == best_cone.property_roots
                    && coverage.next_roots > best_cone.next_roots)
                || (gain == best_gain
                    && coverage.property_roots == best_cone.property_roots
                    && coverage.next_roots == best_cone.next_roots
                    && occurrences[candidate] > best_occurrence);
            if(better){
                best = candidate;
                best_gain = gain;
                best_cone = coverage;
                best_occurrence = occurrences[candidate];
            }
        }
        if(best < 0)
            break;
        // If no single control has immediate gain, keep one cone-dominant seed
        // so that the second greedy step can expose two-control mux patterns.
        if(best_gain <= 0 && !guarded_affine_controls.empty())
            break;
        guarded_affine_controls.push_back(best);
        guarded_affine_selection_next_roots += best_cone.next_roots;
        guarded_affine_selection_property_roots += best_cone.property_roots;
        current_valid_count += best_gain;
    }

    if(guarded_affine_controls.empty())
        return;
    GuardEvaluation current = evaluate_controls(guarded_affine_controls);
    if(current.valid_count <= affine_next_count){
        guarded_affine_controls.clear();
        guarded_affine_selection_next_roots = 0;
        guarded_affine_selection_property_roots = 0;
        return;
    }
    guarded_affine_selection_gain = current.valid_count - affine_next_count;
    const int mode_count = 1 << guarded_affine_controls.size();
    for(int latch_index = 0; latch_index < num_latches; ++latch_index){
        if(static_cast<int>(current.modes_by_latch[latch_index].size())
                != mode_count)
            continue;
        guarded_affine_next_valid[latch_index] = 1;
        guarded_affine_next_modes[latch_index].swap(
            current.modes_by_latch[latch_index]);
        ++guarded_affine_next_count;
        guarded_affine_modes += mode_count;
        for(const GuardedAffineMode &mode : guarded_affine_next_modes[latch_index]){
            guarded_affine_support_sum += mode.support.size();
            guarded_affine_support_max = std::max(
                guarded_affine_support_max,
                static_cast<int>(mode.support.size()));
        }
    }
}

bool PDR::validate_guarded_affine_transition(){
    if(is_reverse() || guarded_affine_next_count == 0)
        return false;

    CMSatSolver solver;
    solver.add(-1);
    solver.add(0);
    set<int> next_cone;
    for(int latch_index = 0; latch_index < num_latches; ++latch_index)
        if(guarded_affine_next_valid[latch_index])
            next_cone.insert(abs(nexts[latch_index]));
    encode_gate_cone(&solver, next_cone);
    solver.reserve_variables(2 * primed_first_dimacs + 2);

    const int mode_count = 1 << guarded_affine_controls.size();
    for(int mode_index = 0; mode_index < mode_count; ++mode_index){
        vector<int> mismatches;
        vector<int> guard;
        for(int latch_index = 0; latch_index < num_latches; ++latch_index){
            if(!guarded_affine_next_valid[latch_index])
                continue;
            const GuardedAffineMode &mode =
                guarded_affine_next_modes[latch_index][mode_index];
            guard = mode.guard;
            const int summary = solver.fresh_variable();
            vector<int> equation = mode.support;
            equation.push_back(summary);
            solver.add_xor_clause(equation, mode.rhs != 0);
            const int mismatch = solver.fresh_variable();
            vector<int> difference;
            difference.push_back(mismatch);
            difference.push_back(summary);
            difference.push_back(nexts[latch_index]);
            solver.add_xor_clause(difference, false);
            mismatches.push_back(mismatch);
        }
        const int activation = solver.fresh_variable();
        solver.add(-activation);
        for(int mismatch : mismatches)
            solver.add(mismatch);
        solver.add(0);
        solver.assume(activation);
        for(int literal : guard)
            solver.assume(literal);
        if(solver.solve() != UNSAT)
            return false;
    }
    return true;
}

void PDR::analyze_affine_invariants(){
    const auto started = std::chrono::steady_clock::now();
    affine_parity_invariants.clear();
    affine_invariants_model_validated = false;
    affine_invariants_prove_target = false;
    affine_invariants_guarded = false;
    affine_invariants_conditioned = false;
    affine_invariants_partial = false;
    affine_invariants_modes = 0;
    affine_invariants_tracked_latches = 0;
    affine_invariants_abstracted_latches = 0;
    affine_invariants_reachable_rank = 0;
    affine_invariants_closure_rounds = 0;
    affine_invariants_reachable_modes = 0;
    affine_invariants_support_sum = 0;
    affine_invariants_support_max = 0;
    affine_invariants_selected = 0;
    affine_invariants_encoded = 0;
    affine_invariants_conditioned_encoded = 0;
    affine_invariants_conditioned_clauses = 0;
    affine_invariants_conditioned_feedback_selected = 0;

    if(is_reverse() || num_latches <= 0)
        return;

    // Missing next-state equations are soundly abstracted as independent
    // nondeterministic bits below.  This lets a property-local affine cone
    // contribute invariants even when unrelated RTL state is nonlinear.
    const bool use_guarded = guarded_affine_next_count > affine_next_count
        && !guarded_affine_controls.empty();
    const bool use_plain = affine_next_count > 0;
    if(!use_guarded && !use_plain)
        return;

    int guarded_template_latch = -1;
    if(use_guarded)
        for(int latch_index = 0; latch_index < num_latches; ++latch_index)
            if(guarded_affine_next_valid[latch_index]){
                guarded_template_latch = latch_index;
                break;
            }

    if(use_guarded){
        affine_invariants_guarded = true;
        affine_invariants_modes = static_cast<int>(
            guarded_affine_next_modes[guarded_template_latch].size());
        affine_invariants_tracked_latches = guarded_affine_next_count;
        if(affine_invariants_modes <= 0)
            return;
        if(!guarded_affine_validation_attempted){
            guarded_affine_validation_attempted = true;
            guarded_affine_validation_passed = validate_guarded_affine_transition();
        }
        affine_invariants_model_validated = guarded_affine_validation_passed;
    }else{
        affine_invariants_modes = 1;
        affine_invariants_tracked_latches = affine_next_count;
        CMSatSolver validator;
        validator.add(-1);
        validator.add(0);
        set<int> cone;
        for(int latch_index = 0; latch_index < num_latches; ++latch_index)
            if(affine_next_valid[latch_index])
                cone.insert(abs(nexts[latch_index]));
        encode_gate_cone(&validator, cone);
        vector<int> mismatches;
        for(int latch_index = 0; latch_index < num_latches; ++latch_index){
            if(!affine_next_valid[latch_index])
                continue;
            const int summary = validator.fresh_variable();
            vector<int> equation = affine_next_supports[latch_index];
            equation.push_back(summary);
            validator.add_xor_clause(
                equation, affine_next_rhs[latch_index] != 0);
            const int mismatch = validator.fresh_variable();
            vector<int> difference = {
                mismatch, summary, nexts[latch_index]
            };
            validator.add_xor_clause(difference, false);
            mismatches.push_back(mismatch);
        }
        const int activation = validator.fresh_variable();
        validator.add(-activation);
        for(int mismatch : mismatches)
            validator.add(mismatch);
        validator.add(0);
        validator.assume(activation);
        affine_invariants_model_validated = validator.solve() == UNSAT;
    }
    if(!affine_invariants_model_validated)
        return;
    affine_invariants_abstracted_latches =
        num_latches - affine_invariants_tracked_latches;
    affine_invariants_partial = affine_invariants_abstracted_latches > 0;

    using Bits = vector<std::uint64_t>;
    const int words = (num_latches + 63) / 64;
    auto zero = [&](){ return Bits(words, 0); };
    auto test = [](const Bits &bits, int index){
        return (bits[index / 64] >> (index % 64)) & 1ULL;
    };
    auto toggle = [](Bits &bits, int index){
        bits[index / 64] ^= 1ULL << (index % 64);
    };
    auto xor_into = [](Bits &left, const Bits &right){
        for(size_t word = 0; word < left.size(); ++word)
            left[word] ^= right[word];
    };
    auto parity = [](const Bits &left, const Bits &right){
        unsigned value = 0;
        for(size_t word = 0; word < left.size(); ++word)
            value ^= static_cast<unsigned>(
                __builtin_parityll(left[word] & right[word]));
        return (value & 1U) != 0;
    };

    struct ModeMatrix {
        vector<Bits> rows;
        vector<Bits> input_columns;
        Bits constant;
    };
    vector<ModeMatrix> matrices;
    matrices.reserve(affine_invariants_modes);
    const int first_input = unprimed_first_dimacs;
    const int first_latch = unprimed_first_dimacs + num_inputs;
    bool closed = true;
    for(int mode_index = 0; mode_index < affine_invariants_modes; ++mode_index){
        ModeMatrix matrix;
        matrix.rows.assign(num_latches, zero());
        matrix.input_columns.assign(num_inputs, zero());
        matrix.constant = zero();
        for(int latch_index = 0; latch_index < num_latches; ++latch_index){
            const bool tracked = use_guarded
                ? guarded_affine_next_valid[latch_index] != 0
                : affine_next_valid[latch_index] != 0;
            if(!tracked){
                // An independent direction for this next-state bit is the
                // exact affine representation of nondeterministic abstraction.
                Bits nondeterministic = zero();
                toggle(nondeterministic, latch_index);
                matrix.input_columns.push_back(std::move(nondeterministic));
                continue;
            }
            const vector<int> *support = nullptr;
            bool rhs = false;
            if(use_guarded){
                const GuardedAffineMode &mode =
                    guarded_affine_next_modes[latch_index][mode_index];
                support = &mode.support;
                rhs = mode.rhs != 0;
            }else{
                support = &affine_next_supports[latch_index];
                rhs = affine_next_rhs[latch_index] != 0;
            }
            if(rhs)
                toggle(matrix.constant, latch_index);
            for(int variable : *support){
                if(variable >= first_input
                   && variable < first_input + num_inputs){
                    toggle(matrix.input_columns[variable - first_input],
                           latch_index);
                }else if(variable >= first_latch
                         && variable < first_latch + num_latches){
                    toggle(matrix.rows[latch_index], variable - first_latch);
                }else{
                    closed = false;
                }
            }
        }
        matrices.push_back(std::move(matrix));
    }
    if(!closed)
        return;

    vector<Bits> basis(num_latches, zero());
    vector<char> has_pivot(num_latches, 0);
    int rank = 0;
    auto insert_basis = [&](Bits row){
        for(int pivot = 0; pivot < num_latches; ++pivot){
            if(!test(row, pivot))
                continue;
            if(has_pivot[pivot]){
                xor_into(row, basis[pivot]);
                continue;
            }
            for(int other = 0; other < num_latches; ++other)
                if(has_pivot[other] && test(basis[other], pivot))
                    xor_into(basis[other], row);
            basis[pivot] = std::move(row);
            has_pivot[pivot] = 1;
            ++rank;
            return true;
        }
        return false;
    };

    Bits offset = zero();
    vector<char> fixed(num_latches, -1);
    for(int literal : init_state){
        const int index = abs(literal) - first_latch;
        if(index >= 0 && index < num_latches)
            fixed[index] = literal > 0 ? 1 : 0;
    }
    for(int latch_index = 0; latch_index < num_latches; ++latch_index){
        if(fixed[latch_index] > 0)
            toggle(offset, latch_index);
        if(fixed[latch_index] < 0){
            Bits direction = zero();
            toggle(direction, latch_index);
            insert_basis(std::move(direction));
        }
    }

    // A guarded transition often has no useful invariant once every guard
    // mode is merged together.  When the guards are state bits, retain those
    // modes as a finite control partition and close one affine hull per mode.
    bool latch_conditioned = use_guarded;
    vector<int> control_latch_indices;
    for(int control : guarded_affine_controls){
        const int index = control - first_latch;
        if(index < 0 || index >= num_latches){
            latch_conditioned = false;
            break;
        }
        control_latch_indices.push_back(index);
    }
    if(latch_conditioned){
        struct AffineSpace {
            bool valid = false;
            Bits offset;
            vector<Bits> directions;
        };
        auto canonicalize = [&](AffineSpace &space){
            vector<Bits> local_basis(num_latches, zero());
            vector<char> local_pivots(num_latches, 0);
            for(Bits row : space.directions){
                for(int pivot = 0; pivot < num_latches; ++pivot){
                    if(!test(row, pivot))
                        continue;
                    if(local_pivots[pivot]){
                        xor_into(row, local_basis[pivot]);
                        continue;
                    }
                    for(int other = 0; other < num_latches; ++other)
                        if(local_pivots[other]
                           && test(local_basis[other], pivot))
                            xor_into(local_basis[other], row);
                    local_basis[pivot] = std::move(row);
                    local_pivots[pivot] = 1;
                    break;
                }
            }
            space.directions.clear();
            for(int pivot = 0; pivot < num_latches; ++pivot)
                if(local_pivots[pivot])
                    space.directions.push_back(local_basis[pivot]);
        };
        auto intersect_bit = [&](AffineSpace &space, int index, bool value){
            int selected = -1;
            for(size_t i = 0; i < space.directions.size(); ++i)
                if(test(space.directions[i], index)){
                    selected = static_cast<int>(i);
                    break;
                }
            if(selected < 0){
                if(test(space.offset, index) != value)
                    space.valid = false;
                return;
            }
            const Bits pivot = space.directions[selected];
            if(test(space.offset, index) != value)
                xor_into(space.offset, pivot);
            vector<Bits> reduced;
            for(size_t i = 0; i < space.directions.size(); ++i){
                if(static_cast<int>(i) == selected)
                    continue;
                Bits row = space.directions[i];
                if(test(row, index))
                    xor_into(row, pivot);
                reduced.push_back(std::move(row));
            }
            space.directions.swap(reduced);
            canonicalize(space);
        };
        auto add_space = [&](AffineSpace &target, const AffineSpace &source){
            if(!source.valid)
                return false;
            if(!target.valid){
                target = source;
                canonicalize(target);
                return true;
            }
            const size_t old_rank = target.directions.size();
            Bits delta = source.offset;
            xor_into(delta, target.offset);
            target.directions.push_back(std::move(delta));
            target.directions.insert(target.directions.end(),
                                     source.directions.begin(),
                                     source.directions.end());
            canonicalize(target);
            return target.directions.size() != old_rank;
        };
        auto apply_space = [&](const ModeMatrix &matrix,
                               const AffineSpace &source){
            AffineSpace image;
            image.valid = source.valid;
            image.offset = zero();
            for(int latch_index = 0; latch_index < num_latches;
                ++latch_index)
                if(parity(matrix.rows[latch_index], source.offset))
                    toggle(image.offset, latch_index);
            xor_into(image.offset, matrix.constant);
            for(const Bits &direction : source.directions){
                Bits mapped = zero();
                for(int latch_index = 0; latch_index < num_latches;
                    ++latch_index)
                    if(parity(matrix.rows[latch_index], direction))
                        toggle(mapped, latch_index);
                image.directions.push_back(std::move(mapped));
            }
            image.directions.insert(image.directions.end(),
                                    matrix.input_columns.begin(),
                                    matrix.input_columns.end());
            canonicalize(image);
            return image;
        };

        AffineSpace initial;
        initial.valid = true;
        initial.offset = offset;
        for(int pivot = 0; pivot < num_latches; ++pivot)
            if(has_pivot[pivot])
                initial.directions.push_back(basis[pivot]);
        vector<AffineSpace> spaces(affine_invariants_modes);
        for(int mode = 0; mode < affine_invariants_modes; ++mode){
            AffineSpace partition = initial;
            for(size_t control = 0; control < control_latch_indices.size();
                ++control)
                intersect_bit(partition, control_latch_indices[control],
                              (mode & (1 << control)) != 0);
            add_space(spaces[mode], partition);
        }

        bool phase_changed = true;
        while(phase_changed){
            phase_changed = false;
            ++affine_invariants_closure_rounds;
            for(int source = 0; source < affine_invariants_modes; ++source){
                if(!spaces[source].valid)
                    continue;
                const AffineSpace image = apply_space(matrices[source],
                                                      spaces[source]);
                for(int target = 0; target < affine_invariants_modes;
                    ++target){
                    AffineSpace partition = image;
                    for(size_t control = 0;
                        control < control_latch_indices.size(); ++control)
                        intersect_bit(partition, control_latch_indices[control],
                                      (target & (1 << control)) != 0);
                    phase_changed = add_space(spaces[target], partition)
                        || phase_changed;
                }
            }
        }

        affine_invariants_conditioned = true;
        int maximum_rank = 0;
        std::unordered_set<int> controls(guarded_affine_controls.begin(),
                                          guarded_affine_controls.end());
        for(int mode = 0; mode < affine_invariants_modes; ++mode){
            if(!spaces[mode].valid)
                continue;
            ++affine_invariants_reachable_modes;
            maximum_rank = std::max(maximum_rank,
                static_cast<int>(spaces[mode].directions.size()));
            vector<Bits> mode_basis(num_latches, zero());
            vector<char> mode_pivots(num_latches, 0);
            for(Bits row : spaces[mode].directions){
                for(int pivot = 0; pivot < num_latches; ++pivot){
                    if(!test(row, pivot))
                        continue;
                    if(mode_pivots[pivot]){
                        xor_into(row, mode_basis[pivot]);
                        continue;
                    }
                    for(int other = 0; other < num_latches; ++other)
                        if(mode_pivots[other]
                           && test(mode_basis[other], pivot))
                            xor_into(mode_basis[other], row);
                    mode_basis[pivot] = std::move(row);
                    mode_pivots[pivot] = 1;
                    break;
                }
            }
            for(int free_variable = 0; free_variable < num_latches;
                ++free_variable){
                if(mode_pivots[free_variable])
                    continue;
                Bits normal = zero();
                toggle(normal, free_variable);
                for(int pivot = 0; pivot < num_latches; ++pivot)
                    if(mode_pivots[pivot]
                       && test(mode_basis[pivot], free_variable))
                        toggle(normal, pivot);
                AffineParityInvariant invariant;
                invariant.guard =
                    guarded_affine_next_modes[guarded_template_latch][mode].guard;
                bool has_data = false;
                for(int latch_index = 0; latch_index < num_latches;
                    ++latch_index){
                    if(!test(normal, latch_index))
                        continue;
                    const int variable = first_latch + latch_index;
                    invariant.support.push_back(variable);
                    has_data = has_data || controls.find(variable)
                        == controls.end();
                }
                if(!has_data)
                    continue;
                invariant.rhs = static_cast<char>(
                    parity(normal, spaces[mode].offset));
                affine_invariants_support_sum += invariant.support.size();
                affine_invariants_support_max = std::max(
                    affine_invariants_support_max,
                    static_cast<int>(invariant.support.size()));
                affine_parity_invariants.push_back(std::move(invariant));
            }
        }
        affine_invariants_reachable_rank = maximum_rank;
        for(const AffineParityInvariant &invariant : affine_parity_invariants)
            if(static_cast<int>(invariant.support.size())
                    <= affine_invariants_max_width)
                ++affine_invariants_selected;

        if(affine_invariants_direct_check && !affine_parity_invariants.empty()){
            // Check one disjoint control mode at a time.  The mode guards
            // cover every valuation of the selected latch controls, so the
            // conjunction of these UNSAT checks proves Inv => !bad.  Keeping
            // the rows separated also keeps CMSat's Gaussian matrices small.
            affine_invariants_prove_target = true;
            for(int mode = 0; mode < affine_invariants_modes; ++mode){
                if(!spaces[mode].valid)
                    continue;
                CMSatSolver property_check;
                property_check.add(-1);
                property_check.add(0);
                for(const AffineParityInvariant &invariant
                        : affine_parity_invariants){
                    if(invariant.guard
                       != guarded_affine_next_modes[guarded_template_latch][mode].guard)
                        continue;
                    property_check.add_xor_clause(
                        invariant.support, invariant.rhs != 0);
                }
                for(int guard
                        : guarded_affine_next_modes[guarded_template_latch][mode].guard){
                    property_check.add(guard);
                    property_check.add(0);
                }
                set<int> cone;
                cone.insert(abs(bad));
                for(int constraint : constraints)
                    cone.insert(abs(constraint));
                encode_gate_cone(&property_check, cone);
                property_check.add(bad);
                property_check.add(0);
                for(int constraint : constraints){
                    property_check.add(constraint);
                    property_check.add(0);
                }
                if(property_check.solve() != UNSAT){
                    affine_invariants_prove_target = false;
                    break;
                }
            }
        }
        affine_invariants_seconds = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - started).count();
        return;
    }

    auto apply = [&](const ModeMatrix &matrix, const Bits &state){
        Bits result = zero();
        for(int latch_index = 0; latch_index < num_latches; ++latch_index)
            if(parity(matrix.rows[latch_index], state))
                toggle(result, latch_index);
        return result;
    };

    bool changed = true;
    while(changed && rank < num_latches){
        changed = false;
        ++affine_invariants_closure_rounds;
        vector<Bits> directions;
        for(int pivot = 0; pivot < num_latches; ++pivot)
            if(has_pivot[pivot])
                directions.push_back(basis[pivot]);
        for(const ModeMatrix &matrix : matrices){
            Bits next_offset = apply(matrix, offset);
            xor_into(next_offset, matrix.constant);
            xor_into(next_offset, offset);
            changed = insert_basis(std::move(next_offset)) || changed;
            for(const Bits &direction : directions)
                changed = insert_basis(apply(matrix, direction)) || changed;
            for(const Bits &input : matrix.input_columns)
                changed = insert_basis(input) || changed;
        }
    }
    affine_invariants_reachable_rank = rank;

    for(int free_variable = 0; free_variable < num_latches; ++free_variable){
        if(has_pivot[free_variable])
            continue;
        Bits normal = zero();
        toggle(normal, free_variable);
        for(int pivot = 0; pivot < num_latches; ++pivot)
            if(has_pivot[pivot] && test(basis[pivot], free_variable))
                toggle(normal, pivot);
        AffineParityInvariant invariant;
        for(int latch_index = 0; latch_index < num_latches; ++latch_index)
            if(test(normal, latch_index))
                invariant.support.push_back(first_latch + latch_index);
        invariant.rhs = static_cast<char>(parity(normal, offset));
        affine_invariants_support_sum += invariant.support.size();
        affine_invariants_support_max = std::max(
            affine_invariants_support_max,
            static_cast<int>(invariant.support.size()));
        affine_parity_invariants.push_back(std::move(invariant));
    }
    for(const AffineParityInvariant &invariant : affine_parity_invariants)
        if(static_cast<int>(invariant.support.size())
                <= affine_invariants_max_width)
            ++affine_invariants_selected;

    if(affine_invariants_direct_check && !affine_parity_invariants.empty()){
        CMSatSolver property_check;
        property_check.add(-1);
        property_check.add(0);
        for(const AffineParityInvariant &invariant : affine_parity_invariants)
            property_check.add_xor_clause(
                invariant.support, invariant.rhs != 0);
        set<int> cone;
        cone.insert(abs(bad));
        for(int constraint : constraints)
            cone.insert(abs(constraint));
        encode_gate_cone(&property_check, cone);
        property_check.add(bad);
        property_check.add(0);
        for(int constraint : constraints){
            property_check.add(constraint);
            property_check.add(0);
        }
        affine_invariants_prove_target = property_check.solve() == UNSAT;
    }
    affine_invariants_seconds = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - started).count();
}

void PDR::encode_affine_parity_invariants(
    SATSolver *s, bool current, bool primed){
    if(!affine_invariants_enabled || !affine_invariants_model_validated
       || affine_parity_invariants.empty() || !s->supports_native_xor())
        return;
    vector<const AffineParityInvariant *> feedback_rows;
    if(affine_invariants_conditioned_feedback){
        for(const AffineParityInvariant &invariant : affine_parity_invariants)
            if(!invariant.guard.empty()
               && static_cast<int>(invariant.support.size())
                      <= affine_invariants_max_width)
                feedback_rows.push_back(&invariant);
        auto relevance = [&](const AffineParityInvariant *invariant){
            int score = 0;
            for(int variable : invariant->support){
                const int latch_index = variable
                    - (unprimed_first_dimacs + num_inputs);
                if(latch_index < 0 || latch_index >= num_latches)
                    continue;
                const int distance = latch_bad_distance[latch_index];
                if(distance >= 0)
                    score += std::max(1, 64 - distance);
            }
            return score;
        };
        std::sort(feedback_rows.begin(), feedback_rows.end(),
            [&](const AffineParityInvariant *lhs,
                const AffineParityInvariant *rhs){
                const int lhs_relevance = relevance(lhs);
                const int rhs_relevance = relevance(rhs);
                if(lhs_relevance != rhs_relevance)
                    return lhs_relevance > rhs_relevance;
                if(lhs->support.size() != rhs->support.size())
                    return lhs->support.size() < rhs->support.size();
                if(lhs->guard.size() != rhs->guard.size())
                    return lhs->guard.size() < rhs->guard.size();
                return lhs->support < rhs->support;
            });
        if(affine_invariants_conditioned_feedback_max_rows > 0
           && static_cast<int>(feedback_rows.size())
                  > affine_invariants_conditioned_feedback_max_rows){
            // Retain one high-relevance row for each reachable control mode
            // before filling the remaining budget.  A short row from only
            // one phase can otherwise erase another phase entirely.
            vector<const AffineParityInvariant *> selected;
            set<vector<int> > covered_guards;
            for(const AffineParityInvariant *row : feedback_rows){
                if(static_cast<int>(selected.size())
                   >= affine_invariants_conditioned_feedback_max_rows)
                    break;
                if(covered_guards.insert(row->guard).second)
                    selected.push_back(row);
            }
            for(const AffineParityInvariant *row : feedback_rows){
                if(static_cast<int>(selected.size())
                   >= affine_invariants_conditioned_feedback_max_rows)
                    break;
                if(std::find(selected.begin(), selected.end(), row)
                   == selected.end())
                    selected.push_back(row);
            }
            feedback_rows.swap(selected);
        }
        affine_invariants_conditioned_feedback_selected =
            static_cast<int>(feedback_rows.size());
    }
    for(const AffineParityInvariant &invariant : affine_parity_invariants){
        if(static_cast<int>(invariant.support.size())
                > affine_invariants_max_width)
            continue;
        if(!invariant.guard.empty()){
            if(!affine_invariants_conditioned_feedback)
                continue;
            if(std::find(feedback_rows.begin(), feedback_rows.end(),
                         &invariant) == feedback_rows.end())
                continue;
            // guard -> XOR(support) = rhs.  The fresh bit is one precisely
            // when the parity is violated, making the implication one clause.
            s->reserve_variables(2 * primed_first_dimacs + 2);
            auto add_conditioned = [&](bool use_primed){
                vector<int> equation;
                equation.reserve(invariant.support.size() + 1);
                for(int literal : invariant.support)
                    equation.push_back(use_primed ? prime_lit(literal)
                                                   : literal);
                const int violation = s->fresh_variable();
                equation.push_back(violation);
                s->add_xor_clause(equation, invariant.rhs != 0);
                for(int literal : invariant.guard)
                    s->add(use_primed ? -prime_lit(literal) : -literal);
                s->add(-violation);
                s->add(0);
                ++affine_invariants_encoded;
                ++affine_invariants_conditioned_encoded;
                ++affine_invariants_conditioned_clauses;
            };
            if(current)
                add_conditioned(false);
            if(primed)
                add_conditioned(true);
            continue;
        }
        if(current){
            s->add_xor_clause(invariant.support, invariant.rhs != 0);
            ++affine_invariants_encoded;
        }
        if(primed){
            vector<int> equation;
            equation.reserve(invariant.support.size());
            for(int variable : invariant.support)
                equation.push_back(prime_var(variable));
            s->add_xor_clause(equation, invariant.rhs != 0);
            ++affine_invariants_encoded;
        }
    }
}

bool PDR::encode_affine_next_summary(SATSolver *s, int latch_index){
    if(!affine_summary_enabled || is_reverse()
       || latch_index < 0 || latch_index >= num_latches)
        return false;
    const int latch = 1 + num_inputs + latch_index + 1;
    const int primed_latch = prime_lit(latch);
    if(affine_next_valid[latch_index]){
        vector<int> equation = affine_next_supports[latch_index];
        equation.push_back(primed_latch);
        s->add_xor_clause(equation, affine_next_rhs[latch_index] != 0);
        ++affine_summary_equations;
        affine_summary_literals += equation.size();
        return true;
    }
    if(!guarded_affine_enabled
       || !guarded_affine_next_valid[latch_index])
        return false;

    s->reserve_variables(2 * primed_first_dimacs + 2);
    for(const GuardedAffineMode &mode : guarded_affine_next_modes[latch_index]){
        const int summary = s->fresh_variable();
        vector<int> equation = mode.support;
        equation.push_back(summary);
        s->add_xor_clause(equation, mode.rhs != 0);
        for(int guard_literal : mode.guard)
            s->add(-guard_literal);
        s->add(-primed_latch); s->add(summary); s->add(0);
        for(int guard_literal : mode.guard)
            s->add(-guard_literal);
        s->add(primed_latch); s->add(-summary); s->add(0);
        ++guarded_affine_encoded_modes;
        guarded_affine_guard_clauses += 2;
        ++affine_summary_equations;
        affine_summary_literals += equation.size();
    }
    return true;
}

void PDR::encode_xor_cnf(
    SATSolver *s, const vector<int> &equation, bool rhs){
    auto add_binary = [s, this](int first, int second){
        s->add(first); s->add(second); s->add(0);
        ++cadical_affine_hint_clauses;
    };
    auto add_xor_gate = [s, this](int output, int left, int right){
        s->add(-output); s->add(left); s->add(right); s->add(0);
        s->add(-output); s->add(-left); s->add(-right); s->add(0);
        s->add(output); s->add(-left); s->add(right); s->add(0);
        s->add(output); s->add(left); s->add(-right); s->add(0);
        cadical_affine_hint_clauses += 4;
    };

    if(equation.empty()){
        if(rhs){
            s->add(0);
            ++cadical_affine_hint_clauses;
        }
        return;
    }
    if(equation.size() == 1){
        s->add(rhs ? equation[0] : -equation[0]); s->add(0);
        ++cadical_affine_hint_clauses;
        return;
    }
    if(equation.size() == 2){
        const int left = equation[0], right = equation[1];
        if(rhs){
            add_binary(left, right);
            add_binary(-left, -right);
        }else{
            add_binary(-left, right);
            add_binary(left, -right);
        }
        return;
    }

    int accumulator = s->fresh_variable();
    add_xor_gate(accumulator, equation[0], equation[1]);
    for(size_t index = 2; index + 1 < equation.size(); ++index){
        const int next = s->fresh_variable();
        add_xor_gate(next, accumulator, equation[index]);
        accumulator = next;
    }
    const int last = equation.back();
    if(rhs){
        add_binary(accumulator, last);
        add_binary(-accumulator, -last);
    }else{
        add_binary(-accumulator, last);
        add_binary(accumulator, -last);
    }
}

void PDR::encode_affine_hints_cnf(SATSolver *s){
    if(!cadical_affine_hints_enabled || is_reverse())
        return;
    // Reserve the complete possible primed structural range before allocating
    // auxiliary variables for parity chains.
    s->reserve_variables(2 * primed_first_dimacs + 2);
    for(int latch_index = 0; latch_index < num_latches; ++latch_index){
        if(!affine_next_valid[latch_index])
            continue;
        vector<int> equation = affine_next_supports[latch_index];
        const int latch = 1 + num_inputs + latch_index + 1;
        equation.push_back(prime_lit(latch));
        encode_xor_cnf(s, equation, affine_next_rhs[latch_index] != 0);
        ++cadical_affine_hint_equations;
    }
}

void PDR::encode_affine_island_summaries(
    SATSolver *s, const set<int> &cone, bool primed){
    if(!affine_island_summary_enabled || !s->supports_native_xor())
        return;
    for(const AffineIslandSummary &summary : affine_island_summaries){
        if(cone.find(summary.root) == cone.end())
            continue;
        vector<int> equation;
        equation.reserve(summary.support.size() + 1);
        equation.push_back(primed ? prime_lit(summary.root) : summary.root);
        for(int variable : summary.support)
            equation.push_back(primed ? prime_lit(variable) : variable);
        s->add_xor_clause(equation, summary.rhs != 0);
        ++affine_island_encoded_equations;
        affine_island_encoded_literals += equation.size();
    }
}

void PDR::encode_gate_cone(SATSolver *s, set<int> &lit_set){
    vector<pair<int, And> > gates;
    for(size_t i=0; i<ands.size(); ++i) gates.push_back(make_pair(0, ands[i]));
    for(size_t i=0; i<xors.size(); ++i) gates.push_back(make_pair(1, xors[i]));
    for(size_t i=0; i<ors.size(); ++i)  gates.push_back(make_pair(2, ors[i]));
    sort(gates.begin(), gates.end(), [](const pair<int, And> &a, const pair<int, And> &b){ return a.second.o < b.second.o; });

    std::unordered_set<int> replaced;
    std::unordered_map<int, const AffineIslandSummary *> summaries;
    if(affine_island_summary_enabled && affine_island_replace_enabled)
        for(const AffineIslandSummary &summary : affine_island_summaries)
            summaries.emplace(summary.root, &summary);
    for(auto it = gates.rbegin(); it != gates.rend(); ++it){
        const And &g = it->second;
        assert(g.o > 0);
        if(lit_set.find(g.o) == lit_set.end())
            continue;
        auto summary = summaries.find(g.o);
        if(summary != summaries.end())
            replaced.insert(summary->second->xor_variables.begin(),
                            summary->second->xor_variables.end());
        lit_set.insert(abs(g.i1));
        lit_set.insert(abs(g.i2));
        if(replaced.find(g.o) == replaced.end())
            encode_gate(s, g, it->first);
        else
            ++affine_island_replaced_gates;
    }
    encode_affine_island_summaries(s, lit_set, false);
}

void PDR::encode_gate_cone_with_prime(SATSolver *s, set<int> &lit_set, set<int> &prime_lit_set){
    vector<pair<int, And> > gates;
    for(size_t i=0; i<ands.size(); ++i) gates.push_back(make_pair(0, ands[i]));
    for(size_t i=0; i<xors.size(); ++i) gates.push_back(make_pair(1, xors[i]));
    for(size_t i=0; i<ors.size(); ++i)  gates.push_back(make_pair(2, ors[i]));
    sort(gates.begin(), gates.end(), [](const pair<int, And> &a, const pair<int, And> &b){ return a.second.o < b.second.o; });

    std::unordered_set<int> replaced;
    std::unordered_set<int> prime_replaced;
    std::unordered_map<int, const AffineIslandSummary *> summaries;
    if(affine_island_summary_enabled && affine_island_replace_enabled)
        for(const AffineIslandSummary &summary : affine_island_summaries)
            summaries.emplace(summary.root, &summary);
    for(auto it = gates.rbegin(); it != gates.rend(); ++it){
        const And &g = it->second;
        assert(g.o > 0);
        if(lit_set.find(g.o) != lit_set.end()){
            auto summary = summaries.find(g.o);
            if(summary != summaries.end())
                replaced.insert(summary->second->xor_variables.begin(),
                                summary->second->xor_variables.end());
            lit_set.insert(abs(g.i1));
            lit_set.insert(abs(g.i2));
            if(replaced.find(g.o) == replaced.end())
                encode_gate(s, g, it->first);
            else
                ++affine_island_replaced_gates;

            if(prime_lit_set.find(g.o) != prime_lit_set.end()){
                if(summary != summaries.end())
                    prime_replaced.insert(
                        summary->second->xor_variables.begin(),
                        summary->second->xor_variables.end());
                And pg(prime_lit(g.o), prime_lit(g.i1), prime_lit(g.i2));
                prime_lit_set.insert(abs(g.i1));
                prime_lit_set.insert(abs(g.i2));
                if(prime_replaced.find(g.o) == prime_replaced.end())
                    encode_gate(s, pg, it->first);
                else
                    ++affine_island_replaced_gates;
            }
        }
    }
    encode_affine_island_summaries(s, lit_set, false);
    encode_affine_island_summaries(s, prime_lit_set, true);
}

void PDR::encode_gate_cone_with_prime_boundary_bve(
    SATSolver *s, set<int> &lit_set, set<int> &prime_lit_set,
    vector<int> &cached_cnf){
    struct GateInstance {
        int type;
        And gate;
    };

    vector<pair<int, And> > gates;
    for(const And &gate : ands) gates.push_back(make_pair(0, gate));
    for(const And &gate : xors) gates.push_back(make_pair(1, gate));
    for(const And &gate : ors)  gates.push_back(make_pair(2, gate));
    sort(gates.begin(), gates.end(), [](const pair<int, And> &left,
                                       const pair<int, And> &right){
        return left.second.o < right.second.o;
    });

    set<int> boundary_roots = lit_set;
    for(int variable : prime_lit_set)
        boundary_roots.insert(prime_var(variable));

    std::unordered_set<int> replaced;
    std::unordered_set<int> prime_replaced;
    std::unordered_map<int, const AffineIslandSummary *> summaries;
    if(affine_island_summary_enabled && affine_island_replace_enabled)
        for(const AffineIslandSummary &summary : affine_island_summaries)
            summaries.emplace(summary.root, &summary);

    vector<GateInstance> cnf_gates;
    vector<GateInstance> xor_gates;
    auto collect_instance = [&](int type, const And &gate, bool skip){
        if(skip){
            ++affine_island_replaced_gates;
            return;
        }
        if(type == 1)
            xor_gates.push_back({type, gate});
        else
            cnf_gates.push_back({type, gate});
    };

    for(auto it = gates.rbegin(); it != gates.rend(); ++it){
        const int type = it->first;
        const And &gate = it->second;
        if(lit_set.find(gate.o) != lit_set.end()){
            auto summary = summaries.find(gate.o);
            if(summary != summaries.end())
                replaced.insert(summary->second->xor_variables.begin(),
                                summary->second->xor_variables.end());
            lit_set.insert(abs(gate.i1));
            lit_set.insert(abs(gate.i2));
            collect_instance(type, gate, replaced.find(gate.o) != replaced.end());
        }
        if(prime_lit_set.find(gate.o) != prime_lit_set.end()){
            auto summary = summaries.find(gate.o);
            if(summary != summaries.end())
                prime_replaced.insert(summary->second->xor_variables.begin(),
                                      summary->second->xor_variables.end());
            prime_lit_set.insert(abs(gate.i1));
            prime_lit_set.insert(abs(gate.i2));
            And primed_gate(prime_lit(gate.o), prime_lit(gate.i1),
                            prime_lit(gate.i2));
            collect_instance(type, primed_gate,
                             prime_replaced.find(gate.o) != prime_replaced.end());
        }
    }

    for(const GateInstance &instance : xor_gates)
        encode_gate(s, instance.gate, instance.type);

    if(cached_cnf.empty()){
        minisatSimp simplifier;

        std::unordered_map<int, int> consumers;
        std::unordered_set<int> cnf_outputs;
        std::unordered_set<int> touched;
        for(const GateInstance &instance : cnf_gates){
            const And &gate = instance.gate;
            cnf_outputs.insert(abs(gate.o));
            touched.insert(abs(gate.o));
            touched.insert(abs(gate.i1));
            touched.insert(abs(gate.i2));
            ++consumers[abs(gate.i1)];
            ++consumers[abs(gate.i2)];
        }

        if(cnf_gates.empty()){
            cached_cnf = {1, -1, 0};
            for(int literal : cached_cnf)
                s->add(literal);
            encode_affine_island_summaries(s, lit_set, false);
            encode_affine_island_summaries(s, prime_lit_set, true);
            return;
        }

        std::unordered_set<int> xor_boundary;
        for(const GateInstance &instance : xor_gates){
            xor_boundary.insert(abs(instance.gate.o));
            xor_boundary.insert(abs(instance.gate.i1));
            xor_boundary.insert(abs(instance.gate.i2));
        }
        for(const AffineIslandSummary &summary : affine_island_summaries){
            if(lit_set.find(summary.root) != lit_set.end()){
                xor_boundary.insert(summary.root);
                xor_boundary.insert(summary.support.begin(), summary.support.end());
            }
            if(prime_lit_set.find(summary.root) != prime_lit_set.end()){
                xor_boundary.insert(prime_var(summary.root));
                for(int variable : summary.support)
                    xor_boundary.insert(prime_var(variable));
            }
        }

        std::unordered_set<int> eliminable;
        for(int output : cnf_outputs){
            if(consumers[output] == 1
               && boundary_roots.find(output) == boundary_roots.end()
               && xor_boundary.find(output) == xor_boundary.end())
                eliminable.insert(output);
        }
        cmsat_boundary_bve_candidates += eliminable.size();

        const int maximum_variable = *std::max_element(touched.begin(), touched.end());
        simplifier.var_enlarge_to(maximum_variable);
        // Primed variables use a disjoint high range. Freeze numbering gaps so
        // MiniSat does not report unrelated free variables as BVE work.
        for(int variable = 1; variable <= maximum_variable; ++variable)
            if(eliminable.find(variable) == eliminable.end())
                simplifier.set_frozen(variable);
        for(const GateInstance &instance : cnf_gates)
            encode_gate(&simplifier, instance.gate, instance.type);

        cmsat_boundary_bve_raw_clauses += simplifier.num_clauses();
        simplifier.simplify();
        cached_cnf = simplifier.simplified_cnf;
        if(cached_cnf.empty())
            cached_cnf = {1, -1, 0};
        const CNFSimplificationStats stats = simplifier.simplification_stats();
        cmsat_boundary_bve_eliminated += stats.eliminated_vars;
        for(int literal : cached_cnf)
            if(literal == 0)
                ++cmsat_boundary_bve_simplified_clauses;
        ++cmsat_boundary_bve_runs;
    }

    for(int literal : cached_cnf)
        s->add(literal);
    encode_affine_island_summaries(s, lit_set, false);
    encode_affine_island_summaries(s, prime_lit_set, true);
}

int PDR::freeze_structural_variables(CNFSimplifier *s, const set<int> &lit_set,
                                     const set<int> &prime_lit_set){
    if(minisat_freeze_policy == "none")
        return 0;

    vector<And> gates;
    gates.reserve(ands.size() + xors.size() + ors.size());
    gates.insert(gates.end(), ands.begin(), ands.end());
    gates.insert(gates.end(), xors.begin(), xors.end());
    gates.insert(gates.end(), ors.begin(), ors.end());

    std::unordered_map<int, And> gate_by_output;
    std::unordered_map<int, int> fanout;
    std::unordered_set<int> xor_outputs;
    for(const And &gate : gates){
        gate_by_output.emplace(gate.o, gate);
        ++fanout[abs(gate.i1)];
        ++fanout[abs(gate.i2)];
    }
    for(const And &gate : xors)
        xor_outputs.insert(gate.o);
    for(int literal : nexts)
        ++fanout[abs(literal)];
    ++fanout[abs(bad)];
    for(int literal : constraints)
        ++fanout[abs(literal)];

    auto collect_cone = [&](const vector<int> &roots){
        std::unordered_set<int> cone;
        vector<int> pending;
        pending.reserve(roots.size());
        for(int literal : roots)
            pending.push_back(abs(literal));
        while(!pending.empty()){
            int variable = pending.back();
            pending.pop_back();
            if(!cone.insert(variable).second)
                continue;
            auto found = gate_by_output.find(variable);
            if(found == gate_by_output.end())
                continue;
            pending.push_back(abs(found->second.i1));
            pending.push_back(abs(found->second.i2));
        }
        return cone;
    };

    vector<int> bad_roots(1, bad);
    bad_roots.insert(bad_roots.end(), constraints.begin(), constraints.end());
    vector<int> next_roots = nexts;
    next_roots.insert(next_roots.end(), constraints.begin(), constraints.end());
    const auto bad_cone = collect_cone(bad_roots);
    const auto next_cone = collect_cone(next_roots);

    auto selected = [&](int variable){
        const bool in_bad = bad_cone.find(variable) != bad_cone.end();
        const bool in_next = next_cone.find(variable) != next_cone.end();
        const bool high_fanout = fanout[variable] >= minisat_freeze_fanout;
        if(minisat_freeze_policy == "all")
            return true;
        if(minisat_freeze_policy == "high-fanout")
            return high_fanout;
        if(minisat_freeze_policy == "shared")
            return in_bad && in_next;
        if(minisat_freeze_policy == "bad")
            return in_bad;
        if(minisat_freeze_policy == "next")
            return in_next;
        if(minisat_freeze_policy == "xor")
            return xor_outputs.find(variable) != xor_outputs.end();
        if(minisat_freeze_policy == "hybrid")
            return high_fanout || (in_bad && in_next);
        return false;
    };

    int frozen = 0;
    for(const And &gate : gates){
        if(!selected(gate.o))
            continue;
        if(lit_set.find(gate.o) != lit_set.end()){
            s->set_frozen(gate.o);
            ++frozen;
        }
        if(prime_lit_set.find(gate.o) != prime_lit_set.end()){
            s->set_frozen(prime_var(gate.o));
            ++frozen;
        }
    }
    return frozen;
}

void PDR::simplify_aiger(){
    //TODO: rewriting aiger
}

// translate the aiger language to internal states
void PDR::translate_to_dimacs(){
    // load inputs prime
    for(int i=0; i<num_inputs; ++i){
        variables.push_back(
            Variable(primed_first_dimacs + i, 'i', i, true));
    }

    // load latches prime
    for(int i=0; i<num_latches; ++i){
        variables.push_back(
            Variable(primed_first_dimacs + num_inputs + i, 'l', i, true));
    }

    // load bad prime
    bad_prime = prime_lit(bad);

    // load constraint prime
    for(int i=0; i<constraints.size(); ++i){
        int pl = prime_lit(constraints[i]);
        constraints_prime.push_back(pl);
    }
    if (aig_veb){
        for(int i=1; i<=num_latches; ++i){
            Aiger_latch & al = Aiger_latches[i-1];
            cout << 1 + num_inputs + i << " " << nexts[i-1] << " " << al.default_val << endl;
        }        
        cout << "bad: " << bad << endl;
        cout << "primed bad: " << bad_prime << endl;
        cout << "constraints: \n";
        for(int i=0; i<num_constraints; ++i) cout << constraints[i] << " ";
        cout << "\nprimed constraints: \n";
        for(int i=0; i<num_constraints; ++i) cout << constraints_prime[i] << " ";
        cout << endl;
        for(int i=0; i<ands.size(); ++i){
            cout<<ands[i].o<<" ";
            cout<<ands[i].i1<<" ";
            cout<<ands[i].i2;
            cout<<endl;
        }
    }

    if(aig_veb > 2)
        show_variables();
}

void PDR::show_uaiger(){ //suppose all latch init to 0, and the bad property is denoted by the output
    int depth = 130;
    string filename = "unfold" + to_string(depth) + ".aag";
    std::ofstream file(filename);
    
    file << "aag " << (num_inputs*depth + num_latches*depth + num_ands*depth) << " " << num_inputs*depth << " " << 0 << " 1 " << num_ands*depth+num_latches*depth;
    // if(constraints.size()>0){
    //     file << " " << constraints.size();
    // }
    file << std::endl;
    // 1-d step bmc input
    for(int i = 1; i <= num_inputs * depth; ++i) {
        file << 2 * i << std::endl;
    }
    file << dimacs_to_aiger(bad) + 2*num_inputs*(depth-1) + 2*(num_latches+num_ands)*(depth-1) << std::endl;
    // 1 step latch
    int falselit = num_inputs * depth + 1;
    for(int i = 1; i <= num_latches; ++i) {
        file << 2 * (num_inputs * depth + i) << " 2 3" << endl;
    }
    // 1 step and
    for(int i = 0; i < ands.size(); ++i) {
        int o = dimacs_to_aiger(ands[i].o), i1 = dimacs_to_aiger(ands[i].i1), i2 = dimacs_to_aiger(ands[i].i2);
        file << o + 2*num_inputs*(depth-1) << " ";
        file << i1 + (i1>=2*(num_inputs + 1) ? 2*num_inputs*(depth-1) : 0) << " ";
        file << i2 + (i2>=2*(num_inputs + 1) ? 2*num_inputs*(depth-1) : 0) << std::endl;
    }
    // 2-d step
    for(int d=2; d<=depth; d++){
        // 2-d step latch
        for(int i = 1; i <= num_latches; ++i){
            int next = dimacs_to_aiger(nexts[i-1]);
            if(next >= 2*(num_inputs + 1)) //pre: latch or and
                next += 2*num_inputs*(depth-1) + 2*(num_latches+num_ands)*(d-2);
            else if(next > 1)//pre: input
                next += 2*num_inputs*(d-1);
            else if(next >= 0)
                next = 2*falselit + next;
            file << 2 * (num_inputs * depth + (d-1)*(num_latches+num_ands) + i) << " " << next << " " << next << endl;
        }
        // 2-d step and
        for(int i = 0; i < ands.size(); ++i){
            int o = dimacs_to_aiger(ands[i].o), i1 = dimacs_to_aiger(ands[i].i1), i2 = dimacs_to_aiger(ands[i].i2);
            file << o + 2*num_inputs*(depth-1) + 2*(num_latches+num_ands)*(d-1) << " ";
            file << i1 + (i1>=2*(num_inputs + 1) ? 2*num_inputs*(depth-1) + 2*(num_latches+num_ands)*(d-1) : 2*(num_inputs)*(d-1)) << " ";
            file << i2 + (i2>=2*(num_inputs + 1) ? 2*num_inputs*(depth-1) + 2*(num_latches+num_ands)*(d-1) : 2*(num_inputs)*(d-1)) << endl;
        }
    }
    file.close(); 
    std::string command = "./aigtoaig unfold" + to_string(depth) + ".aag unfold" + to_string(depth) + ".aig" ;
    int result = system(command.c_str());
    // command = "../project/circuitsat/build/csat --instance=./unfold" + to_string(depth) + ".aig" ;
    // result = system(command.c_str());
}

void PDR::initialize_heuristic(){
    heuristic_lit_cmp = new heuristic_Lit_CMP();
    heuristic_lit_cmp->counts.clear();
    (heuristic_lit_cmp->counts).resize(num_inputs+num_latches+num_inputs+2);
    //correspond to unprimed_first_dimacs + 0 to unprimed_first_dimacs + num_inputs - 1
    for(int i = 2; i <= num_inputs+1; i+=10){
        heuristic_lit_cmp->counts[i] = 0.5;
    }
    //correspond to unprimed_first_dimacs + num_inputs to unprimed_first_dimacs + + num_inputs + num_latches - 1
    for(int i = num_inputs+2; i <= num_inputs+num_latches+1; i+=10){
        heuristic_lit_cmp->counts[i] = 0.5;
    }
    //correspond to primed_first_dimacs + 0 to primed_first_dimacs + num_inputs - 1
    // for(int i = num_inputs+num_latches+2; i <= num_inputs+num_latches+num_inputs+1; i+=10){
    //     heuristic_lit_cmp->counts[i] = 0.5;
    // }
}

void PDR::restart_heuristic(){
    for(int i = num_inputs+2; i <= num_inputs+num_latches+1; i++){
        if(heuristic_lit_cmp->counts[i] > 0.5)
        heuristic_lit_cmp->counts[i] = 1.0/heuristic_lit_cmp->counts[i];
    }    
}

void PDR::updateLitOrder(Cube &cube, int level){
    //decay
    for(int i = 0; i < num_inputs+num_latches+num_inputs+2; i++){
        heuristic_lit_cmp->counts[i] *= 0.99;
    }
    //update heuristic score of literals remove abs
    for(int index: cube){
        if(use_plusone_count)
            heuristic_lit_cmp->counts[abs(index)] += 1;
        else
            heuristic_lit_cmp->counts[abs(index)] += 10.0/cube.size();
    }
    //check
    if(output_stats_for_heuristic){
        for(int i=0; i<heuristic_lit_cmp->counts.size(); i++){
            cout << heuristic_lit_cmp->counts[i] << " ";
        }
        cout << endl;
    }
    // nCube++;
    // nCubelen += cube.size();
}

void PDR::initialize(){
    satelite = nullptr;
    simplify_aiger();
    translate_to_dimacs();
    initialize_distance_metadata();
    initialize_heuristic();
    //show_uaiger();

    nQuery = nInductive = nCTI = nCTG = nmic = nCoreReduced = nAbortJoin = nAbortMic = 0;
    nBlock = nGeneralize = nExtract = nPre = 0;
    nLemmaAdded = nLemmaLiterals = 0;
    nBlockLemmaAdded = nBlockLemmaLiterals = 0;
    nPushLemmaAdded = nPushLemmaLiterals = 0;
    nFrameCore = nFrameCoreInputLiterals = nFrameCoreLiterals = 0;
    nLiftCore = nLiftCoreInputLiterals = nLiftCoreLiterals = 0;
    nReverseLiftAttempt = nReverseLiftSuccess = nReverseLiftFallback = nReverseLiftRestart = 0;
    tBlock = tInductive = tGeneralize = tCTG = tPropagate = tExtract = tPre = 0.0;
    tTranslationBuild = tTranslationSimplify = tTranslationInject = 0.0;
    tLiftBuild = tLiftSimplify = tLiftInject = 0.0;
    tBmc0Solve = tFirstPreSolve = tFirstLiftSolve = 0.0;
    translationRawVars = translationRawClauses = 0;
    translationSimplifiedVars = translationSimplifiedClauses = 0;
    translationSimplifiedLiterals = 0;
    liftRawVars = liftRawClauses = 0;
    liftSimplifiedVars = liftSimplifiedClauses = 0;
    liftSimplifiedLiterals = 0;
    //cout<<"c PDR constructed from aiger file [Finished] \n";
}

void PDR::new_frame(){
    int last = frames.size();
    maybe_disable_cmsat_gauss(last);
    frames.push_back(Frame());
    configure_solver(frames[last].solver, string("frame-") + std::to_string(last));
    encode_translation(frames[last].solver);
    // Goal of frame-k is to find a pre-condition or prove clause c inductive to k-1.
    for(int l : constraints_prime){
        frames[last].solver->add(l);
        frames[last].solver->add(0);
    }
    if(last > 0){
        for(const Cube &cube : inductive_cubes){
            for(int literal : cube)
                frames[last].solver->add(-literal);
            frames[last].solver->add(0);
        }
    }
}

int add_ct = 0;
void PDR::add_cube(Cube &cube, int k, bool to_all, bool ispropagate, int prtimes){
    if(!ispropagate)
        earliest_strengthened_frame =min(earliest_strengthened_frame,k);
    sort(cube.begin(), cube.end(), Lit_CMP());
    pair<set<Cube, Cube_CMP>::iterator, bool> rv = frames[k].cubes.insert(cube);
    if(!rv.second) return;
    ++nLemmaAdded;
    nLemmaLiterals += cube.size();
    if(ispropagate){
        ++nPushLemmaAdded;
        nPushLemmaLiterals += cube.size();
    }else{
        ++nBlockLemmaAdded;
        nBlockLemmaLiterals += cube.size();
    }
    semantic_event("lemma", 0, "pdr", ispropagate ? "propagate" : "block",
                   k, prtimes, &cube, static_cast<int>(cube.size()), 0);
    for(int literal : cube){
        const int index = latch_index_from_literal(literal);
        if(index < 0)
            continue;
        ++latch_lemma_occurrences[index];
        if(ispropagate){
            ++latch_push_occurrences[index];
            latch_push_distance_sum[index] += static_cast<std::uint64_t>(
                std::max(0, prtimes));
        }
        if(decision_trace_lemmas)
            decision_event(ispropagate ? "push_lemma" : "block_lemma",
                           k, prtimes, literal, cube.size(), cube.size(),
                           1, 0.0, 0, 0);
    }

    if(output_stats_for_addcube and !ispropagate) {
        cout<<"add Cube: (sz"<<cube.size()<<") to "<<k<<" : ";
        show_litvec(cube); 
    }
    if(to_all){
        for(int i=1; i< k; ++i){
            for(int l : cube)
                frames[i].solver->add(-l);
            frames[i].solver->add(0);
        }
    }
    for(int l : cube)
        frames[k].solver->add(-l);
    frames[k].solver->add(0);

    if(cfg_use_heuristic and !ispropagate)
        updateLitOrder(cube, k);

    if(cfg_certify_early
       && static_cast<int>(cube.size()) <= cfg_certify_early_max_cube
       && prtimes >= cfg_certify_early_min_push){
        ++early_certify_attempted;
        if(maybe_certify_inductive_cube(cube))
            ++early_certify_succeeded;
    }

}

bool PDR::cube_to_canonical(const Cube &cube, Cube &canonical) const{
    canonical.clear();
    canonical.reserve(cube.size());
    const int first_latch = unprimed_first_dimacs + num_inputs;
    for(int literal : cube){
        int index = abs(literal) - first_latch;
        if(index < 0 || index >= num_latches)
            return false;
        int mapped = index + 1;
        canonical.push_back(literal < 0 ? -mapped : mapped);
    }
    sort(canonical.begin(), canonical.end(), Lit_CMP());
    return true;
}

bool PDR::cube_from_canonical(const Cube &canonical, Cube &cube) const{
    cube.clear();
    cube.reserve(canonical.size());
    const int first_latch = unprimed_first_dimacs + num_inputs;
    for(int literal : canonical){
        int index = abs(literal) - 1;
        if(index < 0 || index >= num_latches)
            return false;
        int mapped = first_latch + index;
        cube.push_back(literal < 0 ? -mapped : mapped);
    }
    sort(cube.begin(), cube.end(), Lit_CMP());
    return true;
}

void PDR::publish_inductive_cube(const Cube &cube){
    if(lemma_exchange == nullptr)
        return;
    Cube canonical;
    if(!cube_to_canonical(cube, canonical)){
        ++shared_rejected;
        return;
    }
    if(lemma_exchange->publish(is_reverse(), thread_index, canonical))
        ++shared_published;
}

void PDR::ensure_inductive_solver(){
    if(inductive_solver != nullptr)
        return;
    inductive_solver = new_pdr_solver();
    configure_solver(inductive_solver, "inductive");
    encode_translation(inductive_solver);
    for(int literal : constraints_prime){
        inductive_solver->add(literal);
        inductive_solver->add(0);
    }
    if(cfg_certify_early){
        for(const Cube &cube : inductive_cubes){
            for(int literal : cube)
                inductive_solver->add(-literal);
            inductive_solver->add(0);
        }
    }
}

bool PDR::install_inductive_cube(Cube cube, bool publish){
    sort(cube.begin(), cube.end(), Lit_CMP());
    if(!inductive_cubes.insert(cube).second)
        return false;

    // In early-certification mode, certified cubes form a growing inductive
    // conjunction.  Legacy mode retains independent self-induction checks.
    if(cfg_certify_early && inductive_solver != nullptr){
        for(int literal : cube)
            inductive_solver->add(-literal);
        inductive_solver->add(0);
    }
    if(cfg_certify_early)
        inductive_attempted_cubes.clear();

    // Each certified clause belongs to a sound inductive conjunction that is
    // independent of frame-local lemmas, so it can strengthen every frame.
    for(size_t frame = 1; frame < frames.size(); ++frame){
        for(int literal : cube)
            frames[frame].solver->add(-literal);
        frames[frame].solver->add(0);
    }
    if(publish)
        publish_inductive_cube(cube);
    return true;
}

bool PDR::certify_inductive_cube(Cube cube){
    sort(cube.begin(), cube.end(), Lit_CMP());
    if(inductive_cubes.find(cube) != inductive_cubes.end())
        return true;
    if(!inductive_attempted_cubes.insert(cube).second)
        return false;
    if(is_source(cube)){
        ++shared_not_inductive;
        return false;
    }

    ensure_inductive_solver();
    // Early mode may also contain previously certified invariant clauses;
    // legacy mode retains the original independent self-induction test.
    if(!is_inductive(inductive_solver, cube, false)){
        ++shared_not_inductive;
        return false;
    }
    ++shared_certified;
    install_inductive_cube(std::move(cube), true);
    return true;
}

bool PDR::maybe_certify_inductive_cube(Cube cube){
    sort(cube.begin(), cube.end(), Lit_CMP());
    if(inductive_cubes.find(cube) != inductive_cubes.end())
        return true;
    if((lemma_exchange == nullptr && !cfg_certify_early)
       || share_inductive_budget_remaining <= 0 ||
       inductive_attempted_cubes.find(cube) != inductive_attempted_cubes.end())
        return false;
    --share_inductive_budget_remaining;
    return certify_inductive_cube(std::move(cube));
}

void PDR::import_shared_lemmas(){
    if(lemma_exchange == nullptr || frames.empty())
        return;

    vector<SharedLemma> received = lemma_exchange->consume(
        is_reverse(), thread_index, lemma_cursor);
    for(const SharedLemma &shared : received){
        Cube cube;
        if(!cube_from_canonical(shared.canonical_cube, cube)){
            ++shared_rejected;
            continue;
        }
        ++shared_received;
        if(install_inductive_cube(std::move(cube), false))
            ++shared_imported;
    }
}

bool PDR::import_external_invariant(){
    if(invariant_import_path.empty())
        return true;

    std::ifstream input(invariant_import_path.c_str());
    if(!input){
        cerr << "Warning: cannot open MC_PDR_INVARIANT_IMPORT='"
             << invariant_import_path << "'." << endl;
        ++invariant_import_rejected;
        return false;
    }

    string magic;
    int file_latches = -1;
    input >> magic >> file_latches;
    if(magic != "mc-pdr-invariant-v1" || file_latches != num_latches){
        cerr << "Warning: incompatible invariant file '" << invariant_import_path
             << "' (latches=" << file_latches << ", expected="
             << num_latches << ")." << endl;
        ++invariant_import_rejected;
        return false;
    }

    string line;
    std::getline(input, line);
    set<Cube, Cube_CMP> canonical_cubes;
    while(std::getline(input, line)){
        if(line.empty() || line[0] == 'c' || line[0] == '#')
            continue;
        std::istringstream fields(line);
        Cube cube;
        int literal = 0;
        bool terminated = false;
        while(fields >> literal){
            if(literal == 0){
                terminated = true;
                break;
            }
            if(abs(literal) > num_latches){
                cerr << "Warning: out-of-range latch literal in invariant file '"
                     << invariant_import_path << "'." << endl;
                ++invariant_import_rejected;
                return false;
            }
            cube.push_back(literal);
        }
        if(!terminated || cube.empty()){
            cerr << "Warning: malformed invariant clause in '"
                 << invariant_import_path << "'." << endl;
            ++invariant_import_rejected;
            return false;
        }
        sort(cube.begin(), cube.end(), Lit_CMP());
        canonical_cubes.insert(std::move(cube));
    }
    invariant_import_read = canonical_cubes.size();
    if(canonical_cubes.empty()){
        ++invariant_import_rejected;
        return false;
    }

    const bool prune_invalid = env_bool("MC_PDR_INVARIANT_PRUNE", false);
    vector<Cube> cubes;
    cubes.reserve(canonical_cubes.size());
    for(const Cube &canonical : canonical_cubes){
        Cube cube;
        if(!cube_from_canonical(canonical, cube) || is_source(cube)){
            if(prune_invalid){
                ++invariant_import_pruned;
                continue;
            }
            ++invariant_import_rejected;
            cerr << "c PDR_INVARIANT_IMPORT status=reject reason=initial-or-map"
                 << " path=" << invariant_import_path << endl;
            return false;
        }
        cubes.push_back(std::move(cube));
    }

    vector<bool> active(cubes.size(), true);
    if(!invariant_same_transition){
        bool changed = true;
        while(changed){
        changed = false;
        std::unique_ptr<SATSolver> validator(new_pdr_solver());
        configure_solver(validator.get(), "external-invariant");
        encode_translation(validator.get());
        for(int literal : constraints_prime){
            validator->add(literal);
            validator->add(0);
        }
        for(size_t index = 0; index < cubes.size(); ++index){
            if(!active[index])
                continue;
            for(int literal : cubes[index])
                validator->add(-literal);
            validator->add(0);
        }
        for(size_t index = 0; index < cubes.size(); ++index){
            if(!active[index])
                continue;
            if(is_inductive(validator.get(), cubes[index], false, true,
                            "external-invariant", -1,
                            static_cast<int>(index)))
                continue;
            if(!prune_invalid){
                ++invariant_import_rejected;
                cerr << "c PDR_INVARIANT_IMPORT status=reject"
                     << " reason=not-inductive clause=" << index
                     << " path=" << invariant_import_path << endl;
                return false;
            }
            active[index] = false;
            ++invariant_import_pruned;
            changed = true;
        }
        }
    }else{
        cerr << "c PDR_INVARIANT_IMPORT validation=same-transition"
             << " clauses=" << cubes.size()
             << " path=" << invariant_import_path << endl;
    }

    for(size_t index = 0; index < cubes.size(); ++index){
        if(active[index]
           && install_inductive_cube(std::move(cubes[index]), false))
            ++invariant_import_installed;
    }
    if(invariant_import_installed == 0){
        ++invariant_import_rejected;
        cerr << "c PDR_INVARIANT_IMPORT status=reject reason=empty-after-prune"
             << " path=" << invariant_import_path << endl;
        return false;
    }

    if(!is_reverse()){
        std::unique_ptr<SATSolver> target_validator(new_pdr_solver());
        configure_solver(target_validator.get(), "external-invariant-target");
        target_validator->add(-1);
        target_validator->add(0);
        set<int> target_cone;
        target_cone.insert(abs(bad));
        for(int literal : constraints){
            target_validator->add(literal);
            target_validator->add(0);
            target_cone.insert(abs(literal));
        }
        encode_gate_cone(target_validator.get(), target_cone);
        target_validator->add(bad);
        target_validator->add(0);
        for(const Cube &cube : inductive_cubes){
            for(int literal : cube)
                target_validator->add(-literal);
            target_validator->add(0);
        }
        invariant_proves_target = target_validator->solve() == UNSAT;
    }
    cerr << "c PDR_INVARIANT_IMPORT status=accepted clauses="
         << invariant_import_installed << " pruned="
         << invariant_import_pruned << " proves_target="
         << (invariant_proves_target ? 1 : 0) << " path="
         << invariant_import_path << endl;
    return true;
}

void PDR::export_fixed_point(int empty_frame){
    if(invariant_export_path.empty() || is_reverse())
        return;

    string path = invariant_export_path;
    const string marker = "%t";
    size_t position = 0;
    while((position = path.find(marker, position)) != string::npos){
        path.replace(position, marker.size(), to_string(thread_index));
        position += 1;
    }

    set<Cube, Cube_CMP> canonical_cubes;
    auto collect = [&](const Cube &cube){
        Cube canonical;
        if(cube_to_canonical(cube, canonical) && !canonical.empty())
            canonical_cubes.insert(std::move(canonical));
    };
    for(const Cube &cube : inductive_cubes)
        collect(cube);
    for(int frame = empty_frame + 1;
        frame < static_cast<int>(frames.size()); ++frame){
        for(const Cube &cube : frames[frame].cubes)
            collect(cube);
    }

    std::ofstream output(path.c_str(), std::ios::out | std::ios::trunc);
    if(!output){
        cerr << "Warning: cannot open MC_PDR_INVARIANT_EXPORT='"
             << path << "'." << endl;
        return;
    }
    output << "mc-pdr-invariant-v1 " << num_latches << '\n';
    output << "c blocked cubes; each line is a canonical latch cube\n";
    for(const Cube &cube : canonical_cubes){
        for(int literal : cube)
            output << literal << ' ';
        output << "0\n";
    }
    output.flush();
    invariant_exported = canonical_cubes.size();
    cerr << "c PDR_INVARIANT_EXPORT clauses=" << invariant_exported
         << " path=" << path << endl;
}

void PDR::export_inductive_snapshot(){
    if(invariant_snapshot_path.empty() || inductive_cubes.empty()
       || is_reverse())
        return;

    string path = invariant_snapshot_path;
    const string marker = "%t";
    size_t position = 0;
    while((position = path.find(marker, position)) != string::npos){
        path.replace(position, marker.size(), to_string(thread_index));
        position += 1;
    }

    set<Cube, Cube_CMP> canonical_cubes;
    for(const Cube &cube : inductive_cubes){
        Cube canonical;
        if(cube_to_canonical(cube, canonical) && !canonical.empty())
            canonical_cubes.insert(std::move(canonical));
    }
    if(canonical_cubes.empty())
        return;

    std::ofstream output(path.c_str(), std::ios::out | std::ios::trunc);
    if(!output){
        cerr << "Warning: cannot open MC_PDR_INVARIANT_SNAPSHOT='"
             << path << "'." << endl;
        return;
    }
    output << "mc-pdr-invariant-v1 " << num_latches << '\n';
    output << "c certified permanent cubes; incomplete proof snapshot\n";
    for(const Cube &cube : canonical_cubes){
        for(int literal : cube)
            output << literal << ' ';
        output << "0\n";
    }
    output.flush();
    invariant_snapshot_exported = canonical_cubes.size();
    cerr << "c PDR_INVARIANT_SNAPSHOT clauses="
         << invariant_snapshot_exported << " path=" << path << endl;
}

bool PDR::is_source(const vector<int> &latches){
    static const vector<int> no_inputs;
    return is_source(latches, no_inputs);
}

bool PDR::is_source(const vector<int> &latches, const vector<int> &inputs){
    if(init == nullptr){
        init = new_pdr_solver();
        configure_solver(init, "source");
        encode_source_condition(init);
    }
    for(int l : latches)
        init->assume(l);
    for(int i : inputs)
        init->assume(i);
    SATSearchStats before;
    if(semantic_trace)
        before = init->search_stats();
    maybe_print_progress_stats("source");
    int res = init->solve();
    if(semantic_trace){
        SATSearchStats after = init->search_stats();
        vector<int> condition = latches;
        condition.insert(condition.end(), inputs.begin(), inputs.end());
        semantic_query(init, "source", "source", -1, -1,
                       condition, res, before, after);
    }
    if(res == UNKNOWN)
        return false;
    return (res == SAT);
}

// check ~latches inductive by Fi /\ -s /\ T /\ s'
// Fi /\ -latches /\ [constraints /\ -bad /\ T] /\ constraints' /\ latches'
int core_ct = 0;
bool PDR::is_inductive(SATSolver *solver, const Cube &latches, bool gen_core,
                       bool reverse_assumption, const char *query_kind,
                       int query_frame, int query_depth){
    ScopedTimer timer(&tInductive);
    solver->clear_act();
    vector<int> assumptions;
    int act = solver->max_var() + 1;
    solver->add(-act);
    for(int i : latches)
        solver->add(-i);
    solver->add(0);

    if(cfg_use_heuristic){
        for(int i : latches)
            assumptions.push_back(i);
        stable_sort(assumptions.begin(), assumptions.end(), *heuristic_lit_cmp);
        if(reverse_assumption)
            reverse(assumptions.begin(), assumptions.end());
        for(int i=0; i<assumptions.size(); i++){
            assumptions[i] = prime_lit(assumptions[i]);
        }
    }
    else{
        for(int i : latches)
            assumptions.push_back(prime_lit(i));
        stable_sort(assumptions.begin(), assumptions.end(), Lit_CMP());
    }

    solver->assume(act);
    for(int i: assumptions)
        solver->assume(i);

    vector<int> predecessor_phases;
    const string query_name = query_kind == nullptr ? "" : query_kind;
    if(query_name == "block" || query_name == "mic"){
        ++predecessor_phase_queries;
        predecessor_phases = predecessor_phase_literals(
            &latches, predecessor_phase_queries);
        for(int literal : predecessor_phases)
            solver->set_phase(literal);
    }

    SATSearchStats semantic_before;
    if(semantic_trace)
        semantic_before = solver->search_stats();
    maybe_print_progress_stats(query_kind);
    int status = solver->solve();
    for(int literal : predecessor_phases)
        solver->clear_phase(literal);
    std::uint64_t semantic_query_id = 0;
    if(semantic_trace){
        SATSearchStats semantic_after = solver->search_stats();
        semantic_query_id = semantic_query(
            solver, solver == inductive_solver ? "inductive" : "frame",
            query_kind, query_frame, query_depth, assumptions,
            status, semantic_before, semantic_after);
    }
    ++nQuery;
    ++nInductive;
    if(status == UNKNOWN){
        solver->set_clear_act();
        return false;
    }
    bool res = (status == UNSAT);

    if(res & gen_core){
        core.clear();
        for(int i : latches){
            if(solver->failed(prime_lit(i)))
                core.push_back(i);
        }
        if(is_source(core)){
            core = latches;
        }
        ++nFrameCore;
        nFrameCoreInputLiterals += latches.size();
        nFrameCoreLiterals += core.size();
        // DEBUG: per-query-kind core sizes
        static std::uint64_t dbg_core_cnt[8] = {0,0,0,0,0,0,0,0};
        static std::uint64_t dbg_core_lits[8] = {0,0,0,0,0,0,0,0};
        if(query_kind != nullptr){
            int kidx = 7;
            if(std::string(query_kind) == "propagate") kidx = 0;
            else if(std::string(query_kind) == "block") kidx = 1;
            else if(std::string(query_kind) == "mic") kidx = 2;
            else if(std::string(query_kind) == "ctg") kidx = 3;
            else if(std::string(query_kind) == "block-push") kidx = 4;
            else if(std::string(query_kind) == "ctg-push") kidx = 5;
            else if(std::string(query_kind) == "lift") kidx = 6;
            ++dbg_core_cnt[kidx];
            dbg_core_lits[kidx] += core.size();
        }
        semantic_event("core", semantic_query_id, "frame", query_kind,
                       query_frame, query_depth, &core,
                       static_cast<int>(core.size()), status);
    }
    solver->set_clear_act();
    return res;
}

void PDR::encode_init_condition(SATSolver *s){
    s->add(-1); s->add(0);
    for(int l : init_state){
        s->add(l); s->add(0);
    }
    for(const pair<int, int> &equality : init_equalities){
        int latch = equality.first;
        int reset = equality.second;
        s->add(-latch); s->add(reset); s->add(0);
        s->add(latch); s->add(-reset); s->add(0);
    }
    if(constraints.size() >= 0){
        for(int l : constraints){
            s->add(l); s->add(0);}

        set<int> lit_set;
        for(int l : constraints)
            lit_set.insert(abs(l));
        for(const pair<int, int> &equality : init_equalities)
            lit_set.insert(abs(equality.second));

        encode_gate_cone(s, lit_set);
    }
    if(aig_veb > 2)
        cout<<"c add_cls finish load init"<<endl;
}

void PDR::encode_bad_state(SATSolver *s){
    set<int> lit_set;
    lit_set.insert(abs(bad));
    encode_gate_cone(s, lit_set);
    if(aig_veb > 2)
        cout<<"c add_cls finish load bad"<<endl;
}

void PDR::encode_source_condition(SATSolver *s){
    if(!is_reverse()){
        encode_init_condition(s);
        return;
    }

    s->add(-1); s->add(0);
    s->add(bad); s->add(0);
    for(int l : constraints){
        s->add(l); s->add(0);
    }

    set<int> lit_set;
    lit_set.insert(abs(bad));
    for(int l : constraints)
        lit_set.insert(abs(l));
    encode_gate_cone(s, lit_set);
}

void PDR::encode_target_condition(SATSolver *s, bool primed){
    if(!is_reverse()){
        s->add(primed ? bad_prime : bad);
        s->add(0);
        return;
    }

    for(int l : init_state){
        s->add(primed ? prime_lit(l) : l);
        s->add(0);
    }
}

void PDR::encode_not_target_clause(SATSolver *s, bool primed){
    if(!is_reverse()){
        s->add(primed ? -bad_prime : -bad);
        s->add(0);
        return;
    }

    for(int l : init_state)
        s->add(primed ? prime_lit(-l) : -l);
    s->add(0);
}

void PDR::assume_target(SATSolver *s, bool primed){
    if(!is_reverse()){
        s->assume(primed ? bad_prime : bad);
        return;
    }

    for(int l : init_state)
        s->assume(primed ? prime_lit(l) : l);
}

// check ~latches inductive by Fi /\ -s /\ T /\ s'
// Fi /\ latches /\ [constraints /\ -bad /\ T] /\ constraints' /\ latches'
// lift a pre-state by Fi /\ pre /\ T /\ -s' (assert UNSAT)
// Fi /\ inputs /\ latches /\ [constraints /\ -bad /\ T] /\ inputs' /\ -(constraints' /\ latches')
// translation encoding: [constraints /\ -bad /\ T]
void PDR::encode_translation(SATSolver *s, bool cons){
    if(s->supports_native_xor()){
        set<int> prime_lit_set;
        set<int> lit_set;
        s->add(-1); s->add(0);
        if(!is_reverse()){
            prime_lit_set.insert(abs(bad));
            for(int literal : constraints)
                prime_lit_set.insert(abs(literal));
            lit_set.insert(prime_lit_set.begin(), prime_lit_set.end());
            s->add(-bad); s->add(0);
            if(cons){
                for(int literal : constraints){
                    if(literal == bad) satelite_unsat = true;
                    s->add(literal); s->add(0);
                }
            }
            for(int i=0; i<num_latches; ++i){
                const int latch = 1 + num_inputs + i + 1;
                const int primed_latch = prime_lit(latch);
                const int next = nexts[i];
                if(encode_affine_next_summary(s, i))
                    continue;
                lit_set.insert(abs(next));
                s->add(-primed_latch); s->add(next); s->add(0);
                s->add(-next); s->add(primed_latch); s->add(0);
            }
        }else{
            lit_set.insert(abs(bad));
            for(int literal : constraints){
                lit_set.insert(abs(literal));
                prime_lit_set.insert(abs(literal));
            }
            for(int next : nexts){
                lit_set.insert(abs(next));
                prime_lit_set.insert(abs(next));
            }
            encode_not_target_clause(s, false);
            if(cons)
                for(int literal : constraints){ s->add(literal); s->add(0); }
            for(int i=0; i<num_latches; ++i){
                const int latch = 1 + num_inputs + i + 1;
                const int reverse_next = prime_lit(nexts[i]);
                s->add(-latch); s->add(reverse_next); s->add(0);
                s->add(-reverse_next); s->add(latch); s->add(0);
            }
        }
        if(guarded_affine_enabled)
            for(int control : guarded_affine_controls)
                lit_set.insert(abs(control));
        if(cmsat_boundary_bve_enabled)
            encode_gate_cone_with_prime_boundary_bve(
                s, lit_set, prime_lit_set, cmsat_translation_bve_cnf);
        else
            encode_gate_cone_with_prime(s, lit_set, prime_lit_set);
        encode_affine_parity_invariants(s, true, true);
        if(satelite_unsat) { s->add(1); s->add(0); }
        return;
    }
    if(satelite == nullptr){
        auto build_start = std::chrono::steady_clock::now();
        if(cfg_phase_stats)
            cout << "c PDR_PHASE thread=" << thread_index
                 << " phase=translation_build event=start" << endl;
        satelite = cnf_preprocessor == "cadical"
            ? static_cast<CNFSimplifier *>(new cadicalSimp())
            : static_cast<CNFSimplifier *>(
                new minisatSimp(minisat_translation_elim_order,
                                minisat_translation_width_weight));
        satelite->var_enlarge_to(variables.size()-1);

        for(int i=1; i<= num_inputs+num_latches; ++i){
            satelite->set_frozen(1 + i);
            satelite->set_frozen(prime_var(1 + i));
        }
        satelite->set_frozen(abs(bad));
        satelite->set_frozen(abs(bad_prime));
        for(int i=0; i<constraints.size(); ++i){
            assert(prime_var(abs(constraints[i])) == abs(constraints_prime[i]));
            satelite->set_frozen(abs(constraints[i]));
            satelite->set_frozen(abs(constraints_prime[i]));
        }

        set<int> prime_lit_set;
        set<int> lit_set;

        satelite->add(-1); satelite->add(0);
        if(!is_reverse()){
            prime_lit_set.insert(abs(bad));
            for(int l : constraints)
                prime_lit_set.insert(abs(l));
            lit_set.insert(prime_lit_set.begin(), prime_lit_set.end());
            for(int l : nexts)
                lit_set.insert(abs(l));

            satelite->add(-bad); satelite->add(0);
            if(cons){
                for(int l : constraints){
                    if(l == bad) satelite_unsat = true;
                    satelite->add(l); satelite->add(0);
                }
            }
            for(int i=0; i<num_latches; ++i){
                int l = 1 + num_inputs + i + 1;
                int pl = prime_lit(l);
                int next = nexts[i];
                satelite->add(-pl); satelite->add(next); satelite->add(0);
                satelite->add(-next); satelite->add(pl); satelite->add(0);
            }
        }else{
            // Reverse state r is unprimed and its reverse successor r' is primed.
            // T^R(r,r') is the original relation T(r',r).
            lit_set.insert(abs(bad));
            for(int l : constraints){
                lit_set.insert(abs(l));
                prime_lit_set.insert(abs(l));
            }
            for(int next : nexts){
                lit_set.insert(abs(next));
                prime_lit_set.insert(abs(next));
            }

            encode_not_target_clause(satelite, false);
            if(cons){
                for(int l : constraints){
                    satelite->add(l); satelite->add(0);
                }
            }
            for(int i=0; i<num_latches; ++i){
                int l = 1 + num_inputs + i + 1;
                int reverse_next = prime_lit(nexts[i]);
                satelite->add(-l); satelite->add(reverse_next); satelite->add(0);
                satelite->add(-reverse_next); satelite->add(l); satelite->add(0);
            }
        }

        encode_gate_cone_with_prime(satelite, lit_set, prime_lit_set);
        translationFrozenGateVars = freeze_structural_variables(
            satelite, lit_set, prime_lit_set);
        translationRawVars = satelite->num_vars();
        translationRawClauses = satelite->num_clauses();
        tTranslationBuild += std::chrono::duration<double>(
            std::chrono::steady_clock::now() - build_start).count();
        if(cfg_phase_stats)
            cout << "c PDR_PHASE thread=" << thread_index
                 << " phase=translation_build event=done elapsed=" << tTranslationBuild
                 << " vars=" << translationRawVars
                 << " clauses=" << translationRawClauses << endl;
        auto simplify_start = std::chrono::steady_clock::now();
        if(cfg_phase_stats)
            cout << "c PDR_PHASE thread=" << thread_index
                 << " phase=translation_simplify event=start" << endl;
        satelite->simplify();
        tTranslationSimplify += std::chrono::duration<double>(
            std::chrono::steady_clock::now() - simplify_start).count();
        translationSimplifiedVars = satelite->num_vars();
        translationSimplifiedClauses = 0;
        translationSimplifiedLiterals = 0;
        for(int literal : satelite->simplified_cnf){
            if(literal == 0)
                ++translationSimplifiedClauses;
            else
                ++translationSimplifiedLiterals;
        }
        if(cfg_phase_stats)
            cout << "c PDR_PHASE thread=" << thread_index
                 << " phase=translation_simplify event=done elapsed=" << tTranslationSimplify
                 << " vars=" << translationSimplifiedVars
                 << " clauses=" << translationSimplifiedClauses
                 << " literals=" << translationSimplifiedLiterals << endl;
        // for(int l : satelite->simplified_cnf){
        //     cout << l << " ";
        //     if(l == 0){
        //         cout << endl;
        //     }
        // }
    }

    auto inject_start = std::chrono::steady_clock::now();
    apply_cadical_variable_order(s, satelite->simplified_cnf, "translation");
    for(int l : satelite->simplified_cnf){
         s->add(l);
    }
    encode_affine_hints_cnf(s);
    if(satelite_unsat) {s->add(1);s->add(0);}
    double inject_elapsed = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - inject_start).count();
    tTranslationInject += inject_elapsed;
    if(cfg_phase_stats)
        cout << "c PDR_PHASE thread=" << thread_index
             << " phase=translation_inject event=done elapsed=" << inject_elapsed
             << " total=" << tTranslationInject << endl;
    if(aig_veb > 2)
        cout<<"c add_cls finish load translation"<<endl;
}

void PDR::encode_lift(SATSolver *s){
    if(s->supports_native_xor()){
        set<int> prime_lit_set;
        set<int> lit_set;
        s->add(-1); s->add(0);
        if(!is_reverse()){
            prime_lit_set.insert(abs(bad));
            for(int literal : constraints)
                prime_lit_set.insert(abs(literal));
            lit_set.insert(prime_lit_set.begin(), prime_lit_set.end());
            s->add(-bad); s->add(0);
            for(int i=0; i<num_latches; ++i){
                const int latch = 1 + num_inputs + i + 1;
                const int primed_latch = prime_lit(latch);
                const int next = nexts[i];
                if(encode_affine_next_summary(s, i))
                    continue;
                lit_set.insert(abs(next));
                s->add(-primed_latch); s->add(next); s->add(0);
                s->add(-next); s->add(primed_latch); s->add(0);
            }
        }else{
            lit_set.insert(abs(bad));
            for(int literal : constraints){
                lit_set.insert(abs(literal));
                prime_lit_set.insert(abs(literal));
            }
            for(int next : nexts){
                lit_set.insert(abs(next));
                prime_lit_set.insert(abs(next));
            }
            encode_not_target_clause(s, false);
            for(int i=0; i<num_latches; ++i){
                const int latch = 1 + num_inputs + i + 1;
                const int reverse_next = prime_lit(nexts[i]);
                s->add(-latch); s->add(reverse_next); s->add(0);
                s->add(-reverse_next); s->add(latch); s->add(0);
            }
        }
        if(guarded_affine_enabled)
            for(int control : guarded_affine_controls)
                lit_set.insert(abs(control));
        if(cmsat_boundary_bve_enabled)
            encode_gate_cone_with_prime_boundary_bve(
                s, lit_set, prime_lit_set, cmsat_lift_bve_cnf);
        else
            encode_gate_cone_with_prime(s, lit_set, prime_lit_set);
        encode_affine_parity_invariants(s, true, true);
        if(split_ands){
            notInvConstraints = s->max_var() + 1;
            s->add(-notInvConstraints);
            for(int literal : constraints_prime) s->add(-literal);
            for(int literal : constraints) s->add(-literal);
            s->add(0);
        }
        return;
    }
    if(satelite2 == nullptr){
        auto build_start = std::chrono::steady_clock::now();
        if(cfg_phase_stats)
            cout << "c PDR_PHASE thread=" << thread_index
                 << " phase=lift_build event=start" << endl;
        satelite2 = cnf_preprocessor == "cadical"
            ? static_cast<CNFSimplifier *>(new cadicalSimp())
            : static_cast<CNFSimplifier *>(new minisatSimp(
                minisat_lift_elim_order, minisat_lift_width_weight));
        satelite2->var_enlarge_to(variables.size()-1);

        for(int i=1; i<= num_inputs+num_latches; ++i){
            satelite2->set_frozen(1 + i);
            satelite2->set_frozen(prime_var(1 + i));
        }
        satelite2->set_frozen(abs(bad));
        satelite2->set_frozen(abs(bad_prime));
        for(int i=0; i<constraints.size(); ++i){
            assert(prime_var(abs(constraints[i])) == abs(constraints_prime[i]));
            satelite2->set_frozen(abs(constraints[i]));
            satelite2->set_frozen(abs(constraints_prime[i]));
        }

        set<int> prime_lit_set;
        set<int> lit_set;
        satelite2->add(-1); satelite2->add(0);

        if(!is_reverse()){
            prime_lit_set.insert(abs(bad));
            for(int l : constraints)
                prime_lit_set.insert(abs(l));
            lit_set.insert(prime_lit_set.begin(), prime_lit_set.end());
            for(int l : nexts)
                lit_set.insert(abs(l));

            satelite2->add(-bad); satelite2->add(0);
            for(int i=0; i<num_latches; ++i){
                int l = 1 + num_inputs + i + 1;
                int pl = prime_lit(l);
                int next = nexts[i];
                satelite2->add(-pl); satelite2->add(next); satelite2->add(0);
                satelite2->add(-next); satelite2->add(pl); satelite2->add(0);
            }
        }else{
            lit_set.insert(abs(bad));
            for(int l : constraints){
                lit_set.insert(abs(l));
                prime_lit_set.insert(abs(l));
            }
            for(int next : nexts){
                lit_set.insert(abs(next));
                prime_lit_set.insert(abs(next));
            }

            encode_not_target_clause(satelite2, false);
            for(int i=0; i<num_latches; ++i){
                int l = 1 + num_inputs + i + 1;
                int reverse_next = prime_lit(nexts[i]);
                satelite2->add(-l); satelite2->add(reverse_next); satelite2->add(0);
                satelite2->add(-reverse_next); satelite2->add(l); satelite2->add(0);
            }
        }

        encode_gate_cone_with_prime(satelite2, lit_set, prime_lit_set);
        if(split_ands){
            notInvConstraints = satelite2->max_var() + 1;
            satelite2->set_frozen(notInvConstraints);
            satelite2->add(-notInvConstraints);
            for(int l : constraints_prime)
                satelite2->add(-l);
            for(int l : constraints)
                satelite2->add(-l);
            satelite2->add(0);
        }
        liftFrozenGateVars = freeze_structural_variables(
            satelite2, lit_set, prime_lit_set);
        liftRawVars = satelite2->num_vars();
        liftRawClauses = satelite2->num_clauses();
        tLiftBuild += std::chrono::duration<double>(
            std::chrono::steady_clock::now() - build_start).count();
        if(cfg_phase_stats)
            cout << "c PDR_PHASE thread=" << thread_index
                 << " phase=lift_build event=done elapsed=" << tLiftBuild
                 << " vars=" << liftRawVars
                 << " clauses=" << liftRawClauses << endl;
        auto simplify_start = std::chrono::steady_clock::now();
        if(cfg_phase_stats)
            cout << "c PDR_PHASE thread=" << thread_index
                 << " phase=lift_simplify event=start" << endl;
        satelite2->simplify();
        tLiftSimplify += std::chrono::duration<double>(
            std::chrono::steady_clock::now() - simplify_start).count();
        liftSimplifiedVars = satelite2->num_vars();
        liftSimplifiedClauses = 0;
        liftSimplifiedLiterals = 0;
        for(int literal : satelite2->simplified_cnf){
            if(literal == 0)
                ++liftSimplifiedClauses;
            else
                ++liftSimplifiedLiterals;
        }
        if(cfg_phase_stats)
            cout << "c PDR_PHASE thread=" << thread_index
                 << " phase=lift_simplify event=done elapsed=" << tLiftSimplify
                 << " vars=" << liftSimplifiedVars
                 << " clauses=" << liftSimplifiedClauses
                 << " literals=" << liftSimplifiedLiterals << endl;
    }

    auto inject_start = std::chrono::steady_clock::now();
    apply_cadical_variable_order(s, satelite2->simplified_cnf, "lift");
    for(int l : satelite2->simplified_cnf){
        s->add(l);
    }
    encode_affine_hints_cnf(s);
    double inject_elapsed = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - inject_start).count();
    tLiftInject += inject_elapsed;
    if(cfg_phase_stats)
        cout << "c PDR_PHASE thread=" << thread_index
             << " phase=lift_inject event=done elapsed=" << inject_elapsed
             << " total=" << tLiftInject << endl;
}

// Lifts the pre-state on a given frame
// If SAT?[Fk /\ -succ /\ T /\ succ'] return SAT and extract a pre-state pre \in [Fk /\ -succ]
// Then call SAT?[pre /\ T /\ -succ']
// pre must meet constraints.
void PDR::extract_state_from_sat(SATSolver *sat, State *s, State *succ, int findex){
    ScopedTimer timer(&tExtract);
    ++nExtract;
    s->clear();
    vector<int> assumptions, latches, reverse_transition_inputs;
    std::uint64_t parent_query_id = 0;
    auto parent_query = semantic_last_query.find(sat);
    if(parent_query != semantic_last_query.end())
        parent_query_id = parent_query->second;
    int distance = primed_first_dimacs - (num_inputs+num_latches+2);
    // inputs /\ inputs' /\ pre
    for(int i=0; i<num_inputs; ++i){
        int ipt = sat->val(unprimed_first_dimacs + i);
        int pipt = sat->val(primed_first_dimacs + i);
        if(ipt != 0){
            s->inputs.push_back(ipt);
            assumptions.push_back(ipt);
        }
        if(pipt > 0){
            pipt = (pipt-distance);
            assumptions.push_back(pipt);
            if(is_reverse())
                reverse_transition_inputs.push_back(pipt);
        }
        else if (pipt < 0){
            pipt = -(-pipt-distance);
            assumptions.push_back(pipt);
            if(is_reverse())
                reverse_transition_inputs.push_back(pipt);
        }
    }
    int sz = assumptions.size();

    for(int i=0; i<num_latches; ++i){
        int l = sat->val(unprimed_first_dimacs + num_inputs + i);
        if(l!=0){
            latches.push_back(l);
            assumptions.push_back(l);
        }
    }
    if(semantic_trace){
        vector<int> raw_state = latches;
        raw_state.push_back(0);
        raw_state.insert(raw_state.end(), s->inputs.begin(), s->inputs.end());
        semantic_event("state-raw", parent_query_id, "pdr", "predecessor",
                       findex, -1, &raw_state,
                       static_cast<int>(latches.size()), SAT);
    }

    if(is_reverse()){
        s->set_witness_latches(latches);
        if(succ != nullptr)
            succ->inputs = reverse_transition_inputs;
        if(!reverse_lifting_enabled){
            s->latches = latches;
            s->next = succ;
            return;
        }
        ++nReverseLiftAttempt;
    }

    if(lift == nullptr){
        lift = new_pdr_solver();
        configure_solver(lift, "lift");
        encode_lift(lift);
    }
    lift->clear_act();

    // encoding -(constraints' /\ pre') <-> -constraints' \/ -pre'
    int act_var = lift->max_var() + 1;
    lift->add(-act_var);
    if(split_ands)
        lift->add(notInvConstraints);
    else{
        for(int l : constraints)
            lift->add(-l);
        for(int l : constraints_prime)
            lift->add(-l);
    }
    if(succ == nullptr){
        if(!is_reverse())
            lift->add(-bad_prime);
        else
            for(int l : init_state)
                lift->add(prime_lit(-l));
    }else{
        for(int l: succ->latches)
            lift->add(prime_lit(-l));
    }
    lift->add(0);

    if(cfg_use_heuristic and cfg_assumption_allsort){
        stable_sort(assumptions.begin(), assumptions.end(), *heuristic_lit_cmp);
        reverse(assumptions.begin(), assumptions.end());
    }
    else if(cfg_use_heuristic){
        stable_sort(assumptions.begin()+sz, assumptions.end(), *heuristic_lit_cmp);
        reverse(assumptions.begin()+sz, assumptions.end());
    }
    else
        stable_sort(assumptions.begin(), assumptions.end(), Lit_CMP());

    for(int i=0; i<assumptions.size(); i++){
        if(assumptions[i] >= num_inputs+num_latches+2)
            assumptions[i] = assumptions[i] + distance;
        else if(assumptions[i] <= -(num_inputs+num_latches+2))
            assumptions[i] = assumptions[i] - distance;
    }

    lift->assume(act_var);
    for(int l : assumptions)
        lift->assume(l);
    auto lift_solve_start = std::chrono::steady_clock::now();
    if(nExtract == 1 && cfg_phase_stats)
        cout << "c PDR_PHASE thread=" << thread_index
             << " phase=first_lift_solve event=start" << endl;
    SATSearchStats lift_semantic_before;
    if(semantic_trace)
        lift_semantic_before = lift->search_stats();
    maybe_print_progress_stats("lift");
    int res = lift->solve();
    std::uint64_t lift_query_id = 0;
    if(semantic_trace){
        SATSearchStats lift_semantic_after = lift->search_stats();
        lift_query_id = semantic_query(lift, "lift", "lift", findex, -1,
                                       assumptions, res,
                                       lift_semantic_before, lift_semantic_after);
    }
    double lift_solve_elapsed = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - lift_solve_start).count();
    if(nExtract == 1){
        tFirstLiftSolve = lift_solve_elapsed;
        if(cfg_phase_stats)
            cout << "c PDR_PHASE thread=" << thread_index
                 << " phase=first_lift_solve event=done elapsed=" << tFirstLiftSolve << endl;
    }
    ++nQuery;

    if(res == UNKNOWN || (is_reverse() && res != UNSAT)){
        if(is_reverse()){
            ++nReverseLiftFallback;
            s->latches = latches;
            s->next = succ;
            lift->set_clear_act();
        }
        return;
    }
    assert(res == UNSAT);
    if(is_reverse())
        ++nReverseLiftSuccess;

    if(output_stats_for_extract){
        cout << "assumptions ";
        for(int l : assumptions){
            if(abs(l) < primed_first_dimacs)
                cout << variables[abs(l)].name << " "<< heuristic_lit_cmp->counts[abs(l)] << " ";
            else
                cout << variables[abs(l)].name << " "<< heuristic_lit_cmp->counts[abs(l)-distance] << " ";
        }
        cout << endl;

        vector<char> a(num_inputs + num_latches + 2, 'x');
        for(int i : s->inputs)
            a[abs(i)] = (i<0?'0':'1');
        for(int l : latches)
            a[abs(l)] = (l<0?'0':'1');

        cout<<'[';
        for(int i=1; i<=num_inputs; ++i)
            cout<<a[1+i];
        cout<<'|';
        for(int l=1; l<=num_latches; ++l)
            cout<<a[1+num_inputs+l];
        cout<<']';
        cout<<endl;

        cout << "lift \n";
        for(int l : assumptions){
            if(lift->failed(l))
                cout << variables[abs(l)].name << " ";
        }
        cout << endl;
    }

    for(int l : latches){
        if(lift->failed(l)){
            s->latches.push_back(l);
        }
    }
    semantic_event("state-lifted", parent_query_id, "pdr", "predecessor",
                   findex, -1, &s->latches,
                   static_cast<int>(s->latches.size()), res);

    bool cpo = false;
    if(findex){ 
        for(auto ci = frames[findex-1].cubes.begin(); ci!=frames[findex-1].cubes.end(); ci++){
            if ((s->latches).size() < (*ci).size()) break;
            if(includes((s->latches).begin(), (s->latches).end(), (*ci).begin(), (*ci).end(), abs_compare)){
                cpo = true;
                nkCore++;
                break;
            }
        }
    }
    int last_index = 0, corelen = 0;
    if(use_acc and cpo){
        int core_literal = 0;
        for(int i=0; i<assumptions.size(); i++){
            int l = assumptions[i];
            if(abs(l) >= num_inputs+2 and abs(l) <= num_inputs+num_latches+1) corelen++;
            if(lift->failed(l)){
                double score = (i-core_literal)/20.0;
                if(score > 1.0) score = 1.05;
                if(abs(l) < primed_first_dimacs)
                    heuristic_lit_cmp->counts[abs(l)] += score; 
                else
                    heuristic_lit_cmp->counts[abs(l)-distance] += score;
                core_literal = i;
                last_index = corelen;
            }
        }
    }
    else{
        for(int i=0; i<assumptions.size(); i++){
            int l = assumptions[i];
            if(abs(l) >= num_inputs+2 and abs(l) <= num_inputs+num_latches+1) 
                corelen++;
            if(lift->failed(l))
                last_index = corelen;
        }           
    }
    nCore++;
    nCorelen += last_index;
    ++nLiftCore;
    nLiftCoreInputLiterals += latches.size();
    nLiftCoreLiterals += s->latches.size();
    semantic_event("core", lift_query_id, "lift", "lift", findex, -1,
                   &s->latches, static_cast<int>(s->latches.size()), res);

    if(is_reverse() && succ != nullptr)
        succ->inputs = reverse_transition_inputs;
    s->next = succ;
    lift->set_clear_act();
}

// Find a state in the top frame with a transition to the search target.
bool PDR::get_pre_of_target(State *s){
    ScopedTimer timer(&tPre);
    ++nPre;
    s->clear();
    int Fk = depth();
    assume_target(frames[Fk].solver, true);
    ++predecessor_phase_queries;
    vector<int> first_pre_phases = nPre == 1 && first_pre_phase_mode != "default"
        ? first_pre_phase_literals()
        : predecessor_phase_literals(nullptr, predecessor_phase_queries);
    for(int literal : first_pre_phases)
        frames[Fk].solver->set_phase(literal);
    auto pre_solve_start = std::chrono::steady_clock::now();
    if(nPre == 1 && cfg_phase_stats)
        cout << "c PDR_PHASE thread=" << thread_index
             << " phase=first_pre_solve event=start" << endl;
    SATSearchStats pre_stats_before = frames[Fk].solver->search_stats();
    maybe_print_progress_stats("get-pre");
    int res = frames[Fk].solver->solve();
    for(int literal : first_pre_phases)
        frames[Fk].solver->clear_phase(literal);
    SATSearchStats pre_stats_after = frames[Fk].solver->search_stats();
    static const vector<int> no_literals;
    std::uint64_t pre_query_id = semantic_query(
        frames[Fk].solver, "frame", "get-pre", Fk, -1,
        no_literals, res, pre_stats_before, pre_stats_after);
    double pre_solve_elapsed = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - pre_solve_start).count();
    if(nPre == 1){
        tFirstPreSolve = pre_solve_elapsed;
        if(cfg_phase_stats)
            cout << "c PDR_PHASE thread=" << thread_index
                 << " phase=first_pre_solve event=done elapsed=" << tFirstPreSolve << endl;
        if(cfg_phase_stats){
            cout << "c PDR_SOLVER_QUERY thread=" << thread_index
                 << " phase=first_pre_solve"
                 << " result=" << res
                 << " elapsed=" << tFirstPreSolve
                 << " conflicts=" << (pre_stats_after.conflicts - pre_stats_before.conflicts)
                 << " decisions=" << (pre_stats_after.decisions - pre_stats_before.decisions)
                 << " propagations=" << (pre_stats_after.propagations - pre_stats_before.propagations)
                 << " restarts=" << (pre_stats_after.restarts - pre_stats_before.restarts)
                 << endl;
        }
    }
    ++nQuery;
    if(res == SAT){
        State *target_state = new State();
        for(int i=0; i<num_inputs; ++i){
            int pipt = (frames[Fk].solver)->val(primed_first_dimacs + i);
            if(pipt > 0)
                target_state->inputs.push_back(pipt-(primed_first_dimacs-unprimed_first_dimacs));
            else if(pipt < 0)
                target_state->inputs.push_back(pipt+(primed_first_dimacs-unprimed_first_dimacs));
        }
        for(int i=0; i<num_latches; ++i){
            int l = (frames[Fk].solver)->val(primed_first_dimacs + num_inputs + i);
            if(l > 0)
                target_state->latches.push_back(l-(primed_first_dimacs-unprimed_first_dimacs));
            else if(l < 0)
                target_state->latches.push_back(l+(primed_first_dimacs-unprimed_first_dimacs));
        }
        if(is_reverse())
            target_state->set_witness_latches(target_state->latches);
        if(semantic_trace){
            vector<int> target = target_state->latches;
            target.push_back(0);
            target.insert(target.end(), target_state->inputs.begin(), target_state->inputs.end());
            semantic_event("state-target", pre_query_id, "pdr", "target",
                           Fk, -1, &target,
                           static_cast<int>(target_state->latches.size()), res);
        }
        extract_state_from_sat(frames[Fk].solver, s, nullptr, Fk);
        s->next = target_state;
        return true;
    }else{
        return false;
    }
}

bool PDR::rec_block_cube(){
    ScopedTimer timer(&tBlock);
    ++nBlock;
    // all the states dealed in rec_block process will not be released.
    vector<State *> states;
    int ct = 0;
    while(!obligation_queue.empty()){
        import_shared_lemmas();
        if(cancellation_pending() || (!cooperative_mode && RESULT != 0))
            return true;
        Obligation obl = *obligation_queue.begin();
        semantic_event("obligation", 0, "pdr", "block",
                       obl.frame_k, obl.depth, &obl.state->latches,
                       static_cast<int>(obl.state->latches.size()), 0);

        if(output_stats_for_recblock){
            cout << "\nRemaining " << obligation_queue.size() << " Obligation\n";
            cout << "Handling Frames[" << obl.frame_k << "]'s " << "Obligation, depth = " << obl.depth << " , stamp = " << ((obl.state)->index);
            show_state(obl.state);
        }
        bool source_reached = init_equalities.empty()
            ? is_source(obl.state->latches)
            : is_source(obl.state->latches, obl.state->inputs);
        if(cancellation_pending())
            return true;
        if(source_reached){
            State *source_state = new State();
            for(int i=0; i<num_inputs; ++i){
                int input = init->val(unprimed_first_dimacs + i);
                if(input != 0)
                    source_state->inputs.push_back(input);
            }
            for(int i=0; i<num_latches; ++i){
                int latch = init->val(unprimed_first_dimacs + num_inputs + i);
                if(latch != 0)
                    source_state->latches.push_back(latch);
            }
            source_state->set_witness_latches(source_state->latches);
            if(!is_reverse() && init_equalities.empty())
                source_state->inputs = obl.state->inputs;
            source_state->next = obl.state->next;
            cex_state_idx = source_state;
            find_cex = true;
            return !finalize_counterexample();
        }
        // check SAT?[Fk /\ -s /\ T /\ s']
        SATSolver * sat = frames[obl.frame_k].solver;
        bool inductive = is_inductive(sat, obl.state->latches, true, true,
                                      "block", obl.frame_k, obl.depth);
        if(cancellation_pending())
            return true;
        if(inductive){
            if(output_stats_for_recblock){
                cout << "the obligation is already fulfilled, and cube is lifted to ";
                show_litvec(core);
            }
            // latches is inductive to Fk
            obligation_queue.erase(obligation_queue.begin());
            Cube tmp_core = core;
            generalize(tmp_core, obl.frame_k);
            if(cancellation_pending())
                return true;
            if(output_stats_for_recblock){
                cout << "the cube is generalized to ";
                show_litvec(tmp_core);
            }

            if (cfg_use_punishment and (((obl.state)->next) != nullptr)){
                if(tmp_core.size() > 30){
                    (((obl.state)->next)->failed) = (((obl.state)->next)->failed) + 5;
                }
                else if(tmp_core.size() > 20){
                    (((obl.state)->next)->failed) = (((obl.state)->next)->failed) + 3;
                }
                else if(tmp_core.size() > 10){
                    (((obl.state)->next)->failed) = (((obl.state)->next)->failed) + 1;
                }
            }

            int k;
            for(k = obl.frame_k + 1; k<=depth(); ++k){
                ++nPush;
                bool can_push = is_inductive(frames[k].solver, tmp_core, false, true,
                                              "block-push", k, obl.depth);
                if(cancellation_pending())
                    return true;
                if(!can_push){
                    break;
                }
            }

            bool pushpo = 0;
            vector<int> la = obl.state->latches;
            // for(int i=0; i<la.size(); i++) cout << la[i] << " "; cout << endl;
            // show_litvec(la);
            for(auto ci = frames[k].cubes.begin(); ci!=frames[k].cubes.end(); ci++){
                vector<int> lemma = (*ci);
                //for(int i=0; i<lemma.size(); i++) cout << lemma[i] << " "; cout << endl;
                if (la.size() < lemma.size()) break;
                if (includes(la.begin(), la.end(), lemma.begin(), lemma.end(), abs_compare)){
                    pushpo = 1;
                    nkobl++;
                    break;
                }
            }
            nobl++;
            if(!use_pr) pushpo = 1;            
            bool permanent = k > depth() && maybe_certify_inductive_cube(tmp_core);
            if(!permanent)
                add_cube(tmp_core, k, true, false,
                         k - obl.frame_k + (tmp_core.size() < core.size()));
            if(k <= depth() and pushpo)
               obligation_queue.insert(make_obligation(obl.state, k, obl.depth));
        }else{
            if(((obl.state)->failed_depth) and ((obl.state)->failed_depth) <= obl.depth + obl.frame_k){
                obligation_queue.erase(obligation_queue.begin());
                if (((obl.state)->next) != nullptr) {
                    (((obl.state)->next)->failed_depth) = ((obl.state)->failed_depth);
                }
                continue;
            }
            if((obl.state)->failed >= 5 and ((obl.depth + obl.frame_k) > depth())){
                obligation_queue.erase(obligation_queue.begin());
                ((obl.state)->failed_depth) = obl.depth + obl.frame_k;
                if (((obl.state)->next) != nullptr) {
                    (((obl.state)->next)->failed_depth) = ((obl.state)->failed_depth);
                }
                continue;
            }

            State *s = new State();
            ++nCTI;
            if(obl.frame_k == 0){
                s->clear();
                for(int i=0; i<num_inputs; ++i){
                    int ipt = sat->val(unprimed_first_dimacs + i);
                    if(ipt != 0)
                        s->inputs.push_back(ipt);
                }
                for(int i=0; i<num_latches; ++i){
                    int l = sat->val(unprimed_first_dimacs + num_inputs + i);
                    if(l != 0)
                        s->latches.push_back(l);
                }
                if(is_reverse())
                    s->set_witness_latches(s->latches);
                s->next = obl.state;
                cex_state_idx = s;
                find_cex = true;
                return !finalize_counterexample();
            }else{
                extract_state_from_sat(sat, s, obl.state, obl.frame_k);
                if(cancellation_pending())
                    return true;
                obligation_queue.insert(make_obligation(
                    s, obl.frame_k - 1, obl.depth + 1));
            }
        }
    }
    return true;
}

bool PDR::propagate(){
    ScopedTimer timer(&tPropagate);
    // all cubes are sorted according to the variable number;
    int start_k = 1;

    if(cfg_use_earliest_strengthened_frame){
        if(depth() % 5 and depth() > 20)
            start_k = earliest_strengthened_frame;
    }
    if(top_frame_cannot_reach_bad){
        if(output_stats_for_others) cout << "top frame cannot reach bad" << endl;
        start_k = depth();
    }

    if (output_stats_for_propagate)
        cout << "start to propagate" << endl;

    for(int i=start_k; i<=depth(); ++i){
        int ckeep = 0, cprop = 0;
        for(auto ci = frames[i].cubes.begin(); ci!=frames[i].cubes.end();){
            if(cancellation_pending())
                return false;
            bool inductive = is_inductive(frames[i].solver, *ci, true, true,
                                          "propagate", i, -1);
            if(cancellation_pending())
                return false;
            if(inductive){
                ++cprop;
                ++nProp;
                ++nPush;
                Cube pushed = core.size() < ci->size() ? core : *ci;
                bool permanent = i == depth() && maybe_certify_inductive_cube(pushed);
                if(cancellation_pending())
                    return false;

                if(!permanent){
                    // The lemma remains frame-local and moves one level up.
                    if(core.size() < ci->size())
                        add_cube(core, i+1, true, true, 1);
                    else
                        add_cube(core, i+1, false, true, 0);
                }
                auto rm = ci++;
                frames[i].cubes.erase(rm);

            }else{
                ++ckeep;
                ++nUnpush;
                ci++;
            }
        }
        if (output_stats_for_propagate)
            cout << "frame="<<i << " ckeep=" << ckeep << " cprop=" << cprop  << endl;
        if(frames[i].cubes.size() == 0){
            int invariant;
            int new_and_gate;
            bool first_cube = 1;
            Cube badcube;
            badcube.clear();
            badcube.push_back(bad);
            frames[i+1].cubes.insert(badcube);
            for(int l:constraints){
                badcube.clear();
                badcube.push_back(-l);
                frames[i+1].cubes.insert(badcube);
            }
            if(output_stats_for_frames)  show_frames();
            export_fixed_point(i);
            if(output_certificate){
                for(const Cube &c : inductive_cubes)
                    frames[i+1].cubes.insert(c);
                for(int d = i+2; d <= depth()+1; d++){
                    for(const Cube &c : frames[d].cubes)
                        frames[i+1].cubes.insert(c);
                }
                for(const Cube &c : frames[i+1].cubes){
                    Cube cc = c;
                    if(cc.size() == 0) cc.push_back(-1);
                    sort(cc.begin(), cc.end(), Lit_CMP());
                    reverse(cc.begin(), cc.end());
                    bool first_bit = 1;
                    for(int l:cc){
                        if(first_bit){
                            new_and_gate = l;
                            first_bit = 0;
                            continue;
                        }
                        int o = 1+num_inputs+num_latches+num_ands+1;
                        if(abs(new_and_gate) > abs(l)) ands.push_back(And(o, new_and_gate, l));
                        else ands.push_back(And(o, l, new_and_gate));
                        new_and_gate = o;
                        num_ands++;
                    }
                    if(first_cube){
                        invariant = -new_and_gate;
                        first_cube = 0;
                        continue;
                    }
                    int o = 1+num_inputs+num_latches+num_ands+1;
                    if(abs(new_and_gate) > abs(invariant)) ands.push_back(And(o, -new_and_gate, invariant));
                    else ands.push_back(And(o, invariant, -new_and_gate));
                    invariant = o;
                    num_ands++;
                }
                bad = -invariant;
                show_aag();
            }
            return true;
        }

    }
    return false;
}

void PDR::mic(Cube &cube, int k, int depth){
    ++nmic;
    int mic_failed = 0;
    set<int> required;
    sort(cube.begin(), cube.end(), Lit_CMP());

    //drop literal
    if(mic_effective_order_mode != "legacy"){
        auto structural_distance = [&](int literal){
            const int index = latch_index_from_literal(literal);
            if(index < 0)
                return -1.0;
            const int distance = latch_bad_distance[index];
            return static_cast<double>(distance < 0
                ? decision_distance_max_depth + 2 : distance);
        };
        auto feedback_utility = [&](int literal){
            const int index = latch_index_from_literal(literal);
            if(index < 0)
                return 0.0;
            const double attempts = static_cast<double>(latch_mic_attempts[index]);
            const double success_probability =
                (static_cast<double>(latch_mic_successes[index]) + 1.0)
                / (attempts + 2.0);
            const double mean_queries = attempts > 0.0
                ? static_cast<double>(latch_mic_query_sum[index]) / attempts
                : 1.0;
            return success_probability / (1.0 + mean_queries);
        };
        stable_sort(cube.begin(), cube.end(), [&](int a, int b){
            const double distance_a = structural_distance(a);
            const double distance_b = structural_distance(b);
            const double feedback_a = feedback_utility(a);
            const double feedback_b = feedback_utility(b);
            if(mic_effective_order_mode == "distance-near")
                return distance_a < distance_b;
            if(mic_effective_order_mode == "distance-far")
                return distance_a > distance_b;
            if(mic_effective_order_mode == "feedback")
                return feedback_a > feedback_b;
            const double scale = static_cast<double>(
                std::max(1, decision_distance_max_depth + 2));
            const double score_a = distance_a / scale
                + mic_feedback_weight * feedback_a;
            const double score_b = distance_b / scale
                + mic_feedback_weight * feedback_b;
            return score_a > score_b;
        });
    }else if(cfg_use_heuristic && thread_index <= 1)
        stable_sort(cube.begin(), cube.end(), *heuristic_lit_cmp);
    else
        std::shuffle(cube.begin(), cube.end(), random_engine);

    Cube tmp_cube = cube;
    for(int l : tmp_cube){
        if(cancellation_pending())
            return;
        vector<int> cand;
        if(find(cube.begin(), cube.end(), l) == cube.end()) {mic_failed = 0; continue;}
        for(int i : cube){
            if(i != l)
                cand.push_back(i);
        }
        if(output_stats_for_ctg){
             cout << "start ctgdown, level = " << k << ", depth = " << depth << ", cube = ";
             show_litvec(cand);
        }
        const int cube_before = static_cast<int>(cube.size());
        const int queries_before = nQuery;
        const int ctg_before = nCTG;
        const auto attempt_start = std::chrono::steady_clock::now();
        bool generalized = CTG_down(cand, k, depth, required);
        const double attempt_seconds = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - attempt_start).count();
        decision_event("mic_attempt", k, depth, l, cube_before,
                       generalized ? static_cast<int>(cand.size()) : cube_before,
                       generalized ? 1 : 0, attempt_seconds,
                       nQuery - queries_before, nCTG - ctg_before);
        const int latch_index = latch_index_from_literal(l);
        if(latch_index >= 0){
            ++latch_mic_attempts[latch_index];
            latch_mic_query_sum[latch_index] += static_cast<std::uint64_t>(
                std::max(0, nQuery - queries_before));
            latch_mic_elapsed_sum[latch_index] += attempt_seconds;
            if(generalized)
                ++latch_mic_successes[latch_index];
            else
                ++latch_mic_failures[latch_index];
        }
        if(cancellation_pending())
            return;
        if(generalized){
            if(output_stats_for_ctg){
                cout << "ctgdown successed, the stronger cube is ";
                show_litvec(cand);
            }
            mic_failed = 0;
            cube = cand;
        }else{
            if(output_stats_for_ctg){
                cout << "ctgdown failed, try to remove another lit\n";
            }
            mic_failed++;
            if(mic_failed > cfg_option_ctg_tries){
                ++nAbortMic;
                break;
            }
            required.insert(l);
        }
    }
}

bool PDR::CTG_down(Cube &cube, int k, int rec_depth, set<int> &required){
    ScopedTimer timer(&tCTG);
    int ctg_ct = 0;
    int join_ct = 0;
    while(true){
        if(cancellation_pending())
            return false;
        bool source = is_source(cube);
        if(cancellation_pending())
            return false;
        if(source)
            return false;
        // check inductive;
        SATSolver *sat = frames[k].solver;
        bool inductive = is_inductive(sat, cube, true, true,
                                      "mic", k, rec_depth);
        if(cancellation_pending())
            return false;
        if(inductive){
            if(output_stats_for_ctg) cout << "The new cube satisfies induction" << endl;
            if(core.size() < cube.size()){
                ++nCoreReduced;
                cube = core;
            }
            return true;
        }
        else{
            if(rec_depth > cfg_option_ctg_max_depth)
                return false;
            std::unique_ptr<State> s(new State());
            std::unique_ptr<State> succ(new State(cube, Cube()));
            extract_state_from_sat(sat, s.get(), succ.get(), k);
            if(cancellation_pending())
                return false;
            int breaked = false;
            if(output_stats_for_ctg){
                cout << "The new cube fails induction, find ctg ";
                show_litvec(s->latches);
            }
            // CTG
            bool source_ctg = false;
            if(ctg_ct < cfg_option_ctg_tries && k > 1){
                source_ctg = is_source(s->latches);
                if(cancellation_pending())
                    return false;
            }
            bool ctg_inductive = false;
            if(ctg_ct < cfg_option_ctg_tries && k > 1 && !source_ctg)
                ctg_inductive = is_inductive(frames[k-1].solver, s->latches, true, true,
                                              "ctg", k - 1, rec_depth);
            if(cancellation_pending())
                return false;
            if(ctg_ct < cfg_option_ctg_tries && k > 1 && !source_ctg && ctg_inductive){
                if(output_stats_for_ctg){
                    cout << "ctg satisfies induction, is lifted to ";
                    show_litvec(core);
                }
                Cube &ctg = core;
                ctg_ct ++;
                ++nCTG;
                int i;
                for(i=k; i<=depth(); ++i){
                    ++nPush;
                    bool can_push = is_inductive(frames[i].solver, ctg, false, true,
                                                  "ctg-push", i, rec_depth);
                    if(cancellation_pending())
                        return false;
                    if(!can_push)
                        break;
                }
                int Size =  ctg.size();
                mic(ctg, i-1, rec_depth+1);
                if(cancellation_pending())
                    return false;
                add_cube(ctg, i, true, false, i-k+1 + (ctg.size() < Size));
            }else{
                if(join_ct < cfg_option_max_joins){
                    ctg_ct=0;
                    join_ct++;
                    vector<int> join;
                    set<int> s_cti(s->latches.begin(), s->latches.end());
                    for(int i : cube){
                        if(s_cti.find(i) != s_cti.end())
                            join.push_back(i);
                        else if(required.find(i) != required.end()){
                            breaked = true;
                            ++nAbortJoin;
                            break;
                        }
                    }
                    cube = join;
                    if(output_stats_for_ctg){
                        cout << "breaked = "<< breaked << ", ctg cant be removed, join cube and ctg ";
                        show_litvec(cube);
                    }
                }else{
                    breaked = true;
                }
            }
            if(breaked) return false;
        }
    }
}

void PDR::generalize(Cube &cube, int k){
    ScopedTimer timer(&tGeneralize);
    ++nGeneralize;
    if(semantic_trace)
        semantic_event("generalize-before", 0, "pdr", "generalize",
                       k, 1, &cube, static_cast<int>(cube.size()), 0);
    mic(cube, k, 1);
    if(semantic_trace)
        semantic_event("generalize-after", 0, "pdr", "generalize",
                       k, 1, &cube, static_cast<int>(cube.size()), 0);
}

void PDR::clear_po(){
    for(Obligation o : obligation_queue){
        delete o.state;
    }
    obligation_queue.clear();
}

void PDR::release_frames(){
    for(Frame &frame : frames){
        if(frame.solver != nullptr){
            delete frame.solver;
            frame.solver = nullptr;
        }
    }
    frames.clear();
}

void PDR::restart_search_frames(){
    obligation_queue.clear();
    cex_states.clear();
    cex_state_idx = nullptr;
    find_cex = false;
    release_frames();
    new_frame();
    encode_source_condition(frames[0].solver);
    new_frame();
    new_frame();
    assert(depth() == 1);
    top_frame_cannot_reach_bad = true;
    earliest_strengthened_frame = depth();
    reverse_lift_restart_requested = false;
}

vector<TraceFrame> PDR::counterexample_trace() const{
    vector<TraceFrame> trace;
    for(State *state : cex_states)
        trace.push_back(TraceFrame{state->trace_latches(), state->inputs});
    return trace;
}

void PDR::set_counterexample_trace(const vector<TraceFrame> &trace){
    cex_states.clear();
    for(const TraceFrame &frame : trace){
        State *state = new State(frame.latches, frame.inputs);
        cex_states.push_back(state);
    }
    find_cex = !cex_states.empty();
}

bool PDR::validate_trace(const vector<TraceFrame> &trace, bool require_init) const{
    if(trace.empty())
        return false;

    vector<pair<int, And> > gates;
    for(const And &gate : ands) gates.push_back(make_pair(0, gate));
    for(const And &gate : xors) gates.push_back(make_pair(1, gate));
    for(const And &gate : ors)  gates.push_back(make_pair(2, gate));
    sort(gates.begin(), gates.end(), [](const pair<int, And> &a, const pair<int, And> &b){
        return a.second.o < b.second.o;
    });

    vector<char> latch_values(num_latches, 0);
    for(int l : trace.front().latches){
        int index = abs(l) - (unprimed_first_dimacs + num_inputs);
        if(index >= 0 && index < num_latches)
            latch_values[index] = l > 0;
    }
    if(require_init){
        for(int literal : init_state){
            int index = abs(literal) - (unprimed_first_dimacs + num_inputs);
            if(index < 0 || index >= num_latches)
                return false;
            if(static_cast<bool>(latch_values[index]) != (literal > 0))
                return false;
        }
    }

    for(size_t frame_index=0; frame_index<trace.size(); ++frame_index){
        vector<char> values(primed_first_dimacs, 0);
        values[1] = 0;
        for(int input : trace[frame_index].inputs){
            int var = abs(input);
            if(var >= unprimed_first_dimacs && var < unprimed_first_dimacs + num_inputs)
                values[var] = input > 0;
        }
        for(int i=0; i<num_latches; ++i)
            values[unprimed_first_dimacs + num_inputs + i] = latch_values[i];

        auto value_of = [&values](int lit) -> bool {
            bool value = values[abs(lit)] != 0;
            return lit > 0 ? value : !value;
        };

        for(int l : trace[frame_index].latches){
            if(!value_of(l))
                return false;
        }
        for(const pair<int, And> &entry : gates){
            const And &gate = entry.second;
            bool left = value_of(gate.i1);
            bool right = value_of(gate.i2);
            if(entry.first == 0)
                values[gate.o] = left && right;
            else if(entry.first == 1)
                values[gate.o] = left != right;
            else
                values[gate.o] = left || right;
        }
        if(require_init && frame_index == 0){
            for(const pair<int, int> &equality : init_equalities){
                if(value_of(equality.first) != value_of(equality.second))
                    return false;
            }
        }
        for(int constraint : constraints){
            if(!value_of(constraint))
                return false;
        }

        if(frame_index + 1 == trace.size())
            return value_of(bad);

        vector<char> next_values(num_latches, 0);
        for(int i=0; i<num_latches; ++i)
            next_values[i] = value_of(nexts[i]);
        latch_values.swap(next_values);
    }
    return false;
}

bool PDR::map_trace_from(const PDR &source, const TraceFrame &source_frame,
                         TraceFrame &mapped_frame) const{
    if(num_inputs != source.num_inputs || num_latches != source.num_latches)
        return false;

    mapped_frame.inputs.clear();
    mapped_frame.latches.clear();
    for(int literal : source_frame.inputs){
        int index = abs(literal) - source.unprimed_first_dimacs;
        if(index < 0 || index >= num_inputs)
            return false;
        int mapped = unprimed_first_dimacs + index;
        mapped_frame.inputs.push_back(literal < 0 ? -mapped : mapped);
    }
    const int source_first_latch = source.unprimed_first_dimacs + source.num_inputs;
    const int first_latch = unprimed_first_dimacs + num_inputs;
    for(int literal : source_frame.latches){
        int index = abs(literal) - source_first_latch;
        if(index < 0 || index >= num_latches)
            return false;
        int mapped = first_latch + index;
        mapped_frame.latches.push_back(literal < 0 ? -mapped : mapped);
    }
    sort(mapped_frame.inputs.begin(), mapped_frame.inputs.end(), Lit_CMP());
    sort(mapped_frame.latches.begin(), mapped_frame.latches.end(), Lit_CMP());
    return true;
}

bool PDR::block_exact_state(const TraceFrame &state, int level, vector<TraceFrame> &trace){
    assert(engine_started);
    assert(level >= 0 && level <= depth());
    if(cancellation_pending())
        return true;
    obligation_queue.clear();
    cex_states.clear();
    find_cex = false;

    State *candidate = new State(state.latches, state.inputs);
    obligation_queue.insert(make_obligation(candidate, level, 1));
    top_frame_cannot_reach_bad = false;
    bool previous_requires_init = counterexample_requires_init;
    if(is_reverse())
        counterexample_requires_init = false;
    bool blocked = rec_block_cube();
    counterexample_requires_init = previous_requires_init;
    if(cancellation_pending()){
        obligation_queue.clear();
        return true;
    }
    if(!blocked)
        trace = counterexample_trace();
    obligation_queue.clear();
    return blocked;
}

bool PDR::find_bridge(PDR &reverse_pdr, BridgeCandidate &bridge){
    assert(!is_reverse());
    assert(reverse_pdr.is_reverse());
    assert(depth() >= 1 && reverse_pdr.depth() >= 1);
    assert(num_inputs == reverse_pdr.num_inputs);
    assert(num_latches == reverse_pdr.num_latches);

    int forward_level = depth();
    int reverse_level = reverse_pdr.depth();
    SATSolver *solver = frames[forward_level].solver;
    int act = solver->max_var() + 1;

    // Require the forward successor to be in the reverse frame.  Reverse frames
    // exclude Init and contain every clause stored at their level or above.
    solver->add(-act);
    for(int l : init_state)
        solver->add(prime_lit(-l));
    solver->add(0);

    for(int k=reverse_level; k<static_cast<int>(reverse_pdr.frames.size()); ++k){
        for(const Cube &cube : reverse_pdr.frames[k].cubes){
            Cube canonical, mapped_cube;
            if(!reverse_pdr.cube_to_canonical(cube, canonical) ||
               !cube_from_canonical(canonical, mapped_cube))
                return false;
            solver->add(-act);
            for(int l : mapped_cube)
                solver->add(prime_lit(-l));
            solver->add(0);
        }
    }

    solver->assume(act);
    maybe_print_progress_stats("bridge");
    int status = solver->solve();
    ++nQuery;
    if(status != SAT){
        solver->add(-act); solver->add(0);
        return false;
    }

    bridge.left.latches.clear();
    bridge.left.inputs.clear();
    bridge.right.latches.clear();
    bridge.right.inputs.clear();
    for(int i=0; i<num_inputs; ++i){
        int input = solver->val(unprimed_first_dimacs + i);
        if(input != 0)
            bridge.left.inputs.push_back(input);
    }
    for(int i=0; i<num_latches; ++i){
        int latch = unprimed_first_dimacs + num_inputs + i;
        int current_value = solver->val(latch);
        int next_value = solver->val(prime_var(latch));
        assert(current_value != 0 && next_value != 0);
        bridge.left.latches.push_back(current_value > 0 ? latch : -latch);
        bridge.right.latches.push_back(next_value > 0 ? latch : -latch);
    }

    solver->add(-act); solver->add(0);
    return true;
}

bool PDR::check_BMC0(){
    assert(frames.size() == 0);
    // F0 is the source set: Init in forward mode and Bad in reverse mode.
    new_frame();
    encode_source_condition(frames[0].solver);

    checker = new_pdr_solver();
    configure_solver(checker, "checker");
    encode_source_condition(checker);
    if(!is_reverse())
        encode_bad_state(checker);
    encode_target_condition(checker, false);
    auto solve_start = std::chrono::steady_clock::now();
    if(cfg_phase_stats)
        cout << "c PDR_PHASE thread=" << thread_index
             << " phase=bmc0_solve event=start" << endl;
    SATSearchStats bmc_semantic_before;
    if(semantic_trace)
        bmc_semantic_before = checker->search_stats();
    maybe_print_progress_stats("bmc0");
    int status = checker->solve();
    if(semantic_trace){
        SATSearchStats bmc_semantic_after = checker->search_stats();
        static const vector<int> no_literals;
        semantic_query(checker, "checker", "bmc0", 0, 0,
                       no_literals, status,
                       bmc_semantic_before, bmc_semantic_after);
    }
    tBmc0Solve = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - solve_start).count();
    if(cfg_phase_stats)
        cout << "c PDR_PHASE thread=" << thread_index
             << " phase=bmc0_solve event=done elapsed=" << tBmc0Solve << endl;
    ++nQuery;
    if(status == UNKNOWN)
        return true;
    if(status != SAT)
        return true;

    State *s = new State();
    for(int i=0; i<num_inputs; ++i){
        int input = checker->val(unprimed_first_dimacs + i);
        if(input != 0)
            s->inputs.push_back(input);
    }
    for(int i=0; i<num_latches; ++i){
        int latch = checker->val(unprimed_first_dimacs + num_inputs + i);
        if(latch != 0)
            s->latches.push_back(latch);
    }
    if(is_reverse())
        s->set_witness_latches(s->latches);
    cex_state_idx = s;
    find_cex = true;
    cex_states.push_back(s);
    return false;
}

bool PDR::check_BMC1(){
    assert(frames.size() == 1);
    // push F1 (BMC1 SAT check skipped)
    new_frame();
    return true;
}

int PDR::start(bool cooperative){
    assert(!engine_started);
    if(cancellation_pending())
        return -1;
    cooperative_mode = cooperative;
    active_pdr_solver = env_lane_value(
        "MC_PDR_SOLVER_LANES", thread_index,
        std::getenv("MC_PDR_SOLVER") == nullptr ? "cadical" : std::getenv("MC_PDR_SOLVER"));
    if(!affine_auto_solver.empty())
        active_pdr_solver = affine_auto_solver;
    engine_started = true;
    engine_result = 0;
    if(!randomize_lane_seed){
        active_random_seed = cfg_random_seed;
    }else if(cfg_random_seed_explicit){
        active_random_seed = cfg_random_seed
            + 2u * static_cast<unsigned>(std::max(0, thread_index))
            + (is_reverse() ? 1u : 0u);
    }else{
        active_random_seed = random_process_seed()
            + 0x9e3779b9u * static_cast<unsigned>(thread_index + 1);
    }
    random_engine.seed(active_random_seed);
    initialize();
    if(cancellation_pending())
        return -1;

    if(!check_BMC0()) {
        engine_result = 10;
        return 10;
    }
    if(cancellation_pending())
        return -1;
    if(!check_BMC1()) {
        engine_result = 10;
        return 10;
    }
    if(affine_invariants_prove_target && !output_certificate){
        cout << "c PDR_AFFINE_INVARIANT status=proved count="
             << affine_parity_invariants.size() << " rank="
             << affine_invariants_reachable_rank << " modes="
             << affine_invariants_modes << endl;
        engine_result = 20;
        return 20;
    }

    // main loop of IC3, start from depth = 1.
    // Fk need to hold -Bad all the time
    new_frame();
    assert(depth() == 1);
    top_frame_cannot_reach_bad = true;
    earliest_strengthened_frame = depth();
    import_external_invariant();
    export_inductive_snapshot();
    if(invariant_proves_target){
        engine_result = 20;
        return engine_result;
    }
    import_shared_lemmas();
    return 0;
}

void PDR::probe_preprocessing(){
    active_pdr_solver = env_lane_value(
        "MC_PDR_SOLVER_LANES", thread_index,
        std::getenv("MC_PDR_SOLVER") == nullptr ? "cadical" : std::getenv("MC_PDR_SOLVER"));
    if(!affine_auto_solver.empty())
        active_pdr_solver = affine_auto_solver;
    active_random_seed = cfg_random_seed;
    random_engine.seed(active_random_seed);
    initialize();
    std::unique_ptr<SATSolver> translation_solver(new_pdr_solver());
    std::unique_ptr<SATSolver> lift_solver(new_pdr_solver());
    configure_solver(translation_solver.get(), "translation-probe");
    configure_solver(lift_solver.get(), "lift-probe");
    encode_translation(translation_solver.get());
    encode_lift(lift_solver.get());
    print_stats(0);
}

int PDR::step(){
    assert(engine_started);
    if(engine_result != 0)
        return engine_result;
    if(cancellation_pending())
        return -1;
    if(!cooperative_mode && RESULT != 0)
        return -1;

    if(reverse_lift_restart_requested)
        restart_search_frames();

    share_inductive_budget_remaining = std::max(0, cfg_share_inductive_budget);

    import_shared_lemmas();

    if(restart and depth() > restart_depth){
        release_frames();
        new_frame();
        encode_source_condition(frames[0].solver);
        new_frame();
        new_frame();
        assert(depth() == 1);
        top_frame_cannot_reach_bad = true;
        earliest_strengthened_frame = depth();
        restart_heuristic();
    }

    State *s = new State();
    bool flag = get_pre_of_target(s);
    if(cancellation_pending())
        return -1;
    if(flag){
        ++nCTI;
        obligation_queue.clear();
        obligation_queue.insert(make_obligation(s, depth()-1, 1));
        top_frame_cannot_reach_bad = false;
        bool blocked = rec_block_cube();
        if(engine_result < 0)
            return engine_result;
        if(reverse_lift_restart_requested)
            return 0;
        if(!blocked){
            engine_result = 10;
            return engine_result;
        }
        if(cancellation_pending())
            return -1;
        for(State *p : states) delete p;
        return 0;
    }

    assert(obligation_queue.size() == 0);
    if(output_stats_for_recblock) cout << "CTI not found\n";
    bool converged = propagate();
    if(cancellation_pending())
        return -1;
    if(converged){
        engine_result = 20;
        return engine_result;
    }
    if(output_stats_for_conclusion){
        cout << ". # Level        " << depth() << endl;
        cout << ". # Queries:     " << nQuery << endl;
        cout << ". # CTIs:        " << nCTI << endl;
        cout << ". # CTGs:        " << nCTG << endl;
        cout << ". # mic calls:   " << nmic << endl;
        cout << ". # Red. cores:  " << nCoreReduced << endl;
        cout << ". # Abort joins: " << nAbortJoin << endl;
        cout << ". # Abort mics:  " << nAbortMic << endl;
        if(nCube) cout << "Avg lits: " << float(nCubelen) / nCube << endl;  else cout << "Avg lits: 0\n";
    }
    new_frame();
    top_frame_cannot_reach_bad = true;
    earliest_strengthened_frame = depth();
    import_shared_lemmas();
    if(moreinfo_for_pdr) cout << "pdr" + to_string(thread_index) + "_step = " +  to_string(earliest_strengthened_frame) + "\n";
    return 0;
}

void PDR::finish(int result){
    if(!engine_started || frames.empty())
        return;
    int d = depth();
    if(moreinfo_for_pdr) cout <<  "depth" + to_string(thread_index) + " = " + to_string(d) + "\n";
    if(result >= 0)
        print_stats(result);

    if(output_stats_for_cpo){
        cout << "nPush: " << nPush << endl;
        cout << "nUnpush: " << nUnpush << endl;
        cout << "nProp: " << nProp << endl;
        if(nCore) 
            cout << "Avg core lens: " << float(nCorelen)/nCore << endl << "keycore rate: " <<  float(nkCore)/nCore << endl ; 
        else 
            cout << "Avg core lens: 0\n" << "keycore rate: 0\n";
    }
    release_frames();
}

int PDR::check(){
    int result = start(false);
    while(result == 0)
        result = step();

    if(result > 0){
        std::lock_guard<std::mutex> lock(result_mutex);
        if(RESULT == 0){
            RESULT = result;
            if(result == 10)
                show_witness();
        }else{
            result = 0;
        }
    }
    if(result < 0)
        result = 0;
    finish(result);
    return result;
}
