#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
SCREEN="$TOOLS/results/mc_hard_breakthrough_screen_v1"
RESULTS="$TOOLS/results/mc_hard_breakthrough_confirm_v1"
BINARY="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker"
TIMEOUT=${HARD_CONFIRM_TIMEOUT:-3600}

mkdir -p "$RESULTS"
python3 "$TOOLS/build_hard_breakthrough_confirmation.py" \
    --results "$SCREEN" \
    --manifest "$SCREEN/candidates.json" \
    --output-dir "$RESULTS/manifests"

python3 "$TOOLS/run_mc_hard_diagnostic.py" \
    --manifest "$RESULTS/manifests/baseline.json" \
    --binary "$BINARY" --output "$RESULTS/baseline.tsv" \
    --timeout "$TIMEOUT" --workers 2 --seed 730001 --strategy baseline

for manifest in "$RESULTS"/manifests/*.json; do
    strategy=$(basename "$manifest" .json)
    [[ "$strategy" == baseline ]] && continue
    for repeat in 1 2; do
        python3 "$TOOLS/run_mc_hard_diagnostic.py" \
            --manifest "$manifest" \
            --binary "$BINARY" --output "$RESULTS/${strategy}_r${repeat}.tsv" \
            --timeout "$TIMEOUT" --workers 1 --seed 730001 --strategy "$strategy"
    done
done

touch "$RESULTS/complete"
echo "hard breakthrough confirmation complete"
