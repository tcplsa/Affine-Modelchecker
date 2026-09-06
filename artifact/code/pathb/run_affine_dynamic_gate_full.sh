#!/usr/bin/env bash
set -euo pipefail

ROOT=${ROOT:-/home/wudl}
COMPARE="$ROOT/test_tools/compare"
MANIFEST=${MANIFEST:-$COMPARE/results/pathb_affine_full_scope_v1/manifest.json}
BINARY=${BINARY:-$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker-gauss-auto-v1}
OUT_DIR=${OUT_DIR:-$COMPARE/results/pathb_affine_dynamic_gate_full_v1}
TIMEOUT=${TIMEOUT:-600}
WORKERS=${WORKERS:-16}

mkdir -p "$OUT_DIR"

for seed in 998101 998102; do
    python3 "$COMPARE/pathb/run_affine_dynamic_gate.py" \
        --manifest "$MANIFEST" \
        --binary "$BINARY" \
        --output "$OUT_DIR/seed${seed}.tsv" \
        --timeout "$TIMEOUT" \
        --workers "$WORKERS" \
        --seed "$seed"
done

python3 "$COMPARE/pathb/analyze_affine_dynamic_gate_full.py" \
    "$OUT_DIR/seed998101.tsv" "$OUT_DIR/seed998102.tsv" \
    --output "$OUT_DIR/report.md"
