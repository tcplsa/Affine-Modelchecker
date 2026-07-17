#include "PDR.hpp"
#include "BMC.hpp"
#include "pdr_perturb.hpp"
#include <stdio.h>
#include <pthread.h>
#include <errno.h>
#include <condition_variable>
#include <memory>
#include <thread>
using namespace std::chrono;

int pdr_thread = 0, bmc_thread = 0, current_bmc_execution = 0, nframes = INT_MAX-1;

struct ThreadArgs{
    Aiger* aiger;
    int thread_index;
    PDRDirection direction;
    PDRRepresentation representation;
};

void *thread_start_bmc(void *arg){
    auto *args = static_cast<ThreadArgs *>(arg);
    Aiger* aiger_data = args->aiger;
    int thread_index = args->thread_index;
    BMC bmc(aiger_data, nframes + 1, thread_index, bmc_thread);
    int res_bmc = bmc.check(); 
    if(aiger_data->moreinfo_for_bmc and res_bmc) 
        cout << "best configuration: bmc thread " + to_string(thread_index) + "\n";
    pthread_exit(NULL); 
}

void *thread_start_pdr(void *arg){
    auto *args = static_cast<ThreadArgs *>(arg);
    Aiger* aiger_data = args->aiger;
    int thread_index = args->thread_index;
    PDR pdr(aiger_data, thread_index, 1, 1, 1, args->direction, args->representation);
    pdr.set_randomized_seed(pdr_thread > 1);
    int res_pdr = pdr.check();   
    if(moreinfo_for_pdr and res_pdr) 
        cout << "best configuration: pdr thread " + to_string(thread_index) + "\n";
    pthread_exit(NULL); 
}

struct ParallelPDRState{
    PDR *pdr;
    std::mutex mutex;
    std::atomic<int> completed_steps;
    std::atomic<bool> started;
    std::atomic<int> result;

    explicit ParallelPDRState(PDR *engine):
        pdr(engine), completed_steps(0), started(false), result(0) {}
};

struct PDRLaneCounts{
    int forward_aig = 0;
    int forward_compact_aig = 0;
    int forward_lowered_xag = 0;
    int forward_xag = 0;
    int reverse_aig = 0;
    int reverse_compact_aig = 0;
    int reverse_lowered_xag = 0;
    int reverse_xag = 0;
    bool explicit_counts = false;

    int total() const {
        return forward_aig + forward_compact_aig + forward_lowered_xag + forward_xag
            + reverse_aig + reverse_compact_aig + reverse_lowered_xag + reverse_xag;
    }
};

struct PDRLaneConfig{
    PDRDirection direction;
    PDRRepresentation representation;
    string name;
};

const char *pdr_representation_name(PDRRepresentation representation){
    switch(representation){
    case PDRRepresentation::Aig:
        return "aig";
    case PDRRepresentation::CompactAig:
        return "aig-compact";
    case PDRRepresentation::LoweredXag:
        return "xag-lowered";
    case PDRRepresentation::Xag:
    case PDRRepresentation::Default:
        return "xag";
    }
    return "unknown";
}

int run_parallel_pdr(Aiger *aiger, bool uc, bool pr,
                     const PDRLaneCounts &lane_counts){
    auto env_size = [](const char *name, std::size_t default_value){
        const char *value = std::getenv(name);
        if(value == nullptr)
            return default_value;
        long parsed = std::strtol(value, nullptr, 10);
        return parsed < 0 ? default_value : static_cast<std::size_t>(parsed);
    };
    auto env_enabled = [](const char *name, bool default_value){
        const char *value = std::getenv(name);
        if(value == nullptr)
            return default_value;
        string setting(value);
        return !(setting == "0" || setting == "false" || setting == "off");
    };

    bool share_enabled = env_enabled("MC_PDR_SHARE", true);
    const int forward_lane_count = lane_counts.forward_aig + lane_counts.forward_compact_aig
        + lane_counts.forward_lowered_xag + lane_counts.forward_xag;
    const int reverse_lane_count = lane_counts.reverse_aig + lane_counts.reverse_compact_aig
        + lane_counts.reverse_lowered_xag + lane_counts.reverse_xag;
    LemmaExchange lemma_exchange(
        env_size("MC_PDR_SHARE_QUEUE", 100000),
        env_size("MC_PDR_SHARE_MAX_CUBE", 64),
        env_size("MC_PDR_SHARE_BATCH", 256));

    vector<PDRLaneConfig> lane_configs;
    auto add_group = [&](PDRDirection direction, PDRRepresentation representation, int count){
        string base_name = string(direction == PDRDirection::Reverse ? "reverse-" : "forward-") +
                           pdr_representation_name(representation);
        for(int instance=0; instance<count; ++instance)
            lane_configs.push_back(PDRLaneConfig{
                direction, representation, base_name + "-" + to_string(instance)});
    };
    add_group(PDRDirection::Forward, PDRRepresentation::Aig, lane_counts.forward_aig);
    add_group(PDRDirection::Forward, PDRRepresentation::CompactAig,
              lane_counts.forward_compact_aig);
    add_group(PDRDirection::Forward, PDRRepresentation::LoweredXag,
              lane_counts.forward_lowered_xag);
    add_group(PDRDirection::Forward, PDRRepresentation::Xag, lane_counts.forward_xag);
    add_group(PDRDirection::Reverse, PDRRepresentation::Aig, lane_counts.reverse_aig);
    add_group(PDRDirection::Reverse, PDRRepresentation::CompactAig,
              lane_counts.reverse_compact_aig);
    add_group(PDRDirection::Reverse, PDRRepresentation::LoweredXag,
              lane_counts.reverse_lowered_xag);
    add_group(PDRDirection::Reverse, PDRRepresentation::Xag, lane_counts.reverse_xag);

    std::atomic<bool> cancel_requested(false);
    vector<std::unique_ptr<PDR>> engines;
    vector<std::unique_ptr<ParallelPDRState>> states;
    vector<string> lane_names;
    vector<int> forward_lanes;
    vector<int> reverse_lanes;
    engines.reserve(lane_configs.size());
    states.reserve(lane_configs.size());
    lane_names.reserve(lane_configs.size());

    std::atomic<int> winner_result(0);
    std::atomic<int> winner_index(-1);
    int bridge_winner_lane = -1;
    std::mutex event_mutex;
    std::condition_variable event_cv;
    std::atomic<bool> bridge_pending(false);

    int bridge_queries = 0;
    int forward_blocks = 0;
    int reverse_blocks = 0;
    bool print_stats = std::getenv("MC_PDR_STATS") != nullptr;
    int bridge_budget = 1;
    int meet_interval = 8;
    if(const char *value = std::getenv("MC_BIDIR_BRIDGE_BUDGET"))
        bridge_budget = std::max(0, std::atoi(value));
    if(const char *value = std::getenv("MC_BIDIR_MEET_INTERVAL"))
        meet_interval = std::max(1, std::atoi(value));
    bridge_pending.store(bridge_budget > 0 && meet_interval == 1);

    auto publish_result = [&](int index, int result){
        if(result != 10 && result != 20)
            return false;
        int expected = 0;
        if(!winner_result.compare_exchange_strong(expected, result))
            return false;
        winner_index.store(index);
        cancel_requested.store(true);
        bridge_pending.store(false);
        event_cv.notify_all();
        return true;
    };

    auto run_engine = [&](ParallelPDRState *state, int index){
        int result = -1;
        if(!cancel_requested.load()){
            std::lock_guard<std::mutex> lock(state->mutex);
            if(!cancel_requested.load())
                result = state->pdr->start(true);
        }
        state->result.store(result);
        state->started.store(true);
        event_cv.notify_all();
        if(result > 0)
            publish_result(index, result);

        while(result == 0 && !cancel_requested.load()){
            {
                std::unique_lock<std::mutex> lock(event_mutex);
                event_cv.wait(lock, [&]{
                    return !bridge_pending.load() || cancel_requested.load();
                });
            }
            if(cancel_requested.load())
                break;
            {
                std::lock_guard<std::mutex> lock(state->mutex);
                if(cancel_requested.load())
                    break;
                result = state->pdr->step();
            }
            state->result.store(result);
            if(result == 0)
                ++state->completed_steps;
            event_cv.notify_all();
            if(result > 0)
                publish_result(index, result);
            std::this_thread::yield();
        }
    };

    vector<std::thread> workers;
    workers.reserve(lane_configs.size());
    for(const PDRLaneConfig &config : lane_configs){
        if(winner_result.load() != 0)
            break;

        int lane = static_cast<int>(engines.size());
        std::unique_ptr<PDR> engine(new PDR(
            aiger, lane, uc, pr, 1, config.direction, config.representation));
        if(winner_result.load() != 0)
            break;

        engine->set_randomized_seed(lane_configs.size() > 1);
        engine->set_cancel_flag(&cancel_requested);
        bool lane_has_peer = config.direction == PDRDirection::Reverse
            ? reverse_lane_count > 1 : forward_lane_count > 1;
        if(share_enabled && lane_has_peer)
            engine->set_lemma_exchange(&lemma_exchange);
        engines.push_back(std::move(engine));
        states.push_back(std::unique_ptr<ParallelPDRState>(
            new ParallelPDRState(engines.back().get())));
        lane_names.push_back(config.name);
        if(config.direction == PDRDirection::Reverse)
            reverse_lanes.push_back(lane);
        else
            forward_lanes.push_back(lane);
        workers.push_back(std::thread(run_engine, states.back().get(), lane));
        std::this_thread::yield();
    }

    auto best_lane = [&](const vector<int> &lanes){
        int best = -1;
        int best_steps = -1;
        for(int lane : lanes){
            if(!states[lane]->started.load() || states[lane]->result.load() != 0)
                continue;
            int steps = states[lane]->completed_steps.load();
            if(steps > best_steps){
                best = lane;
                best_steps = steps;
            }
        }
        return best;
    };

    int next_bridge_round = meet_interval - 1;
    while(winner_result.load() == 0){
        {
            std::unique_lock<std::mutex> lock(event_mutex);
            event_cv.wait_for(lock, std::chrono::milliseconds(5));
        }
        if(winner_result.load() != 0)
            break;
        if(bridge_budget == 0)
            continue;
        int forward_lane = best_lane(forward_lanes);
        int reverse_lane = best_lane(reverse_lanes);
        if(forward_lane < 0 || reverse_lane < 0)
            continue;
        int completed_rounds = std::min(states[forward_lane]->completed_steps.load(),
                                        states[reverse_lane]->completed_steps.load());
        if(completed_rounds < next_bridge_round)
            continue;

        bridge_pending.store(true);
        std::unique_lock<std::mutex> forward_lock(states[forward_lane]->mutex, std::defer_lock);
        std::unique_lock<std::mutex> reverse_lock(states[reverse_lane]->mutex, std::defer_lock);
        std::lock(forward_lock, reverse_lock);
        PDR &forward = *states[forward_lane]->pdr;
        PDR &reverse = *states[reverse_lane]->pdr;

        if(winner_result.load() == 0){
            for(int attempt=0; attempt<bridge_budget; ++attempt){
                BridgeCandidate bridge;
                ++bridge_queries;
                if(!forward.find_bridge(reverse, bridge))
                    break;

                if(print_stats){
                    cout << "c BIDIR_BRIDGE query=" << bridge_queries
                         << " forward_lane=" << lane_names[forward_lane]
                         << " reverse_lane=" << lane_names[reverse_lane]
                         << " left=";
                    for(int l : bridge.left.latches) cout << (l > 0 ? '1' : '0');
                    cout << " right=";
                    for(int l : bridge.right.latches) cout << (l > 0 ? '1' : '0');
                    cout << endl;
                }

                vector<TraceFrame> prefix;
                if(forward.block_exact_state(bridge.left, forward.depth(), prefix)){
                    ++forward_blocks;
                    if(print_stats)
                        cout << "c BIDIR_CAND query=" << bridge_queries << " blocked=forward" << endl;
                    continue;
                }

                vector<TraceFrame> suffix;
                TraceFrame reverse_candidate;
                if(!reverse.map_trace_from(forward, bridge.right, reverse_candidate)){
                    bridge_budget = 0;
                    break;
                }
                if(reverse.block_exact_state(reverse_candidate, reverse.depth(), suffix)){
                    ++reverse_blocks;
                    if(print_stats)
                        cout << "c BIDIR_CAND query=" << bridge_queries << " blocked=reverse" << endl;
                    continue;
                }

                vector<TraceFrame> witness(prefix.begin(), prefix.end());
                for(const TraceFrame &reverse_frame : suffix){
                    TraceFrame mapped_frame;
                    if(!forward.map_trace_from(reverse, reverse_frame, mapped_frame)){
                        bridge_budget = 0;
                        witness.clear();
                        break;
                    }
                    witness.push_back(std::move(mapped_frame));
                }
                if(witness.empty())
                    break;
                if(!forward.validate_trace(witness)){
                    if(print_stats)
                        cout << "c BIDIR_MEET rejected=invalid_joined_trace" << endl;
                    bridge_budget = 0;
                    break;
                }
                forward.set_counterexample_trace(witness);
                bridge_winner_lane = forward_lane;
                publish_result(static_cast<int>(engines.size()), 10);
                if(print_stats){
                    cout << "c BIDIR_MEET result=unsafe bridge_queries=" << bridge_queries
                         << " forward_blocks=" << forward_blocks
                         << " reverse_blocks=" << reverse_blocks
                         << " interval=" << meet_interval
                         << " budget=" << bridge_budget
                         << " prefix_frames=" << prefix.size()
                         << " suffix_frames=" << suffix.size() << endl;
                }
                break;
            }
        }
        next_bridge_round += meet_interval;
        forward_lock.unlock();
        reverse_lock.unlock();
        bridge_pending.store(false);
        event_cv.notify_all();
    }

    cancel_requested.store(true);
    bridge_pending.store(false);
    event_cv.notify_all();
    for(std::thread &worker : workers)
        worker.join();

    int result = winner_result.load();
    int winner = winner_index.load();
    int result_lane = winner == static_cast<int>(engines.size()) ? bridge_winner_lane : winner;
    PDR &winner_pdr = *engines[result_lane >= 0 ? result_lane : 0];
    {
        std::lock_guard<std::mutex> lock(result_mutex);
        RESULT = result;
        if(result == 10)
            winner_pdr.show_witness();
    }
    if(print_stats){
        string winner_name = winner == static_cast<int>(engines.size())
            ? "bridge-" + lane_names[result_lane]
            : (winner >= 0 ? lane_names[winner] : "none");
        cout << "c BIDIR_MEET result=" << (result == 20 ? "safe" : "unsafe")
             << " winner=" << winner_name
             << " parallel=" << engines.size()
             << " bridge_queries=" << bridge_queries
             << " forward_blocks=" << forward_blocks
             << " reverse_blocks=" << reverse_blocks
             << " interval=" << meet_interval
             << " budget=" << bridge_budget
             << " sharing=" << (share_enabled &&
                                 (forward_lane_count > 1 || reverse_lane_count > 1))
             << " shared_published=" << lemma_exchange.published()
             << " shared_delivered=" << lemma_exchange.delivered()
             << " shared_dropped=" << lemma_exchange.dropped() << endl;
    }
    for(size_t lane=0; lane<engines.size(); ++lane)
        engines[lane]->finish(static_cast<int>(lane) == result_lane ? result : 0);
    return result;
}

int main(int argc, char **argv){
    auto t_begin = system_clock::now();
    if (argc == 2 && std::string(argv[1]) == "-h") {
        std::cout << "USAGE: ./modelchecker [OPTIONS] <aig-file>\n\n"
                     "OPTIONS:\n"
                     "  -findbug [nframes]       Run single-threaded BMC for each property to `nframes` steps. Ignores all other parameters. Default: INT_MAX\n"
                     "  -bmc <bmc_thread>        Set the number of BMC threads (0-12). Default: 0\n"
                     "  -pdr <pdr_thread>        Set the number of PDR threads (0-4). Default: 0\n"
                     "  -pindex <property_index> Specify the property index for verification. Default: 0\n"
                     "  -engine <mode>           Single PDR direction: forward or reverse. Default: forward\n"
                     "  --forward-aig <count>    Number of forward AIG PDR lanes.\n"
                     "  --forward-aig-compact <count> Number of forward swept/renumbered AIG lanes.\n"
                     "  --forward-xag-lowered <count> Number of forward XAG-to-AND control lanes.\n"
                     "  --forward-xag <count>    Number of forward XAG PDR lanes.\n"
                     "  --reverse-aig <count>    Number of reverse AIG PDR lanes.\n"
                     "  --reverse-aig-compact <count> Number of reverse swept/renumbered AIG lanes.\n"
                     "  --reverse-xag-lowered <count> Number of reverse XAG-to-AND control lanes.\n"
                     "  --reverse-xag <count>    Number of reverse XAG PDR lanes.\n"
                     "  -xag                     Run PDR on AIG-to-XAG converted structure. Default: on\n"
                     "  -xag-lowered             Recover XORs, then lower them to canonical AND networks.\n"
                     "  -aig-compact             Sweep and compact the AIG without recovering XORs.\n"
                     "  -aig                     Run PDR on original AIG structure.\n"
                     "  -witness                 Output witness if a bug is found. Default: off\n"
                     "  -certificate             Output certificate if the circuit is safe. Default: off\n"
                     "  -uc                      Enable CPO-Driven UNSAT Core Generation (single-threaded PDR only)\n"
                     "  -pr                      Enable CPO-Driven Proof Obligation Propagation (single-threaded PDR only)\n"
                     "  -h                       Show this help message and exit.\n\n"
                     "Example:\n"
                     "  ./modelchecker --forward-aig 1 --forward-xag 1 --reverse-aig 1 --reverse-xag 1 example.aig\n";
        return 0;
    }

    // cout << "USAGE: ./modelchecker [OPTIONS] <aig-file>\n";
    // cout << "Try './modelchecker -h' for more details.\n";
    int property_index = 0;
    bool pr = 0, uc = 0, witness = 0, certificate = 0, find_bug_only = 0, log = 0;
    PDRRepresentation selected_representation = PDRRepresentation::Xag;
    string engine = "forward";
    PDRLaneCounts lane_counts;
    for (int i = 1; i < argc-1; ++i){
        string arg = argv[i];
        if (arg == "-pr")
            pr = 1;
        else if (arg == "-uc")  
            uc = 1;
        else if (arg == "-witness")
            witness = 1;
        else if (arg == "-certificate")
            certificate = 1;
        else if (arg == "-v")
            log = 1;
        else if (arg == "-xag")
            selected_representation = PDRRepresentation::Xag;
        else if (arg == "-xag-lowered")
            selected_representation = PDRRepresentation::LoweredXag;
        else if (arg == "-aig-compact")
            selected_representation = PDRRepresentation::CompactAig;
        else if (arg == "-aig")
            selected_representation = PDRRepresentation::Aig;
        else if (arg == "-findbug"){
            find_bug_only = 1;
            if (i + 1 < argc && isdigit(argv[i + 1][0])){
                string value = argv[++i];
                nframes = validateInput(arg, value, 0, INT_MAX-1, INT_MAX-1);
            }
        }
        else if (arg == "-bmc" || arg == "-pdr" || arg == "-pindex" || arg == "-engine" ||
                 arg == "--forward-aig" || arg == "--forward-xag" ||
                 arg == "--forward-aig-compact" || arg == "--forward-xag-lowered" ||
                 arg == "--reverse-aig" || arg == "--reverse-xag" ||
                 arg == "--reverse-aig-compact" || arg == "--reverse-xag-lowered"){
            if (i + 1 >= argc) {
                cerr << "Error: Missing value for " << arg << ". Defaulting to 0.\n";
                continue;
            }
            string value = argv[++i];
            if (arg == "-engine"){
                if(value != "forward" && value != "reverse" && value != "bidirectional"){
                    cerr << "Error: -engine must be forward, reverse, or bidirectional.\n";
                    return 2;
                }
                engine = value;
            }
            else if (arg == "-bmc")
                bmc_thread = validateInput(arg, value, 0, 12, 0);
            else if (arg == "-pdr")
                pdr_thread = validateInput(arg, value, 0, 4, 0);
            else if (arg == "-pindex")
                property_index = validateInput(arg, value, 0, INT_MAX, 0);
            else{
                int count = validateInput(arg, value, 0, 128, 0);
                lane_counts.explicit_counts = true;
                if(arg == "--forward-aig") lane_counts.forward_aig = count;
                else if(arg == "--forward-aig-compact") lane_counts.forward_compact_aig = count;
                else if(arg == "--forward-xag-lowered") lane_counts.forward_lowered_xag = count;
                else if(arg == "--forward-xag") lane_counts.forward_xag = count;
                else if(arg == "--reverse-aig") lane_counts.reverse_aig = count;
                else if(arg == "--reverse-aig-compact") lane_counts.reverse_compact_aig = count;
                else if(arg == "--reverse-xag-lowered") lane_counts.reverse_lowered_xag = count;
                else lane_counts.reverse_xag = count;
            }
        }
    }
    Aiger *aiger = load_aiger_from_file(string(argv[argc-1]), property_index, witness, certificate, find_bug_only, log);
    // apply_pdr_perturbations(aiger);
    aiger->use_xag_for_pdr = selected_representation == PDRRepresentation::Xag;
    aiger->translate_to_dimacs();

    if(certificate && (engine != "forward" || lane_counts.total() > 0)){
        cerr << "Warning: certificate output is only supported by the forward engine; disabling it.\n";
        aiger->output_certificate = false;
    }

    if(find_bug_only){
        std::vector<ThreadArgs> bmc_args(aiger->num_property);
        pthread_t tbug[64];
        bmc_thread = 1;
        aiger->output_witness = 1;
        aiger->moreinfo_for_bmc = 0;
        for(int t = 0; t < aiger->num_property; t++){
            bmc_args[t] = {aiger, t, PDRDirection::Forward, selected_representation};
            // aiger->bad = aiger->allbad[t];
            // aiger->propertyIndex = 0;
            int ret_bmc = pthread_create (&tbug[t], NULL, thread_start_bmc, &bmc_args[t]);
        }    
        for(int t = 0; t < aiger->num_property; t++)
            pthread_join(tbug[t], NULL);    
    }
    else if(lane_counts.explicit_counts && lane_counts.total() > 0){
        run_parallel_pdr(aiger, uc, pr, lane_counts);
    }
    else if(lane_counts.explicit_counts || engine == "bidirectional"){
        if(engine == "bidirectional" && !lane_counts.explicit_counts)
            cerr << "Warning: -engine bidirectional requires explicit lane counts; defaulting to single-threaded forward PDR." << endl;
        PDR pdr(aiger, -1, uc, pr, 1, PDRDirection::Forward, selected_representation);
        int res_pdr = pdr.check();
    }
    else if(pdr_thread == 0 and bmc_thread == 0){
        PDRDirection direction = engine == "reverse" ? PDRDirection::Reverse : PDRDirection::Forward;
        PDR pdr(aiger, -1, uc, pr, 1, direction, selected_representation);
        int res_pdr = pdr.check();  
    }
    else{
        std::vector<ThreadArgs> pdr_args(pdr_thread);
        std::vector<ThreadArgs> bmc_args(bmc_thread);
        pthread_t tpdr[8], tbmc[16];
        for(int t = 0; t < pdr_thread; t++){
            PDRDirection direction = engine == "reverse" ? PDRDirection::Reverse : PDRDirection::Forward;
            pdr_args[t] = {aiger, t, direction, selected_representation};
            int ret_pdr = pthread_create (&tpdr[t], NULL, thread_start_pdr, &pdr_args[t]);
        }
        for(int t = 0; t < bmc_thread; t++){
            bmc_args[t] = {aiger, t, PDRDirection::Forward, selected_representation};
            int ret_bmc = pthread_create (&tbmc[t], NULL, thread_start_bmc, &bmc_args[t]);
        }
        
        for(int t = 0; t < pdr_thread; t++)
            pthread_join(tpdr[t], NULL);
        for(int t = 0; t < bmc_thread; t++)
            pthread_join(tbmc[t], NULL);
    }

    if(find_bug_only){
        if(RESULT == 20)
            cout << "0" << endl;
        else if(RESULT == 10)
            cout << "1" << endl;
        else
            cout << "2" << endl;
    }else{
        if(RESULT == 10)
            cout << "result: unsafe\n";
        else if(RESULT == 20)
            cout << "result: safe\n";
        else
            cout << "result: unknown\n";
    }

    delete aiger;
    auto t_end = system_clock::now();
    auto duration = duration_cast<microseconds>(t_end - t_begin);
    double time_in_sec = double(duration.count()) * microseconds::period::num / microseconds::period::den;
    if(!find_bug_only){
        cout << "time = "<< time_in_sec << "s\n";
    } 
    return 0;
}
