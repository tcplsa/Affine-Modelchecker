#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
RESULTS="$TOOLS/results/pathb_affine_phase_sync_ric3_stock_1800_v1"

until [ "$(wc -l < "$RESULTS/seed850001.tsv" 2>/dev/null || echo 0)" -ge 12 ]; do
    sleep 60
done

python3 "$TOOLS/pathb/build_ric3_timeout_selection.py" \
    --selection "$RESULTS/selection.json" \
    --result "$RESULTS/seed850001.tsv" \
    --output "$RESULTS/rerun_selection.json" \
    >"$RESULTS/rerun_selection.log" 2>&1

if ! rg -q '"id"' "$RESULTS/rerun_selection.json"; then
    echo "no first-run rIC3 timeouts" >"$RESULTS/seed850011.log"
    exit 0
fi

python3 "$TOOLS/run_ric3_hard_3600.py" \
    --manifest "$RESULTS/rerun_selection.json" \
    --binary "$ROOT/rIC3-stock-7149d56/target/release/ric3" \
    --output "$RESULTS/seed850011.tsv" \
    --workers 11 \
    --timeout 1800 \
    --seed 850011 \
    >"$RESULTS/seed850011.log" 2>&1
