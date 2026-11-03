#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl/test_tools/compare
RESULTS="$ROOT/results/ric3_aa_noise_v1"
MANIFEST="$ROOT/results/full_aig_xag_all_years_v1/manifest.json"
SOURCE="$ROOT/results/ric3_order_concurrent_v1/seed*.tsv"
SELECTION="$RESULTS/selection.json"
BINARY=/home/wudl/rIC3/target/release/ric3

mkdir -p "$RESULTS"
python3 "$ROOT/build_ric3_aa_noise_selection.py" \
  --input-glob "$SOURCE" --output "$SELECTION"

for repeat in 1 2 3; do
  python3 "$ROOT/run_ric3_aa_noise.py" \
    --manifest "$MANIFEST" \
    --selection "$SELECTION" \
    --binary "$BINARY" \
    --output "$RESULTS/repeat${repeat}.tsv" \
    --seed 1900001 \
    --workers 1 \
    --timeout 300
done

python3 "$ROOT/analyze_ric3_aa_noise.py" \
  --input-glob "$RESULTS/repeat*.tsv" \
  --output "$RESULTS/report.md"
