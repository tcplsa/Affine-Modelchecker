#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RESULT_DIR=${MC_SUMHIGH_RESULT_DIR:-$SCRIPT_DIR/results/mc_sumhigh_concurrent_v1}
SEEDS=(1260001 1270001 1280001)
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

python3 -S "$SCRIPT_DIR/analyze_mc_sumhigh_concurrent.py" \
    --inputs "$RESULT_DIR/seed1260001.tsv" "$RESULT_DIR/seed1270001.tsv" \
    "$RESULT_DIR/seed1280001.tsv" --output "$RESULT_DIR/report.md"
