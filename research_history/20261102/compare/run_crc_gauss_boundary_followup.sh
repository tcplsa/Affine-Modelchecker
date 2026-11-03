#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
SCREEN_RESULTS="${CRC_GAUSS_BOUNDARY_RESULTS:-$TOOLS/results/pathb_crc_gauss_boundary_v1}"
OUTPUT="${CRC_GAUSS_BOUNDARY_CONFIRM_RESULTS:-$TOOLS/results/pathb_crc_gauss_boundary_1800_confirm_v1}"

until test -f "$SCREEN_RESULTS/gauss_180_report.md"; do
    sleep 30
done
mkdir -p "$OUTPUT"
for seed in 985011 985021; do
    python3 "$TOOLS/pathb/run_crc_gauss_pure_1800_confirm.py" \
        --manifest "$SCREEN_RESULTS/benchmarks/manifest.json" \
        --screen "$SCREEN_RESULTS/gauss_180.tsv" \
        --binary "$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker" \
        --output "$OUTPUT/seed${seed}.tsv" \
        --timeout 1800 --workers 4 --seed "$seed" \
        >"$OUTPUT/seed${seed}.log" 2>&1
done
