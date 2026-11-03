#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
RESULTS="$TOOLS/results/first_pre_phase_v1"
MANIFEST="$TOOLS/results/initial_cnf_final_holdout_design_v1/manifest.json"
BINARY="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker-first-pre-phase-v1"

mkdir -p "$RESULTS"
python3 "$TOOLS/run_first_pre_phase_experiment.py" \
    --manifest "$MANIFEST" --binary "$BINARY" \
    --output "$RESULTS/results.tsv" --trace-root "$RESULTS/.trace_tmp" \
    --workers "${FIRST_PRE_WORKERS:-64}" \
    --timeout "${FIRST_PRE_TIMEOUT:-45}" \
    --random-seeds "${FIRST_PRE_RANDOM_SEEDS:-1,2,3,4,5,6,7,8}"

python3 "$TOOLS/analyze_first_pre_phase_experiment.py" \
    --input "$RESULTS/results.tsv" --output "$RESULTS/report.md"
