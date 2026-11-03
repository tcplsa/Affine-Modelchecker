#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RESULT_DIR="$SCRIPT_DIR/results/ric3_phase_order_screen_v1"
EXPECTED=(186 185 185)

while true; do
    complete=1
    for shard in 0 1 2; do
        path="$RESULT_DIR/shard${shard}_of_3.tsv"
        if [[ ! -f "$path" || -d "${path}.lock" ]]; then
            complete=0
            break
        fi
        rows=$(awk 'END { print NR > 0 ? NR - 1 : 0 }' "$path")
        if [[ "$rows" -ne "${EXPECTED[$shard]}" ]]; then
            complete=0
            break
        fi
    done
    if [[ "$complete" -eq 1 ]]; then
        break
    fi
    sleep 60
done

python3 "$SCRIPT_DIR/analyze_ric3_phase_order_screen.py" \
    --inputs "$RESULT_DIR/shard0_of_3.tsv" "$RESULT_DIR/shard1_of_3.tsv" "$RESULT_DIR/shard2_of_3.tsv" \
    --output "$RESULT_DIR/report.md"
