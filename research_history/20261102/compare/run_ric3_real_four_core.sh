#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
RESULTS="$TOOLS/results/ric3_real_four_core_v2"
MANIFEST="$TOOLS/results/initial_cnf_final_holdout_design_v1/manifest.json"
BINARY="$ROOT/rIC3/target/release/ric3-real-four-core-v2"

mkdir -p "$RESULTS"
python3 "$TOOLS/run_ric3_real_four_core.py" \
    --manifest "$MANIFEST" --binary "$BINARY" \
    --output "$RESULTS/results.tsv" \
    --workers "${RIC3_REAL4_MODEL_WORKERS:-9}" \
    --timeout "${RIC3_REAL4_TIMEOUT:-45}"
python3 "$TOOLS/analyze_ric3_real_four_core.py" \
    --input "$RESULTS/results.tsv" --output "$RESULTS/report.md" \
    --manifest "$MANIFEST"
