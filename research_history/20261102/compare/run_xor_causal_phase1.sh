#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${XOR_CAUSAL_OUT:-${SCRIPT_DIR}/results/xor_causal_phase1_v1}"
DESIGN="${OUT}/design"
BINARY="${XOR_CAUSAL_BINARY:-/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker-xor-ablation}"
WORKERS="${XOR_CAUSAL_WORKERS:-80}"
TIMEOUT="${XOR_CAUSAL_TIMEOUT:-120}"
SEED="${XOR_CAUSAL_SEED:-1}"
CTG_DEPTH="${XOR_CAUSAL_CTG_DEPTH:-1}"
STATUS="${OUT}/status.tsv"
YEARS=(2015 2017 2019 2020)
CHILD_PID=""

mkdir -p "${OUT}"
if [[ ! -s "${STATUS}" ]]; then
    printf 'timestamp\tphase\tstatus\tdetail\n' > "${STATUS}"
fi
status() {
    printf '%s\t%s\t%s\t%s\n' \
        "$(date -Iseconds)" "$1" "$2" "$3" >> "${STATUS}"
}
stop_child() {
    if [[ -n "${CHILD_PID}" ]] && kill -0 "${CHILD_PID}" 2>/dev/null; then
        kill -TERM "${CHILD_PID}" 2>/dev/null || true
        wait "${CHILD_PID}" 2>/dev/null || true
    fi
}
cancelled() {
    stop_child
    status "pipeline" "cancelled" "signal received"
    exit 130
}
failed() {
    local code="$?"
    stop_child
    status "pipeline" "failed" "line=${BASH_LINENO[0]} exit=${code}"
    exit "${code}"
}
trap cancelled INT TERM
trap failed ERR

[[ -x "${BINARY}" ]]
status "pipeline" "running" "seed=${SEED} timeout=${TIMEOUT} workers=${WORKERS} ctg_depth=${CTG_DEPTH}"

for year in "${YEARS[@]}"; do
    groups="${DESIGN}/hwmcc${year}_groups_xor_causal.json"
    allowlists="${OUT}/allowlists/${year}"
    [[ -s "${groups}" ]]
    [[ -d "${allowlists}" ]]
    status "run_${year}" "running" "10 models x 10 configurations"
    python3 "${SCRIPT_DIR}/collect_xor_causal_phase1.py" \
        --year "${year}" \
        --groups-file "${groups}" \
        --allowlist-dir "${allowlists}" \
        --binary "${BINARY}" \
        --output "${OUT}/hwmcc${year}_xor_causal_s${SEED}.tsv" \
        --timeout "${TIMEOUT}" \
        --workers "${WORKERS}" \
        --seed "${SEED}" \
        --ctg-depth "${CTG_DEPTH}" &
    CHILD_PID="$!"
    wait "${CHILD_PID}"
    CHILD_PID=""
    status "run_${year}" "completed" "${OUT}/hwmcc${year}_xor_causal_s${SEED}.tsv"
done

results=("${OUT}"/hwmcc*_xor_causal_s"${SEED}".tsv)
status "analysis" "running" "metric=wall min_gap=2 timeout_multiplier=1.5"
python3 "${SCRIPT_DIR}/analyze_mechanism_campaign.py" \
    --results "${results[@]}" \
    --output-dir "${OUT}/analysis" \
    --timeout-multiplier 1.5 \
    --min-gap 2 \
    --min-sample-span 2 \
    --metric wall
python3 "${SCRIPT_DIR}/analyze_xor_causal_phase1.py" \
    --results "${results[@]}" \
    --output-dir "${OUT}/analysis" \
    --timeout-multiplier 1.5 \
    --min-gap 2
status "analysis" "completed" "${OUT}/analysis/report.md"
status "pipeline" "completed" "XOR causal phase 1"
