#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RESULT_DIR=${RIC3_ORDER_CONCURRENT_RESULT_DIR:-$SCRIPT_DIR/results/ric3_order_concurrent_v1}
SEEDS=(1110001 1120001 1130001)
EXPECTED=556

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

python3 "$SCRIPT_DIR/analyze_ric3_order_concurrent.py" \
    --selection "$RESULT_DIR/selection.json" \
    --inputs "$RESULT_DIR/seed1110001.tsv" "$RESULT_DIR/seed1120001.tsv" "$RESULT_DIR/seed1130001.tsv" \
    --output "$RESULT_DIR/report.md"
