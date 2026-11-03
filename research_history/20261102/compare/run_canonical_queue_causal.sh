#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
COMPARE="$ROOT/test_tools/compare"
DESIGN="$COMPARE/results/initial_cnf_final_holdout_design_v1/manifest.json"
OUTDIR="$COMPARE/results/canonical_queue_causal_v1"
BINARY="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker-canonical-causal"

cleanup() {
    pkill -TERM -P $$ 2>/dev/null || true
    wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

mkdir -p "$OUTDIR"
export MC_PDR_CADICAL_REVERSE=1
python3 "$COMPARE/run_representation_simplification.py" \
    --manifest "$DESIGN" --binary "$BINARY" \
    --output "$OUTDIR/results_reverse.tsv" \
    --configs xag_native,xag_canonical-cnf --runs 1,2 \
    --workers "${INITIAL_CNF_WORKERS:-28}" \
    --lanes "${INITIAL_CNF_LANES:-4}" \
    --timeout "${INITIAL_CNF_TIMEOUT:-300}" \
    --input-order original

trap - INT TERM EXIT
