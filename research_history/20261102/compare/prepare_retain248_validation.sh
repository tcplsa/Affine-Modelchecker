#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${RETAIN248_DESIGN:-${SCRIPT_DIR}/results/retain248_validation_design_v1}"

python3 "${SCRIPT_DIR}/build_retain248_validation_design.py" \
    --output-dir "${OUT}" \
    --years "${RETAIN248_YEARS:-2024,2025}" \
    --hard-per-year "${RETAIN248_HARD_PER_YEAR:-80}" \
    --feature-workers "${RETAIN248_FEATURE_WORKERS:-4}"

echo "prepared ${OUT}"
