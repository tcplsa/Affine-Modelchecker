#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
TOOL=${1:?usage: run_bve_aig_hard_domain_seeds.sh mc|ric3 shard-index [shard-count]}
SHARD_INDEX=${2:?usage: run_bve_aig_hard_domain_seeds.sh mc|ric3 shard-index [shard-count]}
SHARD_COUNT=${3:-3}
SEEDS=${BVE_AIG_HARD_SEEDS:-"1310001 1320001 1330001"}

for seed in $SEEDS; do
    echo "tool=$TOOL seed=$seed shard=$SHARD_INDEX/$SHARD_COUNT"
    "$SCRIPT_DIR/run_bve_aig_hard_domain.sh" \
        "$TOOL" "$seed" "$SHARD_INDEX" "$SHARD_COUNT"
done

