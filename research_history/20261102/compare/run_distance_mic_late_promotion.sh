#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
SCREEN="$TOOLS/results/mc_distance_mic_screen_v1"
RESULTS="$TOOLS/results/mc_distance_mic_promotion_v1"
MODEL_ID=2019__ponylink-slaveTXlen-sat

for strategy in baseline mic-mixed; do
    python3 "$TOOLS/run_mc_hard_diagnostic.py" \
        --manifest "$SCREEN/promotion_candidates.json" \
        --model-id "$MODEL_ID" \
        --binary "$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker" \
        --output "$RESULTS/${strategy}-ponylink.tsv" \
        --timeout 3600 \
        --workers 1 \
        --seed 730001 \
        --strategy "$strategy"
done
