#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${AIG_XAG_2024_OUT:-${SCRIPT_DIR}/results/aig_xag_labels_hwmcc2024_v1}"
BINARY="${AIG_XAG_BINARY:-/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker-xor-ablation}"
GROUPS_FILE="${SCRIPT_DIR}/hwmcc2024_groups_mc_60.json"
WORKERS="${AIG_XAG_WORKERS:-80}"
TIMEOUT="${AIG_XAG_TIMEOUT:-300}"
CTG_DEPTH="${AIG_XAG_CTG_DEPTH:-1}"
STATUS="${OUT}/status.tsv"
SEEDS=(1 2 3)
CHILD_PID=""

mkdir -p "${OUT}"
if [[ ! -s "${STATUS}" ]]; then
    printf 'timestamp\tphase\tstatus\tdetail\n' > "${STATUS}"
fi
status() {
    printf '%s\t%s\t%s\t%s\n' "$(date -Iseconds)" "$1" "$2" "$3" >> "${STATUS}"
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
status "pipeline" "running" "HWMCC2024 unique AIG/XAG seeds=1,2,3 timeout=${TIMEOUT} workers=${WORKERS}"
for seed in "${SEEDS[@]}"; do
    output="${OUT}/hwmcc2024_unique_aig_xag_s${seed}.tsv"
    status "run_s${seed}" "running" "319 models x 2 configurations"
    python3 "${SCRIPT_DIR}/collect_aig_xag_labels.py" \
        --year 2024 \
        --group unique \
        --groups-file "${GROUPS_FILE}" \
        --binary "${BINARY}" \
        --output "${output}" \
        --timeout "${TIMEOUT}" \
        --workers "${WORKERS}" \
        --seed "${seed}" \
        --ctg-depth "${CTG_DEPTH}" &
    CHILD_PID="$!"
    wait "${CHILD_PID}"
    CHILD_PID=""
    status "run_s${seed}" "completed" "${output}"
done

results=("${OUT}"/hwmcc2024_unique_aig_xag_s*.tsv)
status "analysis" "running" "timeout_multiplier=1.5 min_gap=2"
python3 "${SCRIPT_DIR}/analyze_aig_xag_labels.py" \
    --results "${results[@]}" \
    --output-dir "${OUT}/analysis" \
    --timeout-multiplier 1.5 \
    --min-gap 2
status "analysis" "completed" "${OUT}/analysis/report.md"
status "pipeline" "completed" "HWMCC2024 direct AIG/XAG labels"
