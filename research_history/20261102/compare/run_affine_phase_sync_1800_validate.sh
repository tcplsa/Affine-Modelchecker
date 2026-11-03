#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
MANIFEST="$TOOLS/results/pathb_affine_phase_sync_v1/benchmarks/manifest.json"
OUTPUT_ROOT="${PATHB_PHASE_SYNC_1800_RESULTS:-$TOOLS/results/pathb_affine_phase_sync_1800_validate_v1}"
TIMEOUT="${PATHB_PHASE_SYNC_1800_TIMEOUT:-1800}"
WORKERS="${PATHB_PHASE_SYNC_1800_WORKERS:-5}"

mkdir -p "$OUTPUT_ROOT"
for SEED in 840011 840021; do
    python3 "$TOOLS/pathb/run_affine_phase_sync_1800_validate.py" \
        --manifest "$MANIFEST" \
        --binary "$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker" \
        --output "$OUTPUT_ROOT/seed${SEED}.tsv" \
        --timeout "$TIMEOUT" \
        --workers "$WORKERS" \
        --seed "$SEED" \
        >"$OUTPUT_ROOT/seed${SEED}.log" 2>&1
done
