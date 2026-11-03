#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
RESULTS="$TOOLS/results/ric3_four_core_baseline_v1"
MANIFEST="$TOOLS/results/initial_cnf_final_holdout_design_v1/manifest.json"
BINARY="$ROOT/rIC3/target/release/ric3-four-core-baseline-v1"

mkdir -p "$RESULTS"
python3 "$TOOLS/run_ric3_four_core_baseline.py" \
    --manifest "$MANIFEST" --binary "$BINARY" \
    --output "$RESULTS/results.tsv" \
    --workers "${RIC3_BASELINE_MODEL_WORKERS:-6}" \
    --timeout "${RIC3_BASELINE_TIMEOUT:-45}"

python3 "$TOOLS/analyze_ric3_four_core_baseline.py" \
    --input "$RESULTS/results.tsv" --output "$RESULTS/report.md"
