#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 5 ]; then
    echo "usage: $0 MANIFEST SCREEN OUTPUT WORKERS SESSION_LABEL" >&2
    exit 2
fi

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
MANIFEST="$1"
SCREEN="$2"
OUTPUT="$3"
WORKERS="$4"
LABEL="$5"

mkdir -p "$OUTPUT"
for SEED in 840041 840051; do
    echo "label=$LABEL seed=$SEED"
    python3 "$TOOLS/pathb/run_affine_phase_sync_1800_confirm.py" \
        --manifest "$MANIFEST" \
        --screen "$SCREEN" \
        --binary "$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker" \
        --output "$OUTPUT/seed${SEED}.tsv" \
        --timeout 1800 \
        --workers "$WORKERS" \
        --seed "$SEED" \
        >"$OUTPUT/seed${SEED}.log" 2>&1
done
