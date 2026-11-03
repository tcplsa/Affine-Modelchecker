#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
RESULTS="${CRC_GAUSS_FINE_RESULTS:-$TOOLS/results/pathb_crc_gauss_boundary_fine_v1}"
SPECS="$TOOLS/pathb_crc_gauss_boundary_fine_specs_v1.json"
BENCHMARKS="$RESULTS/benchmarks"

mkdir -p "$RESULTS"
python3 "$TOOLS/pathb/build_crc_gauss_boundary_fine_suite.py" --output "$SPECS"
python3 "$TOOLS/pathb/generate.py" manifest --manifest "$SPECS" --out "$BENCHMARKS"
python3 "$TOOLS/pathb/validate_semantic_suite.py" \
    --specs "$SPECS" --manifest "$BENCHMARKS/manifest.json" --trials 6 --steps 24
python3 "$TOOLS/pathb/run_mc_gauss_single_sweep.py" \
    --manifest "$BENCHMARKS/manifest.json" \
    --binary "$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker" \
    --output "$RESULTS/gauss_180.tsv" \
    --timeout "${CRC_GAUSS_FINE_TIMEOUT:-180}" \
    --workers "${CRC_GAUSS_FINE_WORKERS:-8}" \
    --seed "${CRC_GAUSS_FINE_SEED:-986001}"
python3 "$TOOLS/pathb/analyze_semantic_gauss_screen.py" \
    --input "$RESULTS/gauss_180.tsv" --report "$RESULTS/gauss_180_report.md"
