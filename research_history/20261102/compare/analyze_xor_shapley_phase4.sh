#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESIGN="${XOR_SHAPLEY_DESIGN_OUT:-${SCRIPT_DIR}/results/xor_shapley_phase4_design_v1}"
BENEFIT="${XOR_SHAPLEY_BENEFIT_OUT:-${SCRIPT_DIR}/results/xor_shapley_phase4_benefit_v1}"
HARM="${XOR_SHAPLEY_HARM_OUT:-${SCRIPT_DIR}/results/xor_shapley_phase4_harm_v1}"
OUT="${XOR_SHAPLEY_ANALYSIS_OUT:-${SCRIPT_DIR}/results/xor_shapley_phase4_analysis_v1}"

results=("${BENEFIT}"/benefit_seed*.tsv "${HARM}"/harm_seed*.tsv)
for result in "${results[@]}"; do
    [[ -s "${result}" ]]
done
python3 "${SCRIPT_DIR}/analyze_xor_shapley.py" \
    --manifest "${DESIGN}/manifest.json" \
    --results "${results[@]}" \
    --output-dir "${OUT}" \
    --timeout-multiplier 1.5 \
    --min-effect 2
echo "analysis: ${OUT}/report.md"
