#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
BINARY="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker-variable-order-v1"
MANIFEST="$TOOLS/results/initial_cnf_final_holdout_design_v1/manifest.json"
OUTPUT="$TOOLS/results/variable_order_numeric_validation_v1/results.tsv"

cleanup() {
    pkill -TERM -P $$ 2>/dev/null || true
    wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

python3 "$TOOLS/run_variable_order_campaign.py" \
    --manifest "$MANIFEST" --binary "$BINARY" --output "$OUTPUT" \
    --configs aig_canonical-cnf,xag_canonical-cnf \
    --orders numeric --runs 4,5,6 \
    --workers "${NUMERIC_VALIDATION_WORKERS:-30}" \
    --lanes "${NUMERIC_VALIDATION_LANES:-4}" \
    --timeout "${NUMERIC_VALIDATION_TIMEOUT:-300}" \
    --seed-base 310000

trap - INT TERM EXIT
