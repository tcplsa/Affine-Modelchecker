#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
    echo "usage: $0 SHARD_INDEX SHARD_COUNT [mc|ric3|both]" >&2
    exit 2
fi

SHARD_INDEX=$1
SHARD_COUNT=$2
SUITE=${3:-both}
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
MANIFEST=${BVE_FULL_MANIFEST:-$SCRIPT_DIR/results/full_aig_xag_all_years_v1/manifest.json}
OUTPUT_DIR=${BVE_FULL_OUTPUT_DIR:-$SCRIPT_DIR/results/bve_full_campaign_v1}
MC_BINARY=${BVE_FULL_MC:-/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker}
RIC3_BINARY=${BVE_FULL_RIC3:-/home/wudl/rIC3/target/release/ric3}
WORKERS=${BVE_FULL_WORKERS:-10}
TIMEOUT=${BVE_FULL_TIMEOUT:-1800}
SEED=${BVE_FULL_SEED:-730001}
MC_XAG_ORDER=${BVE_FULL_MC_XAG_ORDER:-sum-high}
RIC3_XAG_ORDER=${BVE_FULL_RIC3_XAG_ORDER:-product-high}
RIC3_CONFIG=${BVE_FULL_RIC3_CONFIG:-bl_4core_control}
RIC3_MODE=${BVE_FULL_RIC3_MODE:-replicas}
ACTIVE_PID=
ACTIVE_LOCK=

mkdir -p "$OUTPUT_DIR"

cleanup() {
    if [[ -n "${ACTIVE_PID:-}" ]] && kill -0 "$ACTIVE_PID" 2>/dev/null; then
        kill -TERM -- "-$ACTIVE_PID" 2>/dev/null || true
        wait "$ACTIVE_PID" 2>/dev/null || true
    fi
    if [[ -n "${ACTIVE_LOCK:-}" ]]; then
        rmdir "$ACTIVE_LOCK" 2>/dev/null || true
    fi
}
trap cleanup INT TERM EXIT

run_suite() {
    local tool=$1
    local binary output xag_order lock_dir
    if [[ "$tool" == mc ]]; then
        binary=$MC_BINARY
        xag_order=$MC_XAG_ORDER
    else
        binary=$RIC3_BINARY
        xag_order=$RIC3_XAG_ORDER
    fi
    output="$OUTPUT_DIR/${tool}_shard_${SHARD_INDEX}_of_${SHARD_COUNT}.tsv"
    lock_dir="$OUTPUT_DIR/.${tool}_shard_${SHARD_INDEX}_of_${SHARD_COUNT}.lock"
    if ! mkdir "$lock_dir" 2>/dev/null; then
        echo "shard is already running (lock exists): $lock_dir" >&2
        exit 1
    fi
    ACTIVE_LOCK=$lock_dir
    if [[ ! -x "$binary" ]]; then
        echo "missing executable: $binary" >&2
        exit 1
    fi
    setsid python3 "$SCRIPT_DIR/run_bve_full_campaign.py" \
        --tool "$tool" \
        --manifest "$MANIFEST" \
        --binary "$binary" \
        --output "$output" \
        --shard-index "$SHARD_INDEX" \
        --shard-count "$SHARD_COUNT" \
        --workers "$WORKERS" \
        --timeout "$TIMEOUT" \
        --seed "$SEED" \
        --xag-order "$xag_order" \
        --ric3-config "$RIC3_CONFIG" \
        --ric3-mode "$RIC3_MODE" &
    ACTIVE_PID=$!
    wait "$ACTIVE_PID"
    ACTIVE_PID=
    rmdir "$ACTIVE_LOCK"
    ACTIVE_LOCK=
}

case "$SUITE" in
    mc|ric3)
        run_suite "$SUITE"
        ;;
    both)
        run_suite mc
        run_suite ric3
        ;;
    *)
        echo "suite must be mc, ric3, or both" >&2
        exit 2
        ;;
esac

trap - INT TERM EXIT
