#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${XOR_PAIRED_DESIGN:-${SCRIPT_DIR}/results/xor_paired_causal_design_v1}"
python3 "${SCRIPT_DIR}/build_xor_paired_causal_design.py" \
    --source-manifest "${SCRIPT_DIR}/results/retain248_validation_design_v1/manifest.json" \
    --output-dir "${OUT}"
