#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
WORKERS=${CNF_FACTORIAL_WORKERS:-28}
LANES=${CNF_FACTORIAL_LANES:-4}
TIMEOUT=${CNF_FACTORIAL_TIMEOUT:-300}
RUNS=${CNF_FACTORIAL_RUNS:-1,2}
BINARY=${CNF_FACTORIAL_BINARY:-$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker-initial-cnf-factorial}
MANIFEST=${CNF_FACTORIAL_MANIFEST:-$ROOT/test_tools/compare/results/initial_cnf_factorial_design_v1/manifest.json}
OUT_DIR=${CNF_FACTORIAL_OUT_DIR:-$ROOT/test_tools/compare/results/initial_cnf_factorial_v1}
CONFIGS=aig_native,xag_native,aig_raw,xag_raw,aig_precanonical,xag_precanonical

mkdir -p "$OUT_DIR"
for order in original fanout-asc fanout-desc bad-last; do
  python3 "$ROOT/test_tools/compare/run_representation_simplification.py" \
    --manifest "$MANIFEST" \
    --binary "$BINARY" \
    --output "$OUT_DIR/results_${order}.tsv" \
    --shard all \
    --configs "$CONFIGS" \
    --runs "$RUNS" \
    --workers "$WORKERS" \
    --lanes "$LANES" \
    --timeout "$TIMEOUT" \
    --input-order "$order"
done
