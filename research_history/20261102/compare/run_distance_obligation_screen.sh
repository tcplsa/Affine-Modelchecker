#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
COMPARE="$ROOT/test_tools/compare"
RESULTS="$COMPARE/results/mc_distance_obligation_screen_v1"
MANIFEST="$COMPARE/results/mc_hard_breakthrough_screen_v1/diagnostic_progress_candidates.json"
BINARY="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker"
WAIT_SESSION="${WAIT_SESSION:-distance_mic_auto}"

mkdir -p "$RESULTS"

if [[ -n "$WAIT_SESSION" ]]; then
    while tmux has-session -t "$WAIT_SESSION" 2>/dev/null; do
        sleep 30
    done
fi

for strategy in obligation-source-near obligation-source-far obligation-mixed; do
    python3 "$COMPARE/run_mc_hard_diagnostic.py" \
        --manifest "$MANIFEST" \
        --binary "$BINARY" \
        --output "$RESULTS/$strategy.tsv" \
        --timeout 600 \
        --workers 12 \
        --seed 730001 \
        --strategy "$strategy"
done

python3 "$COMPARE/analyze_distance_obligation_screen.py" \
    --baseline "$COMPARE/results/mc_distance_mic_screen_v1/baseline.tsv" \
    --results "$RESULTS" \
    --output "$RESULTS/report.md"
