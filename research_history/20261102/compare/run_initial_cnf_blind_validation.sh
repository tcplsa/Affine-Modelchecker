#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
COMPARE="$ROOT/test_tools/compare"
DESIGN="$COMPARE/results/initial_cnf_blind_validation_design_v1/manifest.json"
OUTDIR="$COMPARE/results/initial_cnf_blind_validation_v1"
BINARY="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker-initial-cnf-factorial"
RUNNER="$COMPARE/run_representation_simplification.py"
WORKERS="${INITIAL_CNF_WORKERS:-28}"
LANES="${INITIAL_CNF_LANES:-4}"
TIMEOUT="${INITIAL_CNF_TIMEOUT:-300}"

mkdir -p "$OUTDIR"
python3 "$COMPARE/build_initial_cnf_blind_validation.py"

cleanup() {
    pkill -TERM -P $$ 2>/dev/null || true
    wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

python3 "$RUNNER" \
    --manifest "$DESIGN" --binary "$BINARY" \
    --output "$OUTDIR/results_original.tsv" \
    --configs aig_native,xag_native --runs 1,2 \
    --workers "$WORKERS" --lanes "$LANES" --timeout "$TIMEOUT" \
    --input-order original

python3 "$RUNNER" \
    --manifest "$DESIGN" --binary "$BINARY" \
    --output "$OUTDIR/results_bad-last.tsv" \
    --configs xag_native --runs 1,2 \
    --workers "$WORKERS" --lanes "$LANES" --timeout "$TIMEOUT" \
    --input-order bad-last

python3 "$RUNNER" \
    --manifest "$DESIGN" --binary "$BINARY" \
    --output "$OUTDIR/results_fanout-desc.tsv" \
    --configs xag_precanonical --runs 1,2 \
    --workers "$WORKERS" --lanes "$LANES" --timeout "$TIMEOUT" \
    --input-order fanout-desc

trap - INT TERM EXIT
