#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
GRID="${PATHB_PHASE_SYNC_GRID:-$TOOLS/results/pathb_affine_phase_sync_1800_grid_v1}"
MANIFEST="${PATHB_PHASE_SYNC_MANIFEST:-$TOOLS/results/pathb_affine_phase_sync_v1/benchmarks/manifest.json}"
OUTPUT="${PATHB_PHASE_SYNC_CONFIRM_OUTPUT:-$TOOLS/results/pathb_affine_phase_sync_1800_confirm_v1}"
WORKERS="${PATHB_PHASE_SYNC_CONFIRM_WORKERS:-24}"

mkdir -p "$OUTPUT"
until grep -q '"cancelled"' "$GRID/run.log" 2>/dev/null; do
    sleep 60
done

for SEED in 840041 840051; do
    python3 "$TOOLS/pathb/run_affine_phase_sync_1800_confirm.py" \
        --manifest "$MANIFEST" \
        --screen "$GRID/results.tsv" \
        --binary "$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker" \
        --output "$OUTPUT/seed${SEED}.tsv" \
        --timeout 1800 \
        --workers "$WORKERS" \
        --seed "$SEED" \
        >"$OUTPUT/seed${SEED}.log" 2>&1
done
