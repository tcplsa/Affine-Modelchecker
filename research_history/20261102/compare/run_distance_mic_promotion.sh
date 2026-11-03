#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^[012]$ ]]; then
    echo "usage: $0 ROLE(0|1|2)" >&2
    exit 2
fi

ROLE=$1
ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
SCREEN="$TOOLS/results/mc_distance_mic_screen_v1"
RESULTS="$TOOLS/results/mc_distance_mic_promotion_v1"
MANIFEST="$SCREEN/promotion_candidates.json"
BINARY="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker"
TIMEOUT=${DISTANCE_MIC_PROMOTION_TIMEOUT:-3600}
WORKERS=${DISTANCE_MIC_PROMOTION_WORKERS:-4}

case "$ROLE" in
    0) STRATEGIES=(baseline mic-mixed) ;;
    1) STRATEGIES=(mic-near mic-far) ;;
    2) STRATEGIES=(mic-feedback mic-distance-feedback) ;;
esac

mkdir -p "$RESULTS"
for strategy in "${STRATEGIES[@]}"; do
    echo "role=$ROLE strategy=$strategy timeout=$TIMEOUT workers=$WORKERS"
    python3 "$TOOLS/run_mc_hard_diagnostic.py" \
        --manifest "$MANIFEST" \
        --binary "$BINARY" \
        --output "$RESULTS/${strategy}.tsv" \
        --timeout "$TIMEOUT" \
        --workers "$WORKERS" \
        --seed 730001 \
        --strategy "$strategy"
done

touch "$RESULTS/role${ROLE}.done"
echo "role=$ROLE complete"
