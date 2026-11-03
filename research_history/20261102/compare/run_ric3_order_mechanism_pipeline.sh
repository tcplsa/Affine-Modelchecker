#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PERF_DIR="$SCRIPT_DIR/results/ric3_order_concurrent_v1"
RESULT_DIR="$SCRIPT_DIR/results/ric3_order_mechanism_v1"
SEEDS=(1110001 1120001 1130001)
EXPECTED=556

while true; do
    complete=1
    for seed in "${SEEDS[@]}"; do
        path="$PERF_DIR/seed${seed}.tsv"
        if [[ ! -f "$path" || -d "${path}.lock" ]]; then
            complete=0
            break
        fi
        rows=$(awk 'END { print NR > 0 ? NR - 1 : 0 }' "$path")
        if [[ "$rows" -ne "$EXPECTED" ]]; then
            complete=0
            break
        fi
    done
    if [[ "$complete" -eq 1 ]]; then
        break
    fi
    sleep 60
done

mkdir -p "$RESULT_DIR"
python3 "$SCRIPT_DIR/analyze_ric3_order_concurrent.py" \
    --selection "$PERF_DIR/selection.json" \
    --inputs "$PERF_DIR/seed1110001.tsv" "$PERF_DIR/seed1120001.tsv" "$PERF_DIR/seed1130001.tsv" \
    --output "$PERF_DIR/report.md"

python3 "$SCRIPT_DIR/build_ric3_order_mechanism_selection.py" \
    --selection "$PERF_DIR/selection.json" \
    --inputs "$PERF_DIR/seed1110001.tsv" "$PERF_DIR/seed1120001.tsv" "$PERF_DIR/seed1130001.tsv" \
    --output "$RESULT_DIR/selection.json"

cd /home/wudl/rIC3
cargo build --release --bin ric3
cp target/release/ric3 target/release/ric3-bve-telemetry-v1

python3 "$SCRIPT_DIR/run_ric3_order_concurrent.py" \
    --manifest "$SCRIPT_DIR/results/full_aig_xag_all_years_v1/manifest.json" \
    --selection "$RESULT_DIR/selection.json" \
    --binary /home/wudl/rIC3/target/release/ric3-bve-telemetry-v1 \
    --output "$RESULT_DIR/results.tsv" \
    --seed 1140001 --workers 60 --replicas 1 --timeout 120 --collect-stats

python3 "$SCRIPT_DIR/analyze_ric3_order_mechanism.py" \
    --selection "$RESULT_DIR/selection.json" \
    --input "$RESULT_DIR/results.tsv" \
    --output "$RESULT_DIR/report.md"
