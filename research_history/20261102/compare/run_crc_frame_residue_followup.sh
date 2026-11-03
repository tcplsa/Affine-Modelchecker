#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
SCREEN_RESULTS="${CRC_RESIDUE_RESULTS:-$TOOLS/results/pathb_crc_frame_residue_v1}"
MANIFEST="$SCREEN_RESULTS/benchmarks/manifest.json"
SCREEN="$SCREEN_RESULTS/gauss_120.tsv"
OUTPUT="${CRC_RESIDUE_CONFIRM_RESULTS:-$TOOLS/results/pathb_crc_frame_residue_1800_confirm_v1}"

until test -f "$SCREEN_RESULTS/gauss_120_report.md"; do
    sleep 30
done

mkdir -p "$OUTPUT"
for seed in 984011 984021; do
    python3 "$TOOLS/pathb/run_affine_phase_sync_1800_confirm.py" \
        --manifest "$MANIFEST" \
        --screen "$SCREEN" \
        --binary "$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker" \
        --output "$OUTPUT/seed${seed}.tsv" \
        --timeout 1800 \
        --workers 4 \
        --seed "$seed" \
        >"$OUTPUT/seed${seed}.log" 2>&1
done
