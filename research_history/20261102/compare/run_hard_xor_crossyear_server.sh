#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${SCRIPT_DIR}/results/mechanism_xor_hard_crossyear_v1"
STATUS="${OUT}/status.tsv"
CORE_BUDGET="${HARD_XOR_CORE_BUDGET:-128}"
TIMEOUT="${HARD_XOR_TIMEOUT:-300}"

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

status "groups" "running" "hard XAG groups"
python3 "${SCRIPT_DIR}/build_hard_xag_groups.py"
status "groups" "completed" "balanced timeout samples"

status "screen" "running" \
    "years=2017,2019,2020 group=timeout_sample_balanced seeds=1..5 timeout=${TIMEOUT}"
python3 "${SCRIPT_DIR}/run_hard_xor_campaign.py" \
    --years 2017 2019 2020 \
    --group timeout_sample_balanced \
    --solver-seeds 1 2 3 4 5 \
    --timeout "${TIMEOUT}" \
    --core-budget "${CORE_BUDGET}" \
    --output-dir "${OUT}"
status "screen" "completed" "${OUT}"

results=("${OUT}"/hwmcc*_hardxor_s*.tsv)
status "analysis" "running" "cross-year hard XOR mechanisms"
python3 "${SCRIPT_DIR}/analyze_mechanism_campaign.py" \
    --results "${results[@]}" \
    --output-dir "${OUT}/analysis" \
    --timeout-multiplier 1.5 \
    --min-gap 1 \
    --min-sample-span 1 \
    --metric wall
status "analysis" "completed" "${OUT}/analysis/report.md"
status "pipeline" "completed" "cross-year hard XOR screen"
