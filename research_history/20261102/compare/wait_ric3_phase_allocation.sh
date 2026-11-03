#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RESULT_DIR=${RIC3_PHASE_ALLOCATION_RESULT_DIR:-$SCRIPT_DIR/results/ric3_phase_allocation_v1}
SEEDS=(1200001 1210001 1220001)
EXPECTED=217

while true; do
    complete=1
    for seed in "${SEEDS[@]}"; do
        path="$RESULT_DIR/seed${seed}.tsv"
        if [[ ! -f "$path" ]]; then
            complete=0
            break
        fi
        rows=$(awk 'END { print (NR > 0 ? NR - 1 : 0) }' "$path")
        if [[ "$rows" -ne "$EXPECTED" || -d "${path}.lock" ]]; then
            complete=0
            break
        fi
    done
    if [[ "$complete" -eq 1 ]]; then
        break
    fi
    sleep 60
done

python3 -S "$SCRIPT_DIR/analyze_ric3_phase_allocation.py" \
    --inputs "$RESULT_DIR/seed1200001.tsv" "$RESULT_DIR/seed1210001.tsv" \
    "$RESULT_DIR/seed1220001.tsv" --output "$RESULT_DIR/report.md"
