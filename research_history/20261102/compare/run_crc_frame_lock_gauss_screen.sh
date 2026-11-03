#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
RESULTS="${CRC_LOCK_RESULTS:-$TOOLS/results/pathb_crc_frame_lock_v1}"
SPECS="${CRC_LOCK_SPECS:-$TOOLS/pathb_crc_frame_lock_specs_v1.json}"
BENCHMARKS="$RESULTS/benchmarks"

mkdir -p "$RESULTS"
python3 "$TOOLS/pathb/generate.py" manifest \
    --manifest "$SPECS" \
    --out "$BENCHMARKS"
python3 "$TOOLS/pathb/validate_semantic_suite.py" \
    --specs "$SPECS" \
    --manifest "$BENCHMARKS/manifest.json" \
    --trials 8 --steps 32
python3 "$TOOLS/pathb/run_mc_gauss_single_sweep.py" \
    --manifest "$BENCHMARKS/manifest.json" \
    --binary "$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker" \
    --output "$RESULTS/gauss_120.tsv" \
    --timeout "${CRC_LOCK_TIMEOUT:-120}" \
    --workers "${CRC_LOCK_WORKERS:-8}" \
    --seed "${CRC_LOCK_SEED:-983001}"
python3 "$TOOLS/pathb/analyze_semantic_gauss_screen.py" \
    --input "$RESULTS/gauss_120.tsv" \
    --report "$RESULTS/gauss_120_report.md"
