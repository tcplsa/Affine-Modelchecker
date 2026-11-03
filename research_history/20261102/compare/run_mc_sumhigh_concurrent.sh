#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SEED=${1:?usage: run_mc_sumhigh_concurrent.sh seed}
RESULT_DIR=${MC_SUMHIGH_RESULT_DIR:-$SCRIPT_DIR/results/mc_sumhigh_concurrent_v1}
BINARY=${MC_SUMHIGH_BINARY:-/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker-sumhigh-confirm-v1}
WORKERS=${MC_SUMHIGH_WORKERS:-12}
TIMEOUT=${MC_SUMHIGH_TIMEOUT:-1800}
MANIFEST=${MC_SUMHIGH_MANIFEST:-$SCRIPT_DIR/results/full_aig_xag_all_years_v1/manifest.json}
SELECTION=${MC_SUMHIGH_SELECTION:-$SCRIPT_DIR/results/ric3_order_concurrent_v1/selection.json}

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
setsid python3 "$SCRIPT_DIR/run_mc_sumhigh_concurrent.py" \
    --manifest "$MANIFEST" \
    --selection "$SELECTION" \
    --binary "$BINARY" --output "$OUTPUT" --seed "$SEED" \
    --workers "$WORKERS" --timeout "$TIMEOUT" &
RUNNER_PID=$!
wait "$RUNNER_PID"
RUNNER_PID=
rmdir "$LOCK_DIR"
trap - HUP INT TERM EXIT
