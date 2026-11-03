#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/analyze_xor_paired_causal.py" \
    "${SCRIPT_DIR}/results/xor_paired_causal_server-a_v1/results.tsv" \
    "${SCRIPT_DIR}/results/xor_paired_causal_server-b_v1/results.tsv" \
    --manifest "${SCRIPT_DIR}/results/xor_paired_causal_design_v1/manifest.json" \
    --output-dir "${SCRIPT_DIR}/results/xor_paired_causal_analysis_v1" \
    --timeout-penalty 1.5 --neutral-seconds 2
