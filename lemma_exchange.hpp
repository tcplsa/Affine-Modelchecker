#pragma once

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <mutex>
#include <vector>

struct SharedLemma{
    std::uint64_t sequence = 0;
    int source_lane = -1;
    std::vector<int> canonical_cube;
};

class LemmaExchange{
    struct Channel{
        std::mutex mutex;
        std::deque<SharedLemma> lemmas;
        std::uint64_t base_sequence = 0;
        std::uint64_t next_sequence = 0;
    };

    Channel channels[2];
    std::size_t queue_capacity;
    std::size_t max_cube_size;
    std::size_t batch_size;
    std::atomic<std::uint64_t> published_count;
    std::atomic<std::uint64_t> delivered_count;
    std::atomic<std::uint64_t> dropped_count;

public:
    LemmaExchange(std::size_t capacity, std::size_t max_cube, std::size_t batch);

    std::uint64_t subscribe(bool reverse);
    bool publish(bool reverse, int source_lane,
                 const std::vector<int> &canonical_cube);
    std::vector<SharedLemma> consume(bool reverse, int consumer_lane,
                                     std::uint64_t &cursor);

    std::uint64_t published() const { return published_count.load(); }
    std::uint64_t delivered() const { return delivered_count.load(); }
    std::uint64_t dropped() const { return dropped_count.load(); }
};
