#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: $0 SHARD_INDEX SHARD_COUNT" >&2
    exit 2
fi

SHARD_INDEX=$1
SHARD_COUNT=$2
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RESULT_DIR=${RIC3_PRODUCT_SUM_DIR:-$SCRIPT_DIR/results/ric3_product_sum_full_v1}
BASELINE_DIR=${RIC3_PRODUCT_SUM_BASELINE_DIR:-$SCRIPT_DIR/results/bve_full_campaign_v1}
MANIFEST=${RIC3_PRODUCT_SUM_MANIFEST:-$SCRIPT_DIR/results/full_aig_xag_all_years_v1/manifest.json}
BINARY=${RIC3_PRODUCT_SUM_BINARY:-/home/wudl/rIC3/target/release/ric3}
WORKERS=${RIC3_PRODUCT_SUM_WORKERS:-12}
TIMEOUT=${RIC3_PRODUCT_SUM_TIMEOUT:-1800}
SEED=${RIC3_PRODUCT_SUM_SEED:-730001}
OUTPUT=$RESULT_DIR/results_shard_${SHARD_INDEX}_of_${SHARD_COUNT}.tsv
LOCK_DIR=${OUTPUT}.lock
RUNNER_PID=

mkdir -p "$RESULT_DIR"

cleanup() {
    if [[ -n "${RUNNER_PID:-}" ]] && kill -0 "$RUNNER_PID" 2>/dev/null; then
        kill -TERM -- "-$RUNNER_PID" 2>/dev/null || true
        wait "$RUNNER_PID" 2>/dev/null || true
    fi
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup HUP INT TERM EXIT

[[ -x "$BINARY" ]] || { echo "missing executable: $BINARY" >&2; exit 1; }
mkdir "$LOCK_DIR" 2>/dev/null || {
    echo "shard already running: $LOCK_DIR" >&2
    exit 1
}

setsid python3 "$SCRIPT_DIR/run_ric3_product_sum_full.py" \
    --manifest "$MANIFEST" --binary "$BINARY" --output "$OUTPUT" \
    --shard-index "$SHARD_INDEX" --shard-count "$SHARD_COUNT" \
    --workers "$WORKERS" --timeout "$TIMEOUT" --seed "$SEED" &
RUNNER_PID=$!
wait "$RUNNER_PID"
RUNNER_PID=

candidate=()
total=0
for ((index = 0; index < SHARD_COUNT; ++index)); do
    path=$RESULT_DIR/results_shard_${index}_of_${SHARD_COUNT}.tsv
    [[ -f "$path" ]] || continue
    candidate+=("$path")
    total=$((total + $(wc -l < "$path") - 1))
done
if (( ${#candidate[@]} == SHARD_COUNT && total == 1980 )); then
    python3 "$SCRIPT_DIR/analyze_ric3_product_sum_full.py" \
        --baseline \
            "$BASELINE_DIR/ric3_shard_0_of_3.tsv" \
            "$BASELINE_DIR/ric3_shard_1_of_3.tsv" \
            "$BASELINE_DIR/ric3_shard_2_of_3.tsv" \
        --candidate "${candidate[@]}" --output "$RESULT_DIR/report.md"
else
    echo "shard complete; aggregate progress=$total/1980"
fi

rmdir "$LOCK_DIR"
trap - HUP INT TERM EXIT
