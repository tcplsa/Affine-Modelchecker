#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RESULT_DIR=${RIC3_HARD_3600_OUTPUT_DIR:-$SCRIPT_DIR/results/ric3_hard_3600_v1}
SOURCE_MANIFEST=${RIC3_HARD_3600_SOURCE_MANIFEST:-$SCRIPT_DIR/results/full_aig_xag_all_years_v1/manifest.json}
CANDIDATES=${RIC3_HARD_3600_MANIFEST:-$RESULT_DIR/candidates_1800.json}
BINARY=${RIC3_HARD_3600_BINARY:-/home/wudl/rIC3-stock-7149d56/target/release/ric3}
WORKERS=${RIC3_HARD_3600_WORKERS:-28}
TIMEOUT=${RIC3_HARD_3600_TIMEOUT:-3600}
OUTPUT=${RIC3_HARD_3600_OUTPUT:-$RESULT_DIR/stock_ric3_3600.tsv}

mkdir -p "$RESULT_DIR"

python3 "$SCRIPT_DIR/build_ric3_hard_3600_manifest.py" \
    --source-manifest "$SOURCE_MANIFEST" \
    --result "$SCRIPT_DIR/results/bve_full_campaign_v1/ric3_shard_0_of_3.tsv" \
    --result "$SCRIPT_DIR/results/bve_full_campaign_v1/ric3_shard_1_of_3.tsv" \
    --result "$SCRIPT_DIR/results/bve_full_campaign_v1/ric3_shard_2_of_3.tsv" \
    --output "$CANDIDATES"

python3 "$SCRIPT_DIR/run_ric3_hard_3600.py" \
    --manifest "$CANDIDATES" \
    --binary "$BINARY" \
    --output "$OUTPUT" \
    --workers "$WORKERS" \
    --timeout "$TIMEOUT"

python3 "$SCRIPT_DIR/analyze_ric3_hard_3600.py" \
    --manifest "$CANDIDATES" \
    --result "$OUTPUT" \
    --output-dir "$RESULT_DIR/analysis"
