#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SEED=${1:?usage: run_ric3_order_concurrent.sh seed}
RESULT_DIR=${RIC3_ORDER_CONCURRENT_RESULT_DIR:-$SCRIPT_DIR/results/ric3_order_concurrent_v1}
SELECTION=${RIC3_ORDER_CONCURRENT_SELECTION:-$RESULT_DIR/selection.json}
BINARY=${RIC3_ORDER_CONCURRENT_BINARY:-/home/wudl/rIC3/target/release/ric3-bve-width-v1}
WORKERS=${RIC3_ORDER_CONCURRENT_WORKERS:-14}
TIMEOUT=${RIC3_ORDER_CONCURRENT_TIMEOUT:-1800}

mkdir -p "$RESULT_DIR"
OUTPUT="$RESULT_DIR/seed${SEED}.tsv"
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
setsid python3 "$SCRIPT_DIR/run_ric3_order_concurrent.py" \
    --manifest "$SCRIPT_DIR/results/full_aig_xag_all_years_v1/manifest.json" \
    --selection "$SELECTION" --binary "$BINARY" --output "$OUTPUT" \
    --seed "$SEED" --workers "$WORKERS" --timeout "$TIMEOUT" &
RUNNER_PID=$!
wait "$RUNNER_PID"
RUNNER_PID=
rmdir "$LOCK_DIR"
trap - HUP INT TERM EXIT
