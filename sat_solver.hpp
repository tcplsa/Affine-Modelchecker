#pragma once
#include "./ipasir.h"
#include "./cadical/src/ccadical.h"
#include "./minisat/simp/SimpSolver.h"
#include <vector>
#include <chrono>
#include <sstream>
#include <fstream>
#include <cstdint>
#include <cstdlib>
#include <unordered_map>
#include <unordered_set>
using std::vector;

extern "C" {
void *cmsat_create();
void *cmsat_create_with_interrupt(void *interrupt_flag);
void cmsat_destroy(void *solver);
bool cmsat_add_clause(void *solver, const int *lits, int len);
int cmsat_solve_with_assumptions(void *solver, const int *assumptions, int len);
int cmsat_model_value(void *solver, int variable);
int cmsat_max_var(void *solver);
int *cmsat_get_conflict(void *solver, int *out_size);
void cmsat_free_buffer(void *buffer);
bool cmsat_add_xor_clause_lits(void *solver, const int *lits, int len, bool rhs);
void cmsat_set_seed(void *solver, unsigned seed);
void cmsat_enable_gauss(void *solver);
bool cmsat_disable_gauss(void *solver);
void cmsat_set_no_simplify_at_startup(void *solver);
uint64_t cmsat_get_last_conflicts(void *solver);
uint64_t cmsat_get_last_decisions(void *solver);
uint64_t cmsat_get_last_propagations(void *solver);
void cmsat_get_gauss_stats(void *solver, uint64_t *checks,
                           uint64_t *row_xors, uint64_t *propagations,
                           uint64_t *conflicts, uint64_t *matrices,
                           uint64_t *rows, uint64_t *columns);
}

#define SAT 10
#define UNSAT 20
#define UNKNOWN 0
struct SATSearchStats {
    int64_t conflicts = 0;
    int64_t decisions = 0;
    int64_t propagations = 0;
    int64_t restarts = 0;
};

struct SATGaussStats {
    uint64_t checks = 0;
    uint64_t row_xors = 0;
    uint64_t propagations = 0;
    uint64_t conflicts = 0;
    uint64_t matrices = 0;
    uint64_t rows = 0;
    uint64_t columns = 0;
};

struct CNFSimplificationStats {
    int64_t attempted_vars = 0;
    int64_t eliminated_vars = 0;
    int64_t rejected_growth = 0;
    int64_t rejected_clause_limit = 0;
    int64_t removed_clauses = 0;
    int64_t resolvents = 0;
    int64_t resolvent_literals = 0;
    int64_t positive_occurrences = 0;
    int64_t negative_occurrences = 0;
    int64_t max_resolvent_size = 0;
    int64_t merge_checks = 0;
};

class SATSolver{
public:
    typedef int (*TerminateCallback)(void *);
    virtual ~SATSolver() = default;
    virtual void add(int dimacs_lit)=0;
    virtual void assume(int assumption_lit)=0;
    virtual int solve()=0;
    virtual int failed(int lit)=0;
    virtual int val(int lit)=0;
    virtual int max_var()=0;
    // Only the CMSat backend consumes this.  Other backends keep the
    // canonical CNF encoding emitted by PDR::encode_gate.
    virtual bool supports_native_xor() const { return false; }
    virtual bool add_xor_clause(const vector<int> &, bool) { return false; }
    virtual bool disable_gauss() { return false; }
    virtual SATGaussStats gauss_stats() const { return SATGaussStats(); }
    virtual void reserve_variables(int) {}
    virtual int fresh_variable() { return max_var() + 1; }
    virtual void set_variable_order(const vector<int> &external_vars) {}
    virtual void set_phase(int lit) {}
    virtual void clear_phase(int lit) {}
    virtual SATSearchStats search_stats() const { return SATSearchStats(); }
    virtual void set_terminate(void *state, TerminateCallback callback) {}
    virtual void set_trace_file(const std::string &path) {}
    virtual bool trace_enabled() const { return false; }
    void set_clear_act(){};
    void clear_act(){};
    virtual void show_info()=0;
};

// Incremental CryptoMiniSat backend used as an optional specialist PDR lane.
// It keeps the exact SATSolver contract used by PDR, including final
// assumption cores, while allowing XAG equations to remain native XORs.
class CMSatSolver: public SATSolver {
    void *solver;
    vector<int> clause;
    vector<int> assumptions;
    std::unordered_set<int> failed_assumptions;
    SATSearchStats totals;
    int nv = 0;
    bool clear_flag = false;
    bool gauss_enabled = false;

    void ensure_var(int variable) {
        nv = std::max(nv, variable);
        (void) variable;
    }

public:
    void configure_solver() {
        const char *seed = std::getenv("MC_PDR_CMSAT_SEED");
        if(seed != nullptr)
            cmsat_set_seed(solver, static_cast<unsigned>(std::strtoul(seed, nullptr, 10)));
        const char *gauss = std::getenv("MC_PDR_CMSAT_GAUSS");
        if(gauss == nullptr || (gauss[0] != '\0' && gauss[0] != '0')) {
            cmsat_enable_gauss(solver);
            gauss_enabled = true;
        }
        const char *simplify = std::getenv("MC_PDR_CMSAT_SIMPLIFY");
        if(simplify == nullptr || simplify[0] == '\0' || simplify[0] == '0')
            cmsat_set_no_simplify_at_startup(solver);
    }

public:
    CMSatSolver() {
        solver = cmsat_create();
        configure_solver();
    }

    ~CMSatSolver() override { cmsat_destroy(solver); }

    void add(int dimacs_lit) override {
        if(dimacs_lit == 0) {
            cmsat_add_clause(solver, clause.empty() ? nullptr : clause.data(),
                             static_cast<int>(clause.size()));
            clause.clear();
            return;
        }
        ensure_var(abs(dimacs_lit));
        clause.push_back(dimacs_lit);
    }

    bool supports_native_xor() const override { return true; }

    bool add_xor_clause(const vector<int> &literals, bool rhs) override {
        for(int literal : literals) {
            ensure_var(abs(literal));
        }
        return cmsat_add_xor_clause_lits(solver,
                                         literals.empty() ? nullptr : literals.data(),
                                         static_cast<int>(literals.size()), rhs);
    }

    bool disable_gauss() override {
        if(!gauss_enabled)
            return false;
        if(!cmsat_disable_gauss(solver))
            return false;
        gauss_enabled = false;
        return true;
    }

    void assume(int assumption_lit) override {
        ensure_var(abs(assumption_lit));
        assumptions.push_back(assumption_lit);
    }

    int solve() override {
        const int result = cmsat_solve_with_assumptions(
            solver, assumptions.empty() ? nullptr : assumptions.data(),
            static_cast<int>(assumptions.size()));
        totals.conflicts += static_cast<int64_t>(cmsat_get_last_conflicts(solver));
        totals.decisions += static_cast<int64_t>(cmsat_get_last_decisions(solver));
        totals.propagations += static_cast<int64_t>(cmsat_get_last_propagations(solver));
        failed_assumptions.clear();
        if(result == UNSAT) {
            // CMSat reports the negated literals of a failed assumption core.
            int count = 0;
            int *conflict = cmsat_get_conflict(solver, &count);
            for(int index=0; index<count; ++index)
                failed_assumptions.insert(-conflict[index]);
            cmsat_free_buffer(conflict);
        }
        assumptions.clear();
        return result;
    }

    int failed(int literal) override {
        return failed_assumptions.find(literal) != failed_assumptions.end();
    }

    int val(int literal) override {
        const int variable = abs(literal);
        if(variable < 1 || variable > cmsat_max_var(solver))
            return 0;
        const int value = cmsat_model_value(solver, variable);
        if(value > 0)
            return literal > 0 ? variable : -variable;
        if(value < 0)
            return literal > 0 ? -variable : variable;
        return 0;
    }

    int max_var() override { return nv; }

    void reserve_variables(int maximum) override {
        ensure_var(maximum);
    }

    int fresh_variable() override {
        return ++nv;
    }

    SATSearchStats search_stats() const override {
        return totals;
    }

    SATGaussStats gauss_stats() const override {
        SATGaussStats stats;
        if(!gauss_enabled)
            return stats;
        cmsat_get_gauss_stats(solver, &stats.checks, &stats.row_xors,
                              &stats.propagations, &stats.conflicts,
                              &stats.matrices, &stats.rows, &stats.columns);
        return stats;
    }

    void set_clear_act() { clear_flag = true; }
    void clear_act() {
        if(clear_flag) {
            add(-nv);
            add(0);
        }
        clear_flag = false;
    }
    void show_info() override {}
};

class CNFSimplifier: public SATSolver{
public:
    vector<int> simplified_cnf;
    virtual void var_enlarge_to(int variable) = 0;
    virtual void set_frozen(int literal) = 0;
    virtual void simplify() = 0;
    virtual int num_vars() const = 0;
    virtual int num_clauses() const = 0;
    virtual CNFSimplificationStats simplification_stats() const {
        return CNFSimplificationStats();
    }
};

class CaDiCaL: public SATSolver{
public:
    void * s;
    vector<int > cls;
    int nv;
    int internal_nv;
    bool clear_flag;
    bool canonical_variables;
    std::unordered_map<int, int> external_to_internal;
    std::ofstream trace;

    template<typename T>
    void trace_value(const T &value){
        trace.write(reinterpret_cast<const char *>(&value), sizeof(value));
    }

    void trace_operation(char operation){
        trace.write(&operation, 1);
    }

    int map_var(int external_var){
        nv = max(nv, external_var);
        if(!canonical_variables)
            return external_var;
        auto found = external_to_internal.find(external_var);
        if(found != external_to_internal.end())
            return found->second;
        int internal_var = ++internal_nv;
        external_to_internal[external_var] = internal_var;
        return internal_var;
    }

    int map_lit(int external_lit){
        if(external_lit == 0)
            return 0;
        int internal_var = map_var(abs(external_lit));
        return external_lit < 0 ? -internal_var : internal_var;
    }

    CaDiCaL(){
        s = ipasir_init();
        nv = 0;
        internal_nv = 0;
        clear_flag = false;
        const char *canonical = std::getenv("MC_PDR_CANONICAL_CNF");
        canonical_variables = canonical != nullptr
            && canonical[0] != '\0' && canonical[0] != '0';
        const char *reverse = std::getenv("MC_PDR_CADICAL_REVERSE");
        if(reverse != nullptr)
            ccadical_set_option(
                static_cast<CCaDiCaL *>(s), "reverse",
                reverse[0] != '\0' && reverse[0] != '0');
        // Allow toggling CaDiCaL's XOR-gate recognition during elimination
        // (elimxors). Default in CaDiCaL 1.5.2 is 1 (enabled); this lets us
        // A/B test the "XOR-gate aware preprocessing" benefit (plan A).
        const char *elimxors = std::getenv("MC_PDR_CADICAL_ELIMXORS");
        if(elimxors != nullptr)
            ccadical_set_option(
                static_cast<CCaDiCaL *>(s), "elimxors",
                elimxors[0] != '\0' && elimxors[0] != '0');
    }
    ~CaDiCaL(){
        if(trace.is_open()){
            trace_operation('E');
            trace.flush();
        }
        ipasir_release(s);
    }
    void add(int dimacs_lit){
        if(trace.is_open()){
            trace_operation('A');
            int32_t literal = dimacs_lit;
            trace_value(literal);
        }
        ipasir_add(s, map_lit(dimacs_lit));
        // if(dimacs_lit == 0){
        //     cout<<"add_cls: ";
        //     for(int l : cls){
        //         cout<<l<<" ";
        //     }cout<<endl;
        //     cls.clear();
        // }else{
        //     cls.push_back(dimacs_lit);
        // }
    }
    void assume(int assumption_lit){
        if(trace.is_open()){
            trace_operation('U');
            int32_t literal = assumption_lit;
            trace_value(literal);
        }
        ipasir_assume(s, map_lit(assumption_lit));
    }
    int solve(){
        SATSearchStats before;
        std::chrono::steady_clock::time_point started;
        if(trace.is_open()){
            before = search_stats();
            started = std::chrono::steady_clock::now();
        }
        int result = ipasir_solve(s);
        if(trace.is_open()){
            SATSearchStats after = search_stats();
            int32_t recorded_result = result;
            uint64_t elapsed_ns = static_cast<uint64_t>(
                std::chrono::duration_cast<std::chrono::nanoseconds>(
                    std::chrono::steady_clock::now() - started).count());
            int64_t conflicts = after.conflicts - before.conflicts;
            int64_t decisions = after.decisions - before.decisions;
            int64_t propagations = after.propagations - before.propagations;
            int64_t restarts = after.restarts - before.restarts;
            trace_operation('S');
            trace_value(recorded_result);
            trace_value(elapsed_ns);
            trace_value(conflicts);
            trace_value(decisions);
            trace_value(propagations);
            trace_value(restarts);
            trace.flush();
        }
        return result;
    }
    void set_terminate(void *state, TerminateCallback callback){
        ipasir_set_terminate(s, state, callback);
    }
    int failed(int lit){
        bool introduces_mapping = trace.is_open() && canonical_variables
            && external_to_internal.find(abs(lit)) == external_to_internal.end();
        // CaDiCaL's ipasir_failed returns 0 (not failed), 1 (in the final
        // core), or 2 (falsified during search but NOT part of the final
        // core). Only literals that are truly in the final core (1) should be
        // treated as failed; treating 2 as failed inflates the extracted core
        // and produces weaker lemmas (larger cubes) than CMS/MiniSat backends.
        int result = ipasir_failed(s, map_lit(lit));
        if(trace.is_open() && introduces_mapping){
            trace_operation('F');
            int32_t literal = lit;
            int32_t recorded_result = result;
            trace_value(literal);
            trace_value(recorded_result);
        }
        return result;    // 0/1/2 all treated as failed (original behavior)
    }
    int val(int lit){
        bool introduces_mapping = trace.is_open() && canonical_variables
            && external_to_internal.find(abs(lit)) == external_to_internal.end();
        int internal_value = ipasir_val(s, map_lit(lit));
        int result = 0;
        if(internal_value > 0)
            result = abs(lit);
        else if(internal_value < 0)
            result = -abs(lit);
        if(trace.is_open() && introduces_mapping){
            trace_operation('V');
            int32_t literal = lit;
            int32_t recorded_result = result;
            trace_value(literal);
            trace_value(recorded_result);
        }
        return result;
    }
    int max_var(){
        return nv;
    }
    void reserve_variables(int maximum) override {
        nv = std::max(nv, maximum);
    }
    int fresh_variable() override {
        return ++nv;
    }
    void set_variable_order(const vector<int> &external_vars){
        if(trace.is_open()){
            trace_operation('O');
            uint32_t count = static_cast<uint32_t>(external_vars.size());
            trace_value(count);
            for(int external_var : external_vars){
                int32_t variable = external_var;
                trace_value(variable);
            }
        }
        if(!canonical_variables)
            return;
        for(int external_var : external_vars){
            if(external_var > 0)
                map_var(external_var);
        }
    }
    void set_phase(int lit){
        ccadical_phase(static_cast<CCaDiCaL *>(s), map_lit(lit));
    }
    void clear_phase(int lit){
        ccadical_unphase(static_cast<CCaDiCaL *>(s), map_lit(lit));
    }
    void set_trace_file(const std::string &path){
        if(trace.is_open() || path.empty())
            return;
        trace.open(path.c_str(), std::ios::out | std::ios::binary | std::ios::trunc);
        if(!trace)
            return;
        const char magic[8] = {'M', 'C', 'P', 'D', 'R', 'Q', '1', '\n'};
        trace.write(magic, sizeof(magic));
        uint32_t version = 2;
        trace_value(version);
    }
    bool trace_enabled() const { return trace.is_open(); }
    SATSearchStats search_stats() const{
        SATSearchStats stats;
        stats.conflicts = ipasir_conflicts(s);
        stats.decisions = ipasir_decisions(s);
        stats.propagations = ipasir_propagations(s);
        stats.restarts = ipasir_restarts(s);
        return stats;
    }
    void set_clear_act(){
        clear_flag = true;
    }
    void clear_act(){
        if(clear_flag){
            this->add(-nv);
            this->add(0);
        }
        clear_flag = false;
    }
    void show_info(){};
};


class minisatSimp: public CNFSimplifier{
    void *s;
    Minisat::vec<Minisat::Lit> clause;
    Minisat::vec<Minisat::Lit> assumptions;
    vector<vector<int>> witness;
    bool canonical_variables;
    int external_nv;
    std::unordered_map<int, int> external_to_internal;
    vector<int> internal_to_external;

    void internal_var_enlarge_to(int v){
        while(((Minisat::SimpSolver *)s)->nVars() < v)
            ((Minisat::SimpSolver *)s)->newVar();
    }

    int map_var(int external_var){
        external_nv = max(external_nv, external_var);
        if(!canonical_variables){
            internal_var_enlarge_to(external_var);
            return external_var;
        }
        auto found = external_to_internal.find(external_var);
        if(found != external_to_internal.end())
            return found->second;
        int internal_var = static_cast<int>(external_to_internal.size()) + 1;
        internal_var_enlarge_to(internal_var);
        external_to_internal[external_var] = internal_var;
        if(internal_to_external.size() <= static_cast<size_t>(internal_var))
            internal_to_external.resize(internal_var + 1, 0);
        internal_to_external[internal_var] = external_var;
        return internal_var;
    }

    int map_lit(int external_lit){
        int internal_var = map_var(abs(external_lit));
        return external_lit < 0 ? -internal_var : internal_var;
    }

    int unmap_var(int internal_var) const{
        if(!canonical_variables)
            return internal_var;
        return internal_to_external.at(internal_var);
    }

    int unmap_lit(const Minisat::Lit &lit) const{
        int external_var = unmap_var(Minisat::var(lit) + 1);
        return Minisat::sign(lit) ? -external_var : external_var;
    }
public:
    explicit minisatSimp(const std::string &elim_order = "", int width_weight = 0){
        s = new Minisat::SimpSolver();
        ((Minisat::SimpSolver*)s)->random_seed = 0;
        std::string mode = elim_order;
        if(mode.empty()){
            if(const char *value = std::getenv("MC_PDR_MINISAT_ELIM_ORDER"))
                mode = value;
        }
        if(!mode.empty()){
            int order = mode == "low" ? 1 : mode == "high" ? 2
                : mode == "sum-low" ? 3 : mode == "sum-high" ? 4 : 0;
            ((Minisat::SimpSolver*)s)->setElimTieBreak(order);
        }
        ((Minisat::SimpSolver*)s)->elim_width_weight = std::max(width_weight, 0);
        if(const char *value = std::getenv("MC_PDR_MINISAT_GROW"))
            ((Minisat::SimpSolver*)s)->grow = std::atoi(value);
        if(const char *value = std::getenv("MC_PDR_MINISAT_CLAUSE_LIMIT"))
            ((Minisat::SimpSolver*)s)->clause_lim = std::atoi(value);
        if(const char *value = std::getenv("MC_PDR_MINISAT_ASYMM"))
            ((Minisat::SimpSolver*)s)->use_asymm = value[0] != '\0' && value[0] != '0';
        if(const char *value = std::getenv("MC_PDR_MINISAT_RCHECK"))
            ((Minisat::SimpSolver*)s)->use_rcheck = value[0] != '\0' && value[0] != '0';
        external_nv = 0;
        const char *canonical = std::getenv("MC_PDR_CANONICAL_MINISAT");
        canonical_variables = canonical != nullptr
            && canonical[0] != '\0' && canonical[0] != '0';
        internal_to_external.push_back(0);
    }
    ~minisatSimp(){ delete static_cast<Minisat::SimpSolver *>(s); }
    
    void var_enlarge_to(int v){
        external_nv = max(external_nv, v);
        if(!canonical_variables)
            internal_var_enlarge_to(v);
    }

    void add(int dimacs_lit){
        if(dimacs_lit == 0){
            // printf("add_cls: ");
            // for(int i = 0; i<clause.size(); ++i){
            //     int v = Minisat::var(clause[i]) + 1;
            //     int l = Minisat::sign(clause[i]) ? -v : v;
            //     printf("%d ", l);
            // }puts("");

            ((Minisat::SimpSolver *)s)->addClause(clause);
            clause.clear();

        }else{
            int internal_lit = map_lit(dimacs_lit);
            Minisat::Lit l = Minisat::mkLit(abs(internal_lit)-1, internal_lit<0);
            clause.push(l);
        }
    }
    void assume(int assumption_lit){
        int internal_lit = map_lit(assumption_lit);
        Minisat::Lit l = Minisat::mkLit(abs(internal_lit)-1, internal_lit<0);
        assumptions.clear();
    }
    int solve(){
        bool res = ((Minisat::SimpSolver *)s)->solve(assumptions);
        assumptions.clear();
        if(res)
            return 10;
        else
            return 20;
    }
    int failed(int lit){
        int internal_lit = map_lit(lit);
        Minisat::Lit l = Minisat::mkLit(abs(internal_lit)-1, internal_lit>0);
        if( ((Minisat::SimpSolver *)s)->conflict.has(l)){
            return 1;
        }else{
            return 0;
        }
    }
    int val(int lit){
        Minisat::Var var_idx = map_var(abs(lit)) - 1;
        Minisat::lbool lb = ((Minisat::SimpSolver *)s)->modelValue(var_idx);
        if(lb == Minisat::l_True){
            return abs(lit);
        }else if(lb == Minisat::l_False){
            return -abs(lit);
        }else{
            return 0;
        }
    }

    void set_frozen(int lit){
        int v = map_var(abs(lit));
        // cout<<"F"<<v<<endl;
        ((Minisat::SimpSolver *)s)->setFrozen(v-1, true);
    }

    void simplify(){

        // cout<<((Minisat::SimpSolver *)s)->nVars()<<endl;
        // cout<<((Minisat::SimpSolver *)s)->nClauses()<<endl;

        const char *eliminate_value = std::getenv("MC_PDR_MINISAT_ELIMINATE");
        bool eliminate = eliminate_value == nullptr
            || (eliminate_value[0] != '\0' && eliminate_value[0] != '0');
        if(eliminate)
            ((Minisat::SimpSolver *)s)->eliminate();
        
        // int max_var = 0;
        // cout<<((Minisat::SimpSolver *)s)->nVars()<<endl;
        // cout<<((Minisat::SimpSolver *)s)->nClauses()<<endl;
        
        simplified_cnf.clear();
        simplified_cnf.push_back(external_nv);
        simplified_cnf.push_back(-external_nv);
        simplified_cnf.push_back(0);
        for (Minisat::ClauseIterator c = ((Minisat::SimpSolver *)s)->clausesBegin(); 
            c != ((Minisat::SimpSolver *)s)->clausesEnd(); ++c) {
                const Minisat::Clause & cls = *c;
                for (int i = 0; i < cls.size(); ++i){
                    int l = unmap_lit(cls[i]);
                    // cout<<l<<" ";
                    simplified_cnf.push_back(l);
                }
                // cout<<endl;
                simplified_cnf.push_back(0);
            }
        for (Minisat::TrailIterator c = ((Minisat::SimpSolver *)s)->trailBegin(); 
            c != ((Minisat::SimpSolver *)s)->trailEnd(); ++c){
                int l = unmap_lit(*c);
                simplified_cnf.push_back(l);
                simplified_cnf.push_back(0);
                // cout<<l<<endl;
        }
        // exit(0);        
        // cout<<"simp max :";
        // cout<<max_var<<endl;
    }

    int num_vars() const{
        return canonical_variables ? external_nv : ((Minisat::SimpSolver *)s)->nVars();
    }

    int num_clauses() const{
        return ((Minisat::SimpSolver *)s)->nClauses();
    }

    CNFSimplificationStats simplification_stats() const{
        const Minisat::SimpSolver *solver =
            static_cast<const Minisat::SimpSolver *>(s);
        CNFSimplificationStats stats;
        stats.attempted_vars = solver->elim_attempted_vars;
        stats.eliminated_vars = solver->eliminated_vars;
        stats.rejected_growth = solver->elim_rejected_growth;
        stats.rejected_clause_limit = solver->elim_rejected_clause_limit;
        stats.removed_clauses = solver->elim_removed_clauses;
        stats.resolvents = solver->elim_resolvents;
        stats.resolvent_literals = solver->elim_resolvent_literals;
        stats.positive_occurrences = solver->elim_positive_occurrences;
        stats.negative_occurrences = solver->elim_negative_occurrences;
        stats.max_resolvent_size = solver->elim_max_resolvent_size;
        stats.merge_checks = solver->merges;
        return stats;
    }
    
    int max_var(){
        return canonical_variables ? external_nv : ((Minisat::SimpSolver *)s)->nVars();
    }
    void show_info(){};

};

class cadicalSimp: public CNFSimplifier{
    CCaDiCaL *solver;
    vector<int> frozen_variables;
    int external_nv = 0;
    int rounds = 3;
    bool simplified = false;

    static int collect_clause(void *state, const int *literals, int size){
        vector<int> *cnf = static_cast<vector<int> *>(state);
        cnf->insert(cnf->end(), literals, literals + size);
        cnf->push_back(0);
        return 1;
    }

public:
    cadicalSimp(): solver(ccadical_init()){
        ccadical_set_option(solver, "quiet", 1);
        if(const char *value = std::getenv("MC_PDR_CADICAL_PRE_ROUNDS"))
            rounds = std::max(0, std::atoi(value));
        if(const char *value = std::getenv("MC_PDR_CADICAL_ELIMPROD"))
            ccadical_set_option(solver, "elimprod", std::atoi(value));
        if(const char *value = std::getenv("MC_PDR_CADICAL_ELIMSUM"))
            ccadical_set_option(solver, "elimsum", std::atoi(value));
    }
    ~cadicalSimp(){ ccadical_release(solver); }

    void var_enlarge_to(int variable){ external_nv = std::max(external_nv, variable); }
    void add(int literal){
        external_nv = std::max(external_nv, abs(literal));
        ccadical_add(solver, literal);
    }
    void assume(int literal){ ccadical_assume(solver, literal); }
    int solve(){ return ccadical_solve(solver); }
    int failed(int literal){ return ccadical_failed(solver, literal); }
    int val(int literal){ return ccadical_val(solver, literal); }
    int max_var(){ return external_nv; }
    void set_frozen(int literal){
        int variable = abs(literal);
        external_nv = std::max(external_nv, variable);
        frozen_variables.push_back(variable);
    }
    void simplify(){
        if(external_nv > 0){
            ccadical_add(solver, external_nv);
            ccadical_add(solver, -external_nv);
            ccadical_add(solver, 0);
        }
        for(int variable : frozen_variables)
            ccadical_freeze(solver, variable);
        ccadical_simplify_rounds(solver, rounds);
        simplified_cnf.clear();
        simplified_cnf.push_back(external_nv);
        simplified_cnf.push_back(-external_nv);
        simplified_cnf.push_back(0);
        ccadical_traverse_clauses(solver, &simplified_cnf, collect_clause);
        simplified = true;
    }
    int num_vars() const{
        return simplified ? static_cast<int>(ccadical_active(solver)) : external_nv;
    }
    int num_clauses() const{
        return static_cast<int>(ccadical_irredundant(solver));
    }
    void show_info(){}
};

class minisatCore: public SATSolver{
    void *s;
    Minisat::vec<Minisat::Lit> clause;
    Minisat::vec<Minisat::Lit> assumptions;
    vector<vector<int>> witness;
    int nv;
    bool clear_flag = false;
public:
    vector<int> simplified_cnf;
    minisatCore(){
        s = new Minisat::Solver();
        nv = 0;
        clear_flag = false;
    }
    void show_info(){
        cout<<((Minisat::Solver *)s)->nVars()<<" ";
        cout<<((Minisat::Solver *)s)->nClauses()<<endl;
    }

     void var_enlarge_to(int v){
        // if(((Minisat::Solver *)s)->nVars() < v)
        //     cout<<((Minisat::Solver *)s)->nVars()<<" to "<<v<<endl;
        while(((Minisat::Solver *)s)->nVars() < v )
            ((Minisat::Solver *)s)->newVar();
    }
    void add(int dimacs_lit){
        if(dimacs_lit == 0){
            // printf("add_cls: ");
            // for(int i = 0; i<clause.size(); ++i){
            //     int v = Minisat::var(clause[i]) + 1;
            //     int l = Minisat::sign(clause[i]) ? -v : v;
            //     printf("%d ", l);
            // }puts("");

            ((Minisat::Solver *)s)->addClause(clause);
            clause.clear();

        }else{
            nv = max(nv, abs(dimacs_lit));
            Minisat::Var var_idx = abs(dimacs_lit) - 1;
            var_enlarge_to(nv);
            Minisat::Lit l = Minisat::mkLit(var_idx, dimacs_lit<0);
            clause.push(l);
        }
    }
    void assume(int assumption_lit){
        Minisat::Var var_idx = abs(assumption_lit) - 1;
        nv = max(nv, abs(assumption_lit));
        var_enlarge_to(nv);
        Minisat::Lit l = Minisat::mkLit(var_idx, assumption_lit<0);
        assumptions.push(l);
    }
    int solve(){
        bool res = ((Minisat::Solver *)s)->solve(assumptions);
        assumptions.clear();
        if(res)
            return 10;
        else
            return 20;
    }
    int failed(int lit){
        Minisat::Var var_idx = abs(lit) - 1;
        Minisat::Lit l = Minisat::mkLit(var_idx, lit>0);

        if( ((Minisat::Solver *)s)->conflict.has(l)){
            return 1;
        }else{
            return 0;
        }
    }
    int val(int lit){
        Minisat::Var var_idx = abs(lit) - 1;
        Minisat::lbool lb = ((Minisat::Solver *)s)->modelValue(var_idx);
        if(lb == Minisat::l_True){
            return abs(lit);
        }else if(lb == Minisat::l_False){
            return -abs(lit);
        }else{
            return 0;
        }
    }

    int max_var(){
        // cout << "max_var = "<<((Minisat::Solver *)s)->nVars()<<endl;
        assert(((Minisat::Solver *)s)->nVars() == nv);
        return nv;
    }

    void set_clear_act(){
        clear_flag = true;
    }
    void clear_act(){
        // cout<<"clear act flag "<<clear_flag<<endl;
        if(clear_flag){
            this->add(-nv);
            this->add(0);
        }
        clear_flag = false;
    }
    void show_clauses(){
        cout<<"show_lift clauses begin"<<endl;
    
        for (Minisat::ClauseIterator c = ((Minisat::SimpSolver *)s)->clausesBegin(); 
            c != ((Minisat::SimpSolver *)s)->clausesEnd(); ++c) {
                const Minisat::Clause & cls = *c;
                for (int i = 0; i < cls.size(); ++i){
                    int v = Minisat::var(cls[i]) + 1;
                    int l = (Minisat::sign(cls[i])? -v : v);
                    cout<<l<<" ";
                }
                cout<<endl;
            }
        for (Minisat::TrailIterator c = ((Minisat::SimpSolver *)s)->trailBegin(); 
            c != ((Minisat::SimpSolver *)s)->trailEnd(); ++c){
                int v = Minisat::var(*c) + 1;
                int l = (Minisat::sign(*c)? -v : v);
                cout<<l<<endl;
        }
        
        cout<<"show_lift clauses end"<<endl;
    }
};
