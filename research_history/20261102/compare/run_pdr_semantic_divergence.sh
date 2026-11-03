#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
RESULTS="$TOOLS/results/pdr_semantic_divergence_v1"
MANIFEST="$TOOLS/results/initial_cnf_final_holdout_design_v1/manifest.json"
BINARY="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker-semantic-v1"

WORKERS=${PDR_SEMANTIC_WORKERS:-64}
TIMEOUT=${PDR_SEMANTIC_TIMEOUT:-45}
MAX_EVENTS=${PDR_SEMANTIC_MAX_EVENTS:-5000}

mkdir -p "$RESULTS"
python3 "$TOOLS/run_pdr_semantic_divergence.py" \
    --manifest "$MANIFEST" --binary "$BINARY" \
    --output "$RESULTS/summary.tsv" --trace-root "$RESULTS/traces" \
    --configs aig_canonical-cnf,xag_canonical-cnf \
    --origins first:first,numeric:first --run 4 --seed 350000 \
    --workers "$WORKERS" --timeout "$TIMEOUT" --max-events "$MAX_EVENTS" \
    --ctg-depth 1

python3 "$TOOLS/analyze_pdr_semantic_divergence.py" \
    --summary "$RESULTS/summary.tsv" --trace-root "$RESULTS/traces" \
    --output "$RESULTS/semantic_divergence_report.md"
