#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${RETAIN248_ANALYSIS_OUT:-${SCRIPT_DIR}/results/retain248_validation_analysis_v1}"
INPUT_A="${RETAIN248_INPUT_A:-${SCRIPT_DIR}/results/retain248_validation_server-a_v1/results.tsv}"
INPUT_B="${RETAIN248_INPUT_B:-${SCRIPT_DIR}/results/retain248_validation_server-b_v1/results.tsv}"

python3 "${SCRIPT_DIR}/analyze_retain248_validation.py" \
    "${INPUT_A}" "${INPUT_B}" \
    --output-dir "${OUT}" \
    --neutral-seconds "${RETAIN248_NEUTRAL_SECONDS:-2}" \
    --timeout-penalty "${RETAIN248_TIMEOUT_PENALTY:-1.5}"
