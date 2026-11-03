#include "ipasir.h"
#include "cadical/src/ccadical.h"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <random>
#include <string>
#include <unordered_map>
#include <vector>

namespace {

template<typename T>
bool read_value(std::istream &input, T &value){
    return static_cast<bool>(input.read(reinterpret_cast<char *>(&value), sizeof(value)));
}

class ReplaySolver{
    void *solver;
    int next_internal = 0;
    std::unordered_map<int, int> mapping;

public:
    ReplaySolver(): solver(ipasir_init()) {
        ccadical_set_option(static_cast<CCaDiCaL *>(solver), "reverse", 0);
    }
    ~ReplaySolver(){ ipasir_release(solver); }

    int map_var(int external){
        std::unordered_map<int, int>::const_iterator found = mapping.find(external);
        if(found != mapping.end())
            return found->second;
        int internal = ++next_internal;
        mapping[external] = internal;
        return internal;
    }

    int map_lit(int literal){
        if(literal == 0)
            return 0;
        int internal = map_var(literal < 0 ? -literal : literal);
        return literal < 0 ? -internal : internal;
    }

    void order(const std::vector<int> &variables){
        for(size_t i = 0; i < variables.size(); ++i)
            if(variables[i] > 0)
                map_var(variables[i]);
    }

    void add(int literal){ ipasir_add(solver, map_lit(literal)); }
    void assume(int literal){ ipasir_assume(solver, map_lit(literal)); }
    int solve(){ return ipasir_solve(solver); }
    int failed(int literal){ return ipasir_failed(solver, map_lit(literal)); }
    int val(int literal){
        int internal_value = ipasir_val(solver, map_lit(literal));
        if(internal_value > 0)
            return literal < 0 ? -literal : literal;
        if(internal_value < 0)
            return literal < 0 ? literal : -literal;
        return 0;
    }
    int64_t conflicts() const { return ipasir_conflicts(solver); }
    int64_t decisions() const { return ipasir_decisions(solver); }
    int64_t propagations() const { return ipasir_propagations(solver); }
    int64_t restarts() const { return ipasir_restarts(solver); }
};

std::string basename(const std::string &path){
    size_t slash = path.find_last_of('/');
    return slash == std::string::npos ? path : path.substr(slash + 1);
}

void usage(const char *program){
    std::cerr << "usage: " << program
              << " [--header] --mode recorded|numeric|reverse|first|encounter|random-SEED TRACE\n";
}

}

int main(int argc, char **argv){
    std::string mode = "recorded";
    std::string path;
    bool header = false;
    for(int i = 1; i < argc; ++i){
        std::string argument = argv[i];
        if(argument == "--header")
            header = true;
        else if(argument == "--mode" && i + 1 < argc)
            mode = argv[++i];
        else if(path.empty())
            path = argument;
        else{
            usage(argv[0]);
            return 2;
        }
    }
    bool random_mode = mode.compare(0, 7, "random-") == 0;
    uint64_t random_seed = 0;
    if(random_mode){
        try{
            size_t consumed = 0;
            random_seed = std::stoull(mode.substr(7), &consumed);
            if(consumed != mode.size() - 7)
                random_mode = false;
        }catch(const std::exception &){
            random_mode = false;
        }
    }
    if(path.empty() || (mode != "recorded" && mode != "numeric" &&
                        mode != "reverse" && mode != "first" &&
                        mode != "encounter" && !random_mode)){
        usage(argv[0]);
        return 2;
    }

    std::ifstream input(path.c_str(), std::ios::in | std::ios::binary);
    char magic[8];
    uint32_t version = 0;
    if(!input.read(magic, sizeof(magic)) ||
       std::string(magic, sizeof(magic)) != "MCPDRQ1\n" ||
       !read_value(input, version) || (version != 1 && version != 2)){
        std::cerr << "invalid trace header: " << path << "\n";
        return 2;
    }

    ReplaySolver solver;
    bool complete = false;
    bool malformed = false;
    bool truncated = false;
    uint64_t queries = 0;
    uint64_t mismatches = 0;
    uint64_t recorded_ns = 0;
    uint64_t replay_ns = 0;
    int64_t recorded_conflicts = 0, recorded_decisions = 0;
    int64_t recorded_propagations = 0, recorded_restarts = 0;
    int64_t replay_conflicts = 0, replay_decisions = 0;
    int64_t replay_propagations = 0, replay_restarts = 0;
    uint64_t observations = 0, observation_mismatches = 0;
    std::mt19937_64 random(random_seed);

    char operation = 0;
    while(input.read(&operation, 1)){
        if(operation == 'E'){
            complete = true;
            break;
        }
        if(operation == 'O'){
            uint32_t count = 0;
            if(!read_value(input, count)){
                truncated = true;
                break;
            }
            std::vector<int> variables(count);
            for(uint32_t i = 0; i < count; ++i){
                int32_t variable = 0;
                if(!read_value(input, variable)){
                    truncated = true;
                    break;
                }
                variables[i] = variable;
            }
            if(malformed)
                break;
            if(mode == "numeric")
                std::sort(variables.begin(), variables.end());
            else if(mode == "reverse")
                std::reverse(variables.begin(), variables.end());
            else if(random_mode)
                std::shuffle(variables.begin(), variables.end(), random);
            if(mode != "encounter" && mode != "first")
                solver.order(variables);
            continue;
        }
        if(operation == 'A' || operation == 'U'){
            int32_t literal = 0;
            if(!read_value(input, literal)){
                truncated = true;
                break;
            }
            if(operation == 'A')
                solver.add(literal);
            else
                solver.assume(literal);
            continue;
        }
        if(version >= 2 && (operation == 'V' || operation == 'F')){
            int32_t literal = 0, expected = 0;
            if(!read_value(input, literal) || !read_value(input, expected)){
                truncated = true;
                break;
            }
            int actual = operation == 'V' ? solver.val(literal) : solver.failed(literal);
            ++observations;
            observation_mismatches += actual != expected;
            continue;
        }
        if(operation == 'S'){
            int32_t expected = 0;
            uint64_t elapsed_ns = 0;
            int64_t conflicts = 0, decisions = 0, propagations = 0, restarts = 0;
            if(!read_value(input, expected) || !read_value(input, elapsed_ns) ||
               !read_value(input, conflicts) || !read_value(input, decisions) ||
               !read_value(input, propagations) || !read_value(input, restarts)){
                truncated = true;
                break;
            }
            // A live timeout terminates the active IPASIR solve with UNKNOWN.
            // It has no reproducible SAT/UNSAT endpoint and is not part of the
            // completed frozen-query prefix.
            if(expected == 0)
                break;
            int64_t before_conflicts = solver.conflicts();
            int64_t before_decisions = solver.decisions();
            int64_t before_propagations = solver.propagations();
            int64_t before_restarts = solver.restarts();
            std::chrono::steady_clock::time_point started = std::chrono::steady_clock::now();
            int actual = solver.solve();
            replay_ns += static_cast<uint64_t>(
                std::chrono::duration_cast<std::chrono::nanoseconds>(
                    std::chrono::steady_clock::now() - started).count());
            ++queries;
            mismatches += actual != expected;
            recorded_ns += elapsed_ns;
            recorded_conflicts += conflicts;
            recorded_decisions += decisions;
            recorded_propagations += propagations;
            recorded_restarts += restarts;
            replay_conflicts += solver.conflicts() - before_conflicts;
            replay_decisions += solver.decisions() - before_decisions;
            replay_propagations += solver.propagations() - before_propagations;
            replay_restarts += solver.restarts() - before_restarts;
            continue;
        }
        malformed = true;
        break;
    }

    if(header)
        std::cout << "trace\tmode\tcomplete\tmalformed\tqueries\tmismatches"
                  << "\trecorded_seconds\treplay_seconds"
                  << "\trecorded_conflicts\treplay_conflicts"
                  << "\trecorded_decisions\treplay_decisions"
                  << "\trecorded_propagations\treplay_propagations"
                  << "\trecorded_restarts\treplay_restarts"
                  << "\tobservations\tobservation_mismatches\n";
    std::cout << basename(path) << '\t' << mode << '\t' << (complete ? 1 : 0)
              << '\t' << (malformed ? 1 : 0) << '\t' << queries << '\t' << mismatches
              << '\t' << std::fixed << std::setprecision(9)
              << static_cast<double>(recorded_ns) / 1e9
              << '\t' << static_cast<double>(replay_ns) / 1e9
              << '\t' << recorded_conflicts << '\t' << replay_conflicts
              << '\t' << recorded_decisions << '\t' << replay_decisions
              << '\t' << recorded_propagations << '\t' << replay_propagations
              << '\t' << recorded_restarts << '\t' << replay_restarts
              << '\t' << observations << '\t' << observation_mismatches << '\n';
    (void) truncated;
    return malformed || mismatches ? 1 : 0;
}
