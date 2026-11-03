#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESIGN="${XOR_REFINEMENT_DESIGN_OUT:-${SCRIPT_DIR}/results/xor_refinement_phase5_design_v1}"
OUT="${XOR_REFINEMENT_ANALYSIS_OUT:-${SCRIPT_DIR}/results/xor_refinement_phase5_analysis_v1}"

if [[ -n "${XOR_REFINEMENT_RESULT_DIRS:-}" ]]; then
    read -r -a RESULT_DIRS <<< "${XOR_REFINEMENT_RESULT_DIRS}"
else
    RESULT_DIRS=(
        "${SCRIPT_DIR}/results/xor_refinement_phase5_server-a_train_v1"
        "${SCRIPT_DIR}/results/xor_refinement_phase5_server-b_train_v1"
    )
fi
for directory in "${RESULT_DIRS[@]}"; do
    [[ -d "${directory}" ]]
done

mkdir -p "${OUT}"
for context in add retain; do
    mapfile -t results < <(find "${RESULT_DIRS[@]}" -maxdepth 1 \
        -type f -name "${context}_*_run*.tsv" | sort)
    if [[ ${#results[@]} -eq 0 ]]; then
        echo "no ${context} result files" >&2
        exit 1
    fi
    python3 "${SCRIPT_DIR}/analyze_xor_shapley.py" \
        --manifest "${DESIGN}/manifest_${context}.json" \
        --results "${results[@]}" \
        --output-dir "${OUT}/${context}" \
        --timeout-multiplier "${XOR_REFINEMENT_TIMEOUT_MULTIPLIER:-1.5}" \
        --min-effect "${XOR_REFINEMENT_MIN_EFFECT:-2}"
done

mapfile -t add_results < <(find "${RESULT_DIRS[@]}" -maxdepth 1 \
    -type f -name 'add_*_run*.tsv' | sort)
mapfile -t retain_results < <(find "${RESULT_DIRS[@]}" -maxdepth 1 \
    -type f -name 'retain_*_run*.tsv' | sort)
python3 "${SCRIPT_DIR}/analyze_xor_refinement.py" \
    --add-manifest "${DESIGN}/manifest_add.json" \
    --retain-manifest "${DESIGN}/manifest_retain.json" \
    --add-results "${add_results[@]}" \
    --retain-results "${retain_results[@]}" \
    --output-dir "${OUT}" \
    --timeout-multiplier "${XOR_REFINEMENT_TIMEOUT_MULTIPLIER:-1.5}" \
    --min-effect "${XOR_REFINEMENT_MIN_EFFECT:-2}"

echo "analysis: ${OUT}/report.md"
