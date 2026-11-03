#!/usr/bin/env bash
set -euo pipefail

if [[ $# -gt 2 ]]; then
    echo "usage: $0 [SHARD_INDEX [SHARD_COUNT]]" >&2
    exit 2
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SHARD_INDEX=${1:-0}
SHARD_COUNT=${2:-1}
OUT_DIR=${RIC3_LOCAL_FOLLOWUP_DIR:-$SCRIPT_DIR/results/ric3_native_local_followup_v1}
# A hard native rIC3 replica can exceed 16 GiB. Five four-replica configs already
# expose up to 20 processes for one model, so model-level concurrency stays at one.
WORKERS=${RIC3_LOCAL_FOLLOWUP_WORKERS:-1}
TIMEOUT=${RIC3_LOCAL_FOLLOWUP_TIMEOUT:-1800}
SEED=${RIC3_LOCAL_FOLLOWUP_SEED:-930001}
ACTIVE_PID=

mkdir -p "$OUT_DIR"

cleanup() {
    if [[ -n "${ACTIVE_PID:-}" ]] && kill -0 "$ACTIVE_PID" 2>/dev/null; then
        kill -TERM -- "-$ACTIVE_PID" 2>/dev/null || true
        wait "$ACTIVE_PID" 2>/dev/null || true
    fi
}
trap cleanup INT TERM EXIT

setsid python3 "$SCRIPT_DIR/run_ric3_native_local_followup.py" \
    --manifest "$SCRIPT_DIR/results/full_aig_xag_all_years_v1/manifest.json" \
    --baseline-inputs \
        "$SCRIPT_DIR/results/bve_full_campaign_v1/ric3_shard_0_of_3.tsv" \
        "$SCRIPT_DIR/results/bve_full_campaign_v1/ric3_shard_1_of_3.tsv" \
        "$SCRIPT_DIR/results/bve_full_campaign_v1/ric3_shard_2_of_3.tsv" \
    --binary /home/wudl/rIC3/target/release/ric3 \
    --output "$OUT_DIR/results_shard_${SHARD_INDEX}_of_${SHARD_COUNT}.tsv" \
    --selection "$OUT_DIR/selection.json" \
    --workers "$WORKERS" --timeout "$TIMEOUT" --seed "$SEED" \
    --shard-index "$SHARD_INDEX" --shard-count "$SHARD_COUNT" &
ACTIVE_PID=$!
wait "$ACTIVE_PID"
ACTIVE_PID=

inputs=()
total=0
for ((shard = 0; shard < SHARD_COUNT; shard++)); do
    path="$OUT_DIR/results_shard_${shard}_of_${SHARD_COUNT}.tsv"
    [[ -f "$path" ]] || continue
    inputs+=("$path")
    total=$((total + $(wc -l < "$path") - 1))
done
if (( ${#inputs[@]} == SHARD_COUNT && total == 100 )); then
    python3 "$SCRIPT_DIR/analyze_ric3_native_local_followup.py" \
        --input "${inputs[@]}" --output "$OUT_DIR/report.md"
else
    echo "shard complete; aggregate progress=$total/100"
fi

trap - INT TERM EXIT
