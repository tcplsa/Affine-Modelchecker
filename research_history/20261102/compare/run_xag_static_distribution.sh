#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${XAG_STATIC_OUT:-${SCRIPT_DIR}/results/xag_static_distribution_v1}"
STATUS="${OUT}/status.tsv"
WORKERS="${XAG_STATIC_WORKERS:-24}"
SUPPORT_LIMIT="${XAG_STATIC_SUPPORT_LIMIT:-128}"
FEATURES="${OUT}/xor_distribution_features.tsv"

mkdir -p "${OUT}"
printf 'timestamp\tphase\tstatus\tdetail\n' > "${STATUS}"
status() {
    printf '%s\t%s\t%s\t%s\n' "$(date -Iseconds)" "$1" "$2" "$3" >> "${STATUS}"
}
failed() {
    local code="$?"
    status "pipeline" "failed" "line=${BASH_LINENO[0]} exit=${code}"
    exit "${code}"
}
trap failed ERR

status "pipeline" "running" "pre-PDR static feature experiment"
status "features" "running" "workers=${WORKERS} support_limit=${SUPPORT_LIMIT}"
python3 "${SCRIPT_DIR}/extract_xor_distribution_features.py" \
    --results-pattern "${SCRIPT_DIR}/results/initial_state_large/hwmcc*.tsv" \
    --structure-files \
        "${SCRIPT_DIR}/results/xag_struct_2015.tsv" \
        "${SCRIPT_DIR}/results/xag_struct_2017.tsv" \
        "${SCRIPT_DIR}/results/xag_struct_2019.tsv" \
        "${SCRIPT_DIR}/results/xag_struct_2020.tsv" \
    --output "${FEATURES}" \
    --workers "${WORKERS}" \
    --support-limit "${SUPPORT_LIMIT}"
status "features" "completed" "${FEATURES}"

status "selector" "running" "family CV + year holdout + seed transfer"
python3 "${SCRIPT_DIR}/fit_xag_distribution_selector.py" \
    --results-pattern "${SCRIPT_DIR}/results/initial_state_large/hwmcc*.tsv" \
    --coarse-features \
        "${SCRIPT_DIR}/results/xag_struct_2015.tsv" \
        "${SCRIPT_DIR}/results/xag_struct_2017.tsv" \
        "${SCRIPT_DIR}/results/xag_struct_2019.tsv" \
        "${SCRIPT_DIR}/results/xag_struct_2020.tsv" \
    --distribution-features "${FEATURES}" \
    --output-dir "${OUT}/analysis" \
    --timeout-multiplier 1.5 \
    --min-span 1 \
    --max-depth 4 \
    --min-leaf 20 \
    --folds 5
status "selector" "completed" "${OUT}/analysis/report.md"
status "pipeline" "completed" "static XAG selector experiment"

