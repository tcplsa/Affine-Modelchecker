#ifndef LEMMA_HPP
#define LEMMA_HPP

#include <cstddef>
#include <mutex>
#include <vector>

typedef std::vector<int> Cube; // the lits in the cube must be sorted
struct SharedLemma {
    Cube cube;
    int frame;
    int producer;
};

class LemmaBus {
    mutable std::mutex mutex_;
    std::vector<SharedLemma> lemmas_;

    public:
    void publish(const Cube& cube, int frame, int producer) {
        std::lock_guard<std::mutex> lock(mutex_);
        lemmas_.push_back({cube, frame, producer});
    }

    std::size_t size() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return lemmas_.size();
    }

    std::vector<SharedLemma> read_from(std::size_t& cursor) const {
        std::lock_guard<std::mutex> lock(mutex_);

        if (cursor > lemmas_.size())
            cursor = lemmas_.size();
        
        std::vector<SharedLemma> unseen(lemmas_.begin() + cursor, lemmas_.end());
        cursor = lemmas_.size();
        return unseen;
    }
};


#endif