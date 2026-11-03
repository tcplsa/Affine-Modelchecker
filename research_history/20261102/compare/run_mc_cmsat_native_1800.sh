#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
RESULTS="${MC_CMSAT_RESULTS:-$TOOLS/results/mc_cmsat_native_1800_v1}"

python3 "$TOOLS/run_mc_cmsat_native_screen.py" \
    --atlas "$TOOLS/results/mc_ric3_hard_gap_v1/global_labels/dynamic_model_atlas.tsv" \
    --binary "$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker" \
    --output "$RESULTS/results.tsv" \
    --manifest "$RESULTS/manifest.json" \
    --timeout "${MC_CMSAT_TIMEOUT:-1800}" \
    --workers "${MC_CMSAT_WORKERS:-8}" \
    --seed "${MC_CMSAT_SEED:-840001}" \
    --suite "${MC_CMSAT_SUITE:-native-one}" \
    --progress-seconds 60
