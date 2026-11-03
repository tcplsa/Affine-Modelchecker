#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RESULT_DIR=${MC_INDUCTION_RESULT_DIR:-$SCRIPT_DIR/results/mc_induction_observables_v2}
BINARY=${MC_INDUCTION_BINARY:-/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker-induction-observables-v1}
WORKERS=${MC_INDUCTION_WORKERS:-10}
TIMEOUT=${MC_INDUCTION_TIMEOUT:-300}
SEEDS=${MC_INDUCTION_SEEDS:-1290001 1300001 1310001}
SELECTION=$RESULT_DIR/selection.json
INPUTS=(
    "$SCRIPT_DIR/results/mc_sumhigh_concurrent_v1/seed1260001.tsv"
    "$SCRIPT_DIR/results/mc_sumhigh_concurrent_v1/seed1270001.tsv"
    "$SCRIPT_DIR/results/mc_sumhigh_concurrent_v1/seed1280001.tsv"
)

mkdir -p "$RESULT_DIR"
python3 "$SCRIPT_DIR/build_mc_induction_observable_selection.py" \
    --inputs "${INPUTS[@]}" --output "$SELECTION" --per-tier 15 --max-seconds "$TIMEOUT"

for seed in $SEEDS; do
    MC_SUMHIGH_RESULT_DIR="$RESULT_DIR" \
    MC_SUMHIGH_BINARY="$BINARY" \
    MC_SUMHIGH_WORKERS="$WORKERS" \
    MC_SUMHIGH_TIMEOUT="$TIMEOUT" \
    MC_SUMHIGH_SELECTION="$SELECTION" \
        "$SCRIPT_DIR/run_mc_sumhigh_concurrent.sh" "$seed"
done

python3 "$SCRIPT_DIR/analyze_mc_sumhigh_concurrent.py" \
    --inputs "$RESULT_DIR"/seed*.tsv --output "$RESULT_DIR/report.md" --bootstrap 10000
