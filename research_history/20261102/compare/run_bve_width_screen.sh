#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TOOL=${1:?usage: run_bve_width_screen.sh mc|ric3 seed [shard-index] [shard-count]}
SEED=${2:?usage: run_bve_width_screen.sh mc|ric3 seed [shard-index] [shard-count]}
SHARD_INDEX=${3:-0}
SHARD_COUNT=${4:-1}
RESULT_DIR=${BVE_WIDTH_RESULT_DIR:-$SCRIPT_DIR/results/bve_width_screen_v1}
MANIFEST=${BVE_WIDTH_MANIFEST:-$SCRIPT_DIR/results/full_aig_xag_all_years_v1/manifest.json}
SELECTION=${BVE_WIDTH_SELECTION:-$SCRIPT_DIR/results/bve_hard_specialization_v1/selection.json}
TIMEOUT=${BVE_WIDTH_TIMEOUT:-600}
WORKERS=${BVE_WIDTH_WORKERS:-7}
REPLICAS=${BVE_WIDTH_REPLICAS:-4}
RIC3_ORDER=${BVE_WIDTH_RIC3_ORDER:-product-sum-high}
WEIGHTS=${BVE_WIDTH_WEIGHTS:-"0 1 2 4"}

case "$TOOL" in
    mc) BINARY=${BVE_WIDTH_MC:-/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker-bve-width-v1} ;;
    ric3) BINARY=${BVE_WIDTH_RIC3:-/home/wudl/rIC3/target/release/ric3-bve-width-v1} ;;
    *) echo "tool must be mc or ric3" >&2; exit 2 ;;
esac

mkdir -p "$RESULT_DIR"
OUTPUT="$RESULT_DIR/${TOOL}_seed${SEED}_shard${SHARD_INDEX}_of_${SHARD_COUNT}.tsv"
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

[[ -x "$BINARY" ]] || { echo "missing executable: $BINARY" >&2; exit 1; }
mkdir "$LOCK_DIR" 2>/dev/null || { echo "experiment already running: $LOCK_DIR" >&2; exit 1; }

read -r -a WEIGHT_ARGS <<<"$WEIGHTS"
setsid python3 "$SCRIPT_DIR/run_bve_width_screen.py" \
    --tool "$TOOL" --manifest "$MANIFEST" --selection "$SELECTION" \
    --binary "$BINARY" --output "$OUTPUT" --weights "${WEIGHT_ARGS[@]}" \
    --seed "$SEED" --workers "$WORKERS" --replicas "$REPLICAS" \
    --bve-order "$RIC3_ORDER" --timeout "$TIMEOUT" \
    --shard-index "$SHARD_INDEX" --shard-count "$SHARD_COUNT" &
RUNNER_PID=$!
wait "$RUNNER_PID"
RUNNER_PID=

rmdir "$LOCK_DIR"
trap - HUP INT TERM EXIT
