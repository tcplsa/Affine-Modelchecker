#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^[012]$ ]]; then
    echo "usage: $0 ROLE(0|1|2)" >&2
    exit 2
fi

ROLE=$1
ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
RESULTS="$TOOLS/results/mc_hard_breakthrough_screen_v1"
MANIFEST="$RESULTS/candidates.json"
BINARY="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker"
TIMEOUT=${HARD_BREAKTHROUGH_TIMEOUT:-1200}
WORKERS=${HARD_BREAKTHROUGH_WORKERS:-28}

case "$ROLE" in
    0) STRATEGIES=(baseline source-init) ;;
    1) STRATEGIES=(source-zero source-random) ;;
    2) STRATEGIES=(first-phase heuristic) ;;
esac

mkdir -p "$RESULTS"
if [[ ! -s "$MANIFEST" ]]; then
    python3 "$TOOLS/build_hard_breakthrough_candidates.py" \
        --atlas "$TOOLS/results/mc_ric3_hard_global_v1/dynamic/dynamic_model_atlas.tsv" \
        --output "$MANIFEST"
fi

for strategy in "${STRATEGIES[@]}"; do
    output="$RESULTS/${strategy}.tsv"
    echo "role=$ROLE strategy=$strategy timeout=$TIMEOUT workers=$WORKERS"
    python3 "$TOOLS/run_mc_hard_diagnostic.py" \
        --manifest "$MANIFEST" \
        --binary "$BINARY" \
        --output "$output" \
        --timeout "$TIMEOUT" \
        --workers "$WORKERS" \
        --seed 730001 \
        --strategy "$strategy"
done

touch "$RESULTS/role${ROLE}.done"
echo "role=$ROLE complete"
