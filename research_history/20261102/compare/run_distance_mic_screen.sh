#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^[012]$ ]]; then
    echo "usage: $0 ROLE(0|1|2)" >&2
    exit 2
fi

ROLE=$1
ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
RESULTS="$TOOLS/results/mc_distance_mic_screen_v1"
MANIFEST="$TOOLS/results/mc_hard_breakthrough_screen_v1/diagnostic_progress_candidates.json"
BINARY="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker"
TIMEOUT=${DISTANCE_MIC_TIMEOUT:-600}
WORKERS=${DISTANCE_MIC_WORKERS:-24}

case "$ROLE" in
    0) STRATEGIES=(baseline mic-near) ;;
    1) STRATEGIES=(mic-far mic-feedback) ;;
    2) STRATEGIES=(mic-distance-feedback mic-mixed) ;;
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
