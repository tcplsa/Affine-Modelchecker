#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TOOL=${1:?usage: run_bve_aig_hard_domain.sh mc|ric3 seed [shard-index] [shard-count]}
SEED=${2:?usage: run_bve_aig_hard_domain.sh mc|ric3 seed [shard-index] [shard-count]}
SHARD_INDEX=${3:-0}
SHARD_COUNT=${4:-1}
RESULT_DIR=${BVE_AIG_HARD_RESULT_DIR:-$SCRIPT_DIR/results/bve_aig_hard_domain_v1}
SELECTION=${BVE_AIG_HARD_SELECTION:-$RESULT_DIR/selection.json}
WORKERS=${BVE_AIG_HARD_WORKERS:-8}
TIMEOUT=${BVE_AIG_HARD_TIMEOUT:-1800}
DOMAIN=${BVE_AIG_HARD_DOMAIN:-all}

case "$TOOL" in
    mc) BINARY=${BVE_AIG_HARD_MC_BINARY:-/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker-sumhigh-confirm-v1} ;;
    ric3) BINARY=${BVE_AIG_HARD_RIC3_BINARY:-/home/wudl/rIC3/target/release/ric3} ;;
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

mkdir "$LOCK_DIR" 2>/dev/null || { echo "experiment already running: $LOCK_DIR" >&2; exit 1; }
setsid python3 "$SCRIPT_DIR/run_bve_aig_hard_domain.py" \
    --selection "$SELECTION" --binary "$BINARY" --output "$OUTPUT" \
    --tool "$TOOL" --seed "$SEED" --workers "$WORKERS" --timeout "$TIMEOUT" \
    --domain "$DOMAIN" --shard-index "$SHARD_INDEX" --shard-count "$SHARD_COUNT" &
RUNNER_PID=$!
wait "$RUNNER_PID"
RUNNER_PID=
rmdir "$LOCK_DIR"
trap - HUP INT TERM EXIT
