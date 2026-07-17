#include "lemma_exchange.hpp"

#include <algorithm>
#include <utility>

LemmaExchange::LemmaExchange(std::size_t capacity, std::size_t max_cube,
                             std::size_t batch):
    queue_capacity(std::max<std::size_t>(1, capacity)),
    max_cube_size(max_cube),
    batch_size(std::max<std::size_t>(1, batch)),
    published_count(0),
    delivered_count(0),
    dropped_count(0) {}

std::uint64_t LemmaExchange::subscribe(bool reverse){
    Channel &channel = channels[reverse ? 1 : 0];
    std::lock_guard<std::mutex> lock(channel.mutex);
    return channel.base_sequence;
}

bool LemmaExchange::publish(bool reverse, int source_lane,
                            const std::vector<int> &canonical_cube){
    if(canonical_cube.empty())
        return false;
    if(max_cube_size != 0 && canonical_cube.size() > max_cube_size)
        return false;

    Channel &channel = channels[reverse ? 1 : 0];
    std::lock_guard<std::mutex> lock(channel.mutex);
    SharedLemma lemma;
    lemma.sequence = channel.next_sequence++;
    lemma.source_lane = source_lane;
    lemma.canonical_cube = canonical_cube;
    channel.lemmas.push_back(std::move(lemma));
    ++published_count;

    while(channel.lemmas.size() > queue_capacity){
        channel.lemmas.pop_front();
        ++channel.base_sequence;
        ++dropped_count;
    }
    return true;
}

std::vector<SharedLemma> LemmaExchange::consume(bool reverse, int consumer_lane,
                                                std::uint64_t &cursor){
    Channel &channel = channels[reverse ? 1 : 0];
    std::lock_guard<std::mutex> lock(channel.mutex);
    if(cursor < channel.base_sequence)
        cursor = channel.base_sequence;

    std::vector<SharedLemma> result;
    result.reserve(batch_size);
    while(cursor < channel.next_sequence && result.size() < batch_size){
        const SharedLemma &lemma = channel.lemmas[cursor - channel.base_sequence];
        ++cursor;
        if(lemma.source_lane == consumer_lane)
            continue;
        result.push_back(lemma);
    }
    delivered_count += result.size();
    return result;
}
