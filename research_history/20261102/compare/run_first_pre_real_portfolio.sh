#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
RESULTS="$TOOLS/results/first_pre_real_portfolio_v1"
MANIFEST="$TOOLS/results/initial_cnf_final_holdout_design_v1/manifest.json"
BINARY="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker-first-pre-portfolio-v1"

mkdir -p "$RESULTS"
python3 "$TOOLS/run_first_pre_real_portfolio.py" \
    --manifest "$MANIFEST" --binary "$BINARY" \
    --output "$RESULTS/results.tsv" \
    --workers "${FIRST_PRE_PORTFOLIO_WORKERS:-3}" \
    --timeout "${FIRST_PRE_PORTFOLIO_TIMEOUT:-45}"
python3 "$TOOLS/analyze_first_pre_real_portfolio.py" \
    --input "$RESULTS/results.tsv" --output "$RESULTS/report.md"
