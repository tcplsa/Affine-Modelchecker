#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
RESULTS="$TOOLS/results/source_directed_portfolio_v1"
MANIFEST="$TOOLS/results/initial_cnf_final_holdout_design_v1/manifest.json"
BINARY="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker-predecessor-phase-v1"

mkdir -p "$RESULTS"
python3 "$TOOLS/run_source_directed_portfolio.py" \
    --manifest "$MANIFEST" --binary "$BINARY" \
    --output "$RESULTS/results.tsv" \
    --workers "${SOURCE_PHASE_MODEL_WORKERS:-6}" \
    --timeout "${SOURCE_PHASE_TIMEOUT:-45}"
python3 "$TOOLS/analyze_source_directed_portfolio.py" \
    --input "$RESULTS/results.tsv" --manifest "$MANIFEST" \
    --output "$RESULTS/report.md"
