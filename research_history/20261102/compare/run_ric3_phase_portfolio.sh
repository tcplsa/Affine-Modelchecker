#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SHARD_INDEX=${1:?usage: run_ric3_phase_portfolio.sh shard-index shard-count}
SHARD_COUNT=${2:?usage: run_ric3_phase_portfolio.sh shard-index shard-count}
RESULT_DIR=${RIC3_PHASE_PORTFOLIO_RESULT_DIR:-$SCRIPT_DIR/results/ric3_phase_portfolio_v1}
BINARY=${RIC3_PHASE_PORTFOLIO_BINARY:-/home/wudl/rIC3/target/release/ric3-phase-order-v1}

mkdir -p "$RESULT_DIR"
OUTPUT="$RESULT_DIR/shard${SHARD_INDEX}_of_${SHARD_COUNT}.tsv"
LOCK_DIR=${OUTPUT}.lock
RUNNER_PID=

cleanup() {
    if [[ -n "${RUNNER_PID:-}" ]] && kill -0 "$RUNNER_PID" 2>/dev/null; then
        kill -TERM -- "-$RUNNER_PID" 2>/dev/null || true
        wait "$RUNNER_PID" 2>/dev/null || true
    fi
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup HUP INT TERM EXIT

mkdir "$LOCK_DIR" 2>/dev/null || { echo "experiment already running: $LOCK_DIR" >&2; exit 1; }
setsid python3 "$SCRIPT_DIR/run_ric3_phase_portfolio.py" \
    --manifest "$SCRIPT_DIR/results/full_aig_xag_all_years_v1/manifest.json" \
    --selection "$SCRIPT_DIR/results/ric3_order_concurrent_v1/selection.json" \
    --binary "$BINARY" --output "$OUTPUT" --shard-index "$SHARD_INDEX" \
    --shard-count "$SHARD_COUNT" --seed 1160001 --workers 8 --timeout 600 &
RUNNER_PID=$!
wait "$RUNNER_PID"
RUNNER_PID=
rmdir "$LOCK_DIR"
trap - HUP INT TERM EXIT
