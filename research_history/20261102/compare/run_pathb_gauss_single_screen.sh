#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
RESULTS="${PATHB_GAUSS_RESULTS:-$TOOLS/results/pathb_gauss_single_v1}"
BENCHMARKS="$RESULTS/benchmarks"
SPECS="${PATHB_GAUSS_SPECS:-$TOOLS/pathb_gauss_single_specs_v1.json}"

mkdir -p "$RESULTS"
python3 "$TOOLS/pathb/generate.py" manifest \
    --manifest "$SPECS" \
    --out "$BENCHMARKS"
python3 "$TOOLS/pathb/run_mc_gauss_single_sweep.py" \
    --manifest "$BENCHMARKS/manifest.json" \
    --binary "$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker" \
    --output "$RESULTS/results.tsv" \
    --timeout "${PATHB_GAUSS_TIMEOUT:-120}" \
    --workers "${PATHB_GAUSS_WORKERS:-8}" \
    --seed "${PATHB_GAUSS_SEED:-840001}"
