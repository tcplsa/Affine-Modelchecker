#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${SCRIPT_DIR}/results/mechanism_xor_v1"
STATUS="${OUT}/status.tsv"
CORE_BUDGET="${MECH_CORE_BUDGET:-128}"
TRANSFORM_SEEDS="${MECH_TRANSFORM_SEEDS:-1,2,3,4,5,6,7,8}"

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

status "xor_campaign" "running" \
    "solver_seeds=1..5 transform_seeds=${TRANSFORM_SEEDS}"
python3 "${SCRIPT_DIR}/run_mechanism_campaign.py" \
    --axis xor \
    --years 2015 2017 2019 2020 \
    --tiers fast_unique medium_unique slow_unique \
    --solver-seeds 1 2 3 4 5 \
    --transform-seeds "${TRANSFORM_SEEDS}" \
    --core-budget "${CORE_BUDGET}" \
    --output-dir "${OUT}"
status "xor_campaign" "completed" "${OUT}"

results=("${OUT}"/hwmcc*_xor_s*.tsv)
status "analysis" "running" "controlled XOR mechanisms"
python3 "${SCRIPT_DIR}/analyze_mechanism_campaign.py" \
    --results "${results[@]}" \
    --output-dir "${OUT}/analysis" \
    --timeout-multiplier 1.5 \
    --min-gap 1 \
    --min-sample-span 1 \
    --metric algorithm
status "analysis" "completed" "${OUT}/analysis/report.md"
status "pipeline" "completed" "xor mechanism experiment"
