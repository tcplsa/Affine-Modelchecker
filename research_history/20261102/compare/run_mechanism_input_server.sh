#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${SCRIPT_DIR}/results/mechanism_input_v1"
STATUS="${OUT}/status.tsv"
CORE_BUDGET="${MECH_CORE_BUDGET:-128}"
TRANSFORM_SEEDS="${MECH_TRANSFORM_SEEDS:-1,2,3,4,5,6,7,8}"

mkdir -p "${OUT}"
printf 'timestamp\tphase\tstatus\tdetail\n' > "${STATUS}"
failed() {
    local code="$?"
    printf '%s\t%s\t%s\t%s\n' \
        "$(date -Iseconds)" "pipeline" "failed" \
        "line=${LINENO} exit=${code}" >> "${STATUS}"
    exit "${code}"
}
trap failed ERR

printf '%s\t%s\t%s\t%s\n' \
    "$(date -Iseconds)" "input_campaign" "running" \
    "solver_seeds=1..5 transform_seeds=${TRANSFORM_SEEDS}" >> "${STATUS}"
python3 "${SCRIPT_DIR}/run_mechanism_campaign.py" \
    --axis input \
    --years 2015 2017 2019 2020 \
    --tiers fast_unique medium_unique slow_unique \
    --solver-seeds 1 2 3 4 5 \
    --transform-seeds "${TRANSFORM_SEEDS}" \
    --core-budget "${CORE_BUDGET}" \
    --output-dir "${OUT}"
printf '%s\t%s\t%s\t%s\n' \
    "$(date -Iseconds)" "input_campaign" "completed" "${OUT}" >> "${STATUS}"

results=("${OUT}"/hwmcc*_input_s*.tsv)
printf '%s\t%s\t%s\t%s\n' \
    "$(date -Iseconds)" "analysis" "running" \
    "controlled input ordering" >> "${STATUS}"
python3 "${SCRIPT_DIR}/analyze_mechanism_campaign.py" \
    --results "${results[@]}" \
    --output-dir "${OUT}/analysis" \
    --timeout-multiplier 1.5 \
    --min-gap 1 \
    --min-sample-span 1 \
    --metric algorithm
printf '%s\t%s\t%s\t%s\n' \
    "$(date -Iseconds)" "analysis" "completed" \
    "${OUT}/analysis/report.md" >> "${STATUS}"
printf '%s\t%s\t%s\t%s\n' \
    "$(date -Iseconds)" "pipeline" "completed" \
    "input mechanism experiment" >> "${STATUS}"
