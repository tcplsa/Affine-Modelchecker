#include "PDR.hpp"
#include <queue>
#include <cstdlib>
#include <iomanip>
#include <boost/lockfree/spsc_queue.hpp>

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

bool env_is(const char *name, const char *expected){
    const char *value = std::getenv(name);
    if(value == nullptr)
        return false;
    return string(value) == expected;
}

SATSolver *new_pdr_solver(){
    if(env_is("MC_PDR_SOLVER", "minisat"))
        return new minisatCore();
    return new CaDiCaL();
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

boost::lockfree::spsc_queue<share_Cube, boost::lockfree::capacity<500000>> cube_producer[2][8]; 
queue<share_Cube> cube_register[2][9999];

Frame::Frame(){
    solver = new_pdr_solver();
    cubes.clear();
}

PDR::PDR(Aiger *aiger, int Thread_index, bool acc, bool pr, bool ao):
    Aiger(*aiger),
    thread_index(Thread_index),
    main_thread_index(-1),
    use_acc(acc),
    use_pr(pr),
    use_plusone_count(ao){
    cfg_use_xag = env_bool("MC_PDR_XAG", aiger->use_xag_for_pdr);
    if(cfg_use_xag)
        use_xag_for_pdr();
    cfg_use_heuristic = env_bool("MC_PDR_HEURISTIC", false);
    cfg_use_punishment = env_bool("MC_PDR_PUNISHMENT", use_punishment);
    cfg_use_earliest_strengthened_frame = env_bool("MC_PDR_EARLIEST", use_earliest_strengthened_frame);
    cfg_assumption_allsort = env_bool("MC_PDR_ASSUMPTION_ALLSORT", assumption_allsort);
    cfg_stats = env_bool("MC_PDR_STATS", false);
    cfg_option_ctg_tries = env_int("MC_PDR_CTG_TRIES", option_ctg_tries);
    cfg_option_ctg_max_depth = env_int("MC_PDR_CTG_DEPTH", option_ctg_max_depth);
    cfg_option_max_joins = env_int("MC_PDR_MAX_JOINS", option_max_joins);
    use_pr = env_bool("MC_PDR_PR", pr);
    use_acc = env_bool("MC_PDR_ACC", acc);
    start_time = std::chrono::steady_clock::now();
    nPush = nUnpush = nCore = nCorelen = nCube = nCubelen = nProp = nkCore = nkobl = nobl = 0;
    first_incremental_check = 1;
    satelite_unsat = 0;
    restart_depth = 5;
    if(Thread_index >= 0){
        if(Thread_index == 1)
            main_thread_index = 0;
        else if(Thread_index == 4)
            main_thread_index = 1;
        else
            main_thread_index = -1;
    }
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
    for(int l : s->latches)
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
    for(int l : s->latches)
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

void PDR::print_stats(int result){
    if(!cfg_stats)
        return;

    int saved_precision = cout.precision();
    ios::fmtflags saved_flags = cout.flags();
    cout << fixed << setprecision(6);
    cout << "c PDR_STATS thread=" << thread_index
         << " result=" << (result == 20 ? "safe" : (result == 10 ? "unsafe" : "unknown"))
         << " depth=" << depth()
         << " runtime=" << get_runtime() << endl;
    cout << "c PDR_CONFIG heuristic=" << cfg_use_heuristic
         << " xag=" << cfg_use_xag
         << " ctg_depth=" << cfg_option_ctg_max_depth
         << " ctg_tries=" << cfg_option_ctg_tries
         << " punishment=" << cfg_use_punishment
         << " pr=" << use_pr
         << " earliest=" << cfg_use_earliest_strengthened_frame
         << " assumption_allsort=" << cfg_assumption_allsort << endl;
    cout << "c XAG_STATS inputs=" << num_inputs
         << " latches=" << num_latches
         << " ands=" << ands.size()
         << " xors=" << xors.size()
         << " ors=" << ors.size() << endl;
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
         << " abort_join=" << nAbortJoin
         << " abort_mic=" << nAbortMic << endl;
    auto avg = [](double total, int count) -> double {
        return count > 0 ? total / count : 0.0;
    };
    cout << "c PDR_TIMES block=" << tBlock
         << " inductive=" << tInductive << " avg_inductive=" << avg(tInductive, nInductive)
         << " generalize=" << tGeneralize << " avg_generalize=" << avg(tGeneralize, nGeneralize)
         << " ctg=" << tCTG
         << " propagate=" << tPropagate
         << " extract=" << tExtract << " avg_extract=" << avg(tExtract, nExtract)
         << " pre=" << tPre << " avg_pre=" << avg(tPre, nPre) << endl;
    cout.flags(saved_flags);
    cout.precision(saved_precision);
}

void PDR::log_witness(){
    State* p = cex_state_idx;
    set<State *> ss;
    while(p != nullptr){
        cex_states.push_back(p);
        ss.insert(p);
        p = p->next;
    }
    for(auto q : states){
        if(ss.find(q) == ss.end()){
            delete q;
        }
    }
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
    aig2xag::ConvertResult converted = aig2xag::convert(*this);
    const aig2xag::XagCircuit &xag = converted.xag;

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

    if(aig_veb){
        cout << "c aig2xag for PDR: ands " << converted.stats.original_ands
             << " -> ands " << ands.size()
             << ", xors " << xors.size()
             << ", ors " << ors.size()
             << ", removed " << converted.stats.removed_ands << endl;
    }
}

void PDR::encode_gate(SATSolver *s, const And &g, int gate_type){
    if(gate_type == 0){
        s->add(-g.o); s->add(g.i1);  s->add(0);
        s->add(-g.o); s->add(g.i2);  s->add(0);
        s->add(g.o);  s->add(-g.i1); s->add(-g.i2); s->add(0);
    }else if(gate_type == 1){
        s->add(-g.o); s->add(g.i1);  s->add(g.i2);  s->add(0);
        s->add(-g.o); s->add(-g.i1); s->add(-g.i2); s->add(0);
        s->add(g.o);  s->add(-g.i1); s->add(g.i2);  s->add(0);
        s->add(g.o);  s->add(g.i1);  s->add(-g.i2); s->add(0);
    }else{
        s->add(-g.o); s->add(g.i1);  s->add(g.i2); s->add(0);
        s->add(g.o);  s->add(-g.i1); s->add(0);
        s->add(g.o);  s->add(-g.i2); s->add(0);
    }
}

void PDR::encode_gate_cone(SATSolver *s, set<int> &lit_set){
    vector<pair<int, And> > gates;
    for(size_t i=0; i<ands.size(); ++i) gates.push_back(make_pair(0, ands[i]));
    for(size_t i=0; i<xors.size(); ++i) gates.push_back(make_pair(1, xors[i]));
    for(size_t i=0; i<ors.size(); ++i)  gates.push_back(make_pair(2, ors[i]));
    sort(gates.begin(), gates.end(), [](const pair<int, And> &a, const pair<int, And> &b){ return a.second.o < b.second.o; });

    for(auto it = gates.rbegin(); it != gates.rend(); ++it){
        const And &g = it->second;
        assert(g.o > 0);
        if(lit_set.find(g.o) == lit_set.end())
            continue;
        lit_set.insert(abs(g.i1));
        lit_set.insert(abs(g.i2));
        encode_gate(s, g, it->first);
    }
}

void PDR::encode_gate_cone_with_prime(SATSolver *s, set<int> &lit_set, set<int> &prime_lit_set){
    vector<pair<int, And> > gates;
    for(size_t i=0; i<ands.size(); ++i) gates.push_back(make_pair(0, ands[i]));
    for(size_t i=0; i<xors.size(); ++i) gates.push_back(make_pair(1, xors[i]));
    for(size_t i=0; i<ors.size(); ++i)  gates.push_back(make_pair(2, ors[i]));
    sort(gates.begin(), gates.end(), [](const pair<int, And> &a, const pair<int, And> &b){ return a.second.o < b.second.o; });

    for(auto it = gates.rbegin(); it != gates.rend(); ++it){
        const And &g = it->second;
        assert(g.o > 0);
        if(lit_set.find(g.o) != lit_set.end()){
            lit_set.insert(abs(g.i1));
            lit_set.insert(abs(g.i2));
            encode_gate(s, g, it->first);

            if(prime_lit_set.find(g.o) != prime_lit_set.end()){
                And pg(prime_lit(g.o), prime_lit(g.i1), prime_lit(g.i2));
                prime_lit_set.insert(abs(g.i1));
                prime_lit_set.insert(abs(g.i2));
                encode_gate(s, pg, it->first);
            }
        }
    }
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
    initialize_heuristic();
    //show_uaiger();

    nQuery = nInductive = nCTI = nCTG = nmic = nCoreReduced = nAbortJoin = nAbortMic = 0;
    nBlock = nGeneralize = nExtract = nPre = 0;
    tBlock = tInductive = tGeneralize = tCTG = tPropagate = tExtract = tPre = 0.0;
    //cout<<"c PDR constructed from aiger file [Finished] \n";
}

void PDR::new_frame(){
    int last = frames.size();
    frames.push_back(Frame());
    encode_translation(frames[last].solver);
    // Goal of frame-k is to find a pre-condition or prove clause c inductive to k-1.
    for(int l : constraints_prime){
        frames[last].solver->add(l);
        frames[last].solver->add(0);
    }
}

int add_ct = 0;
void PDR::add_cube(Cube &cube, int k, bool to_all, bool ispropagate, int prtimes){
    if(!ispropagate)
        earliest_strengthened_frame =min(earliest_strengthened_frame,k);
    sort(cube.begin(), cube.end(), Lit_CMP());
    pair<set<Cube, Cube_CMP>::iterator, bool> rv = frames[k].cubes.insert(cube);
    if(!rv.second) return;

    if(share_memory and main_thread_index < 0) { 
        if(k>9990) k=9990;
        cube_producer[0][thread_index].push(share_Cube(to_all, k, cube));
        cube_producer[1][thread_index].push(share_Cube(to_all, k, cube));
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
}

bool PDR::is_init(vector<int> &latches){ //to be optimized
    if(init == nullptr){
        init = new_pdr_solver();
        encode_init_condition(init);
    }
    for(int l : latches)
        init->assume(l);
    int res = init->solve();
    assert(res != 0);
    return (res == SAT);
}

// check ~latches inductive by Fi /\ -s /\ T /\ s'
// Fi /\ -latches /\ [constraints /\ -bad /\ T] /\ constraints' /\ latches'
int core_ct = 0;
bool PDR::is_inductive(SATSolver *solver, const Cube &latches, bool gen_core, bool reverse_assumption){
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

    int status = solver->solve();
    ++nQuery;
    ++nInductive;
    assert(status != 0);
    bool res = (status == UNSAT);

    if(res & gen_core){
        core.clear();
        for(int i : latches){
            if(solver->failed(prime_lit(i)))
                core.push_back(i);
        }
        if(is_init(core)){
            core = latches;
        }
    }
    solver->set_clear_act();
    return res;
}

void PDR::encode_init_condition(SATSolver *s){
    s->add(-1); s->add(0);
    for(int l : init_state){
        s->add(l); s->add(0);
    }
    if(constraints.size() >= 0){
        for(int l : constraints){
            s->add(l); s->add(0);}

        set<int> lit_set;
        for(int l : constraints)
            lit_set.insert(abs(l));

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

// check ~latches inductive by Fi /\ -s /\ T /\ s'
// Fi /\ latches /\ [constraints /\ -bad /\ T] /\ constraints' /\ latches'
// lift a pre-state by Fi /\ pre /\ T /\ -s' (assert UNSAT)
// Fi /\ inputs /\ latches /\ [constraints /\ -bad /\ T] /\ inputs' /\ -(constraints' /\ latches')
// translation encoding: [constraints /\ -bad /\ T]
void PDR::encode_translation(SATSolver *s, bool cons){
    if(satelite == nullptr){
        satelite = new minisatSimp();
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
        prime_lit_set.insert(abs(bad));
        for(int l : constraints)
            prime_lit_set.insert(abs(l));

        set<int> lit_set(prime_lit_set.begin(), prime_lit_set.end());
        for(int l : nexts)
            lit_set.insert(abs(l));

        satelite->add(-1); satelite->add(0);    // literal 1 is const 'T'
        satelite->add(-bad); satelite->add(0);  // -bad must hold !
        if(cons){
            for(int l : constraints){
                if(l == bad) satelite_unsat = true;
                satelite->add(l);satelite->add(0);
            }
        }
        //for(int l : constraints_prime){satelite->add(l); satelite->add(0);}
        for(int i=0; i<num_latches; ++i){
            int l = 1 + num_inputs + i + 1;
            int pl = prime_lit(l);
            int next = nexts[i];
            satelite->add(-pl);satelite->add(next); satelite->add(0);
            satelite->add(-next); satelite->add(pl); satelite->add(0);
        }

        encode_gate_cone_with_prime(satelite, lit_set, prime_lit_set);
        satelite->simplify();
        // for(int l : satelite->simplified_cnf){
        //     cout << l << " ";
        //     if(l == 0){
        //         cout << endl;
        //     }
        // }
    }

    for(int l : satelite->simplified_cnf){
         s->add(l);
    }
    if(satelite_unsat) {s->add(1);s->add(0);}
    if(aig_veb > 2)
        cout<<"c add_cls finish load translation"<<endl;
}

void PDR::encode_lift(SATSolver *s){
    if(satelite2 == nullptr){
        satelite2 = new minisatSimp();
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
        prime_lit_set.insert(abs(bad));
        for(int l : constraints)
            prime_lit_set.insert(abs(l));

        set<int> lit_set(prime_lit_set.begin(), prime_lit_set.end());
        for(int l : nexts)
            lit_set.insert(abs(l));

        satelite2->add(-1); satelite2->add(0);    // literal 1 is const 'T'
        satelite2->add(-bad); satelite2->add(0);  // -bad must hold !

        for(int i=0; i<num_latches; ++i){
            int l = 1 + num_inputs + i + 1;
            int pl = prime_lit(l);
            int next = nexts[i];
            satelite2->add(-pl);satelite2->add(next); satelite2->add(0);
            satelite2->add(-next); satelite2->add(pl); satelite2->add(0);
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
        satelite2->simplify();
    }

    for(int l : satelite2->simplified_cnf){
         s->add(l);
    }
}

// Lifts the pre-state on a given frame
// If SAT?[Fk /\ -succ /\ T /\ succ'] return SAT and extract a pre-state pre \in [Fk /\ -succ]
// Then call SAT?[pre /\ T /\ -succ']
// pre must meet constraints.
void PDR::extract_state_from_sat(SATSolver *sat, State *s, State *succ, int findex){
    ScopedTimer timer(&tExtract);
    ++nExtract;
    s->clear();
    if(lift == nullptr){
        lift = new_pdr_solver();
        encode_lift(lift);
    }

    lift->clear_act();
    vector<int> assumptions, latches;
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
        }
        else if (pipt < 0){
            pipt = -(-pipt-distance);
            assumptions.push_back(pipt);
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
    if(succ == nullptr)
        lift->add(-bad_prime);
    else{
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
    int res = lift->solve();
    ++nQuery;

    assert(res == UNSAT);

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

    s->next = succ;
    lift->set_clear_act();
}

// solving SAT?[ Fk /\ T /\ -Bad' ]
bool PDR::get_pre_of_bad(State *s){
    ScopedTimer timer(&tPre);
    ++nPre;
    s->clear();
    int Fk = depth();
    frames[Fk].solver->assume(bad_prime);
    int res = frames[Fk].solver->solve();
    ++nQuery;
    if(res == SAT){
        State *bad_state = new State();
        for(int i=0; i<num_inputs; ++i){
            int pipt = (frames[Fk].solver)->val(primed_first_dimacs + i);
            if(pipt > 0)
                bad_state->inputs.push_back(pipt-(primed_first_dimacs-unprimed_first_dimacs));
            else if(pipt < 0)
                bad_state->inputs.push_back(pipt+(primed_first_dimacs-unprimed_first_dimacs));
        }
        for(int i=0; i<num_latches; ++i){
            int l = (frames[Fk].solver)->val(primed_first_dimacs + num_inputs + i);
            if(l > 0)
                bad_state->latches.push_back(l-(primed_first_dimacs-unprimed_first_dimacs));
            else if(l < 0)
                bad_state->latches.push_back(l+(primed_first_dimacs-unprimed_first_dimacs));
        }
        extract_state_from_sat(frames[Fk].solver, s, nullptr, Fk);
        s->next = bad_state;
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
        if(RESULT!=0) return RESULT;
        Obligation obl = *obligation_queue.begin();

        if(output_stats_for_recblock){
            cout << "\nRemaining " << obligation_queue.size() << " Obligation\n";
            cout << "Handling Frames[" << obl.frame_k << "]'s " << "Obligation, depth = " << obl.depth << " , stamp = " << ((obl.state)->index);
            show_state(obl.state);
        }
        // check SAT?[Fk /\ -s /\ T /\ s']
        SATSolver * sat = frames[obl.frame_k].solver;
        if(is_inductive(sat, obl.state->latches, true)){
            if(output_stats_for_recblock){
                cout << "the obligation is already fulfilled, and cube is lifted to ";
                show_litvec(core);
            }
            // latches is inductive to Fk
            obligation_queue.erase(obligation_queue.begin());
            Cube tmp_core = core;
            generalize(tmp_core, obl.frame_k);
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
                if(!is_inductive(frames[k].solver, tmp_core, false)){
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
            add_cube(tmp_core, k, true, false, k - obl.frame_k + (tmp_core.size() < core.size()));
            if(k <= depth() and pushpo)
               obligation_queue.insert(Obligation(obl.state, k, obl.depth, thread_index));
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
                s->next = obl.state;
                cex_state_idx = s;
                find_cex = true;
                log_witness();
                return false;
            }else{
                extract_state_from_sat(sat, s, obl.state, obl.frame_k);
                obligation_queue.insert(Obligation(s, obl.frame_k - 1, obl.depth + 1, thread_index));
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
            if(is_inductive(frames[i].solver, *ci, true)){
                ++cprop;
                ++nProp;
                ++nPush;
                // should add to frame k+1
                if(core.size() < ci->size())
                    add_cube(core, i+1, true, true, 1);
                else
                    add_cube(core, i+1, false, true, 0);
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
            std::lock_guard<std::mutex> lock(result_mutex);
            if(RESULT != 0) return true;
            RESULT = 20;
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
            if(output_certificate){
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
    if(cfg_use_heuristic && thread_index <= 1)
        stable_sort(cube.begin(), cube.end(), *heuristic_lit_cmp);
    else
        random_shuffle(cube.begin(), cube.end());

    Cube tmp_cube = cube;
    for(int l : tmp_cube){
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
        if(CTG_down(cand, k, depth, required)){
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
        if(is_init(cube))
            return false;
        // check inductive;
        SATSolver *sat = frames[k].solver;
        if(is_inductive(sat, cube, true)){
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
            State *s = new State();
            State *succ = new State(cube, Cube());
            extract_state_from_sat(sat, s, succ, k);
            int breaked = false;
            if(output_stats_for_ctg){
                cout << "The new cube fails induction, find ctg ";
                show_litvec(s->latches);
            }
            // CTG
            if(ctg_ct < cfg_option_ctg_tries && k > 1 && !is_init(s->latches)
                && is_inductive(frames[k-1].solver, s->latches, true)){
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
                    if(!is_inductive(frames[i].solver, ctg, false))
                        break;
                }
                int Size =  ctg.size();
                mic(ctg, i-1, rec_depth+1);
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
            delete s, succ;
            if(breaked) return false;
        }
    }
}

void PDR::generalize(Cube &cube, int k){
    ScopedTimer timer(&tGeneralize);
    ++nGeneralize;
    mic(cube, k, 1);
}

void PDR::clear_po(){
    for(Obligation o : obligation_queue){
        delete o.state;
    }
    obligation_queue.clear();
}

bool PDR::check_BMC0(){
    assert(frames.size() == 0);
    // push F0 (BMC0 SAT check skipped)
    new_frame();
    encode_init_condition(frames[0].solver);
    return true;
}

bool PDR::check_BMC1(){
    assert(frames.size() == 1);
    // push F1 (BMC1 SAT check skipped)
    new_frame();
    return true;
}

int PDR::check(){
    initialize();

    if(!check_BMC0()) {
        std::lock_guard<std::mutex> lock(result_mutex);
        if(RESULT == 0){
            RESULT = 10;
            show_witness();
        }
        return 10;
    }
    if(!check_BMC1()) {
        std::lock_guard<std::mutex> lock(result_mutex);
        if(RESULT == 0){
            RESULT = 10;
            show_witness();
        }
        return 10;
    }

    // main loop of IC3, start from depth = 1.
    // Fk need to hold -Bad all the time
    new_frame();
    assert(depth() == 1);
    top_frame_cannot_reach_bad = true;
    earliest_strengthened_frame = depth();
    int result = 10;
    int ct = 0;
    while(true){
        if(RESULT!=0) return 0;
        if(restart and depth() > restart_depth){
            for(auto f : frames){
                if(f.solver != nullptr)
                    delete f.solver;
            }
            frames.clear();  
            assert(frames.size() == 0); 
            new_frame();
            encode_init_condition(frames[0].solver);
            new_frame();
            new_frame();
            assert(depth() == 1);
            top_frame_cannot_reach_bad = true;
            earliest_strengthened_frame = depth();
            restart_heuristic();
        }
        if(share_memory and main_thread_index >= 0){
            while(!cube_register[main_thread_index][depth()].empty()){
                if(RESULT!=0) return RESULT;
                share_Cube c = cube_register[main_thread_index][depth()].front();
                cube_register[main_thread_index][depth()].pop();
                Cube dequeue_cube = c.share_cube;
                pair<set<Cube, Cube_CMP>::iterator, bool> rv = frames[depth()].cubes.insert(dequeue_cube);
                if(!rv.second) continue;
                if(c.toall){
                    for(int index=1; index<depth(); index++){
                        for(int l : dequeue_cube)
                            frames[index].solver->add(-l);
                        frames[index].solver->add(0);
                    }
                }
                for(int l : c.share_cube)
                    frames[depth()].solver->add(-l);
                frames[depth()].solver->add(0);
            }
            for(int thread=0; thread<=3; thread++){
                while(!cube_producer[main_thread_index][thread].empty()){
                    if(RESULT!=0) return RESULT;
                    share_Cube c;
                    cube_producer[main_thread_index][thread].pop(c);
                    if(c.frame > depth()) {cube_register[main_thread_index][c.frame].push(c); continue;}
                    Cube dequeue_cube = c.share_cube;
                    pair<set<Cube, Cube_CMP>::iterator, bool> rv = frames[c.frame].cubes.insert(dequeue_cube);
                    if(!rv.second) continue;
                    cout << "thread" + to_string(thread) + " dequeue into " + to_string(1) + " " + return_litvec(dequeue_cube) +"\n";
                    if(c.toall){
                        for(int index=1; index<c.frame; index++){
                            for(int l : dequeue_cube)
                                frames[index].solver->add(-l);
                            frames[index].solver->add(0);
                        }
                    }
                    for(int l : c.share_cube)
                        frames[c.frame].solver->add(-l);
                    frames[c.frame].solver->add(0);
                }
            }
        }

        // get states which are one step to bad
        State *s = new State();
        bool flag = get_pre_of_bad(s);
        if(flag){
            ++nCTI;
            obligation_queue.clear();
            obligation_queue.insert(Obligation(s, depth()-1, 1, thread_index));
            top_frame_cannot_reach_bad = false;
            if(!rec_block_cube()){
                // find counter-example
                std::lock_guard<std::mutex> lock(result_mutex);
                result = 10;
                if(RESULT==0) {
                    RESULT = 10;
                    show_witness();
                }
                break;
            }else{
                for(State *p : states) delete p;
            }
        }
        else{
            assert(obligation_queue.size() == 0);
            if(output_stats_for_recblock) cout << "CTI not found\n";
            if(propagate()){
                // find invariants
                result = 20;
                RESULT = 20;
                break;
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
            if(moreinfo_for_pdr) cout << "pdr" + to_string(thread_index) + "_step = " +  to_string(earliest_strengthened_frame) + "\n";
        }
    }
    int d = depth();
    if(moreinfo_for_pdr) cout <<  "depth" + to_string(thread_index) + " = " + to_string(d) + "\n";
    print_stats(result);

    for(auto f : frames){
        if(f.solver != nullptr)
            delete f.solver;
    }
    frames.clear();

    if(output_stats_for_cpo){
        cout << "nPush: " << nPush << endl;
        cout << "nUnpush: " << nUnpush << endl;
        cout << "nProp: " << nProp << endl;
        if(nCore) 
            cout << "Avg core lens: " << float(nCorelen)/nCore << endl << "keycore rate: " <<  float(nkCore)/nCore << endl ; 
        else 
            cout << "Avg core lens: 0\n" << "keycore rate: 0\n";
    }
    return result;
}
