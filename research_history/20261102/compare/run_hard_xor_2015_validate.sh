#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCREEN="${SCRIPT_DIR}/results/mechanism_xor_hard2015_v1"
OUT="${SCRIPT_DIR}/results/mechanism_xor_hard2015_validate_v1"
GROUPS_FILE="${SCRIPT_DIR}/hwmcc2015_groups_xag_hard_promoted.json"
STATUS="${OUT}/status.tsv"
CORE_BUDGET="${HARD_XOR_CORE_BUDGET:-128}"
TIMEOUT="${HARD_XOR_VALIDATE_TIMEOUT:-1800}"

mkdir -p "${OUT}"
printf 'timestamp\tphase\tstatus\tdetail\n' > "${STATUS}"
status() {
    printf '%s\t%s\t%s\t%s\n' \
        "$(date -Iseconds)" "$1" "$2" "$3" >> "${STATUS}"
}
failed() {
    local code="$?"
    status "pipeline" "failed" "line=${LINENO} exit=${code}"
    exit "${code}"
}
trap failed ERR

status "promotion" "running" "${SCREEN}"
python3 "${SCRIPT_DIR}/build_hard_xor_promotion.py" \
    --screen-dir "${SCREEN}" \
    --year 2015 \
    --base-groups "${SCRIPT_DIR}/hwmcc2015_groups_xag_hard.json" \
    --output "${GROUPS_FILE}"
[[ -s "${GROUPS_FILE}" ]]
status "promotion" "completed" "${GROUPS_FILE}"

status "validation" "running" \
    "year=2015 group=screen_promote seeds=1..5 timeout=${TIMEOUT}"
python3 "${SCRIPT_DIR}/run_hard_xor_campaign.py" \
    --years 2015 \
    --group screen_promote \
    --groups-pattern "$(basename "${GROUPS_FILE}")" \
    --profile validate \
    --solver-seeds 1 2 3 4 5 \
    --timeout "${TIMEOUT}" \
    --core-budget "${CORE_BUDGET}" \
    --output-dir "${OUT}"
status "validation" "completed" "${OUT}"

results=("${OUT}"/hwmcc*_hardxor_s*.tsv)
status "analysis" "running" "hard 2015 long validation"
python3 "${SCRIPT_DIR}/analyze_mechanism_campaign.py" \
    --results "${results[@]}" \
    --output-dir "${OUT}/analysis" \
    --timeout-multiplier 1.5 \
    --min-gap 2 \
    --min-sample-span 2 \
    --metric wall
status "analysis" "completed" "${OUT}/analysis/report.md"
status "pipeline" "completed" "hard 2015 XOR validation"
