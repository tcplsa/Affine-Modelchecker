#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ( "$1" != "benefit" && "$1" != "harm" ) ]]; then
    echo "usage: $0 benefit|harm" >&2
    exit 2
fi

ARM="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESIGN="${XOR_SHAPLEY_DESIGN_OUT:-${SCRIPT_DIR}/results/xor_shapley_phase4_design_v1}"
MANIFEST="${DESIGN}/manifest.json"
OUT="${XOR_SHAPLEY_OUT:-${SCRIPT_DIR}/results/xor_shapley_phase4_${ARM}_v1}"
BINARY="${XOR_SHAPLEY_BINARY:-/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker-xor-ablation}"
WORKERS="${XOR_SHAPLEY_WORKERS:-80}"
TIMEOUT="${XOR_SHAPLEY_TIMEOUT:-300}"
CTG_DEPTH="${XOR_SHAPLEY_CTG_DEPTH:-1}"
read -r -a SEEDS <<< "${XOR_SHAPLEY_SEEDS:-1 2 3}"
STATUS="${OUT}/status.tsv"
CHILD_PID=""

[[ -s "${MANIFEST}" ]]
[[ -x "${BINARY}" ]]
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

status "pipeline" "running" "arm=${ARM} seeds=${SEEDS[*]} timeout=${TIMEOUT} workers=${WORKERS}"
for seed in "${SEEDS[@]}"; do
    output="${OUT}/${ARM}_seed${seed}.tsv"
    status "seed_${seed}" "running" "${output}"
    python3 "${SCRIPT_DIR}/run_xor_shapley_tasks.py" \
        --manifest "${MANIFEST}" \
        --arm "${ARM}" \
        --binary "${BINARY}" \
        --output "${output}" \
        --seed "${seed}" \
        --timeout "${TIMEOUT}" \
        --workers "${WORKERS}" \
        --ctg-depth "${CTG_DEPTH}" &
    CHILD_PID="$!"
    wait "${CHILD_PID}"
    CHILD_PID=""
    status "seed_${seed}" "completed" "${output}"
done
status "pipeline" "completed" "arm=${ARM}"
echo "completed ${ARM}: ${OUT}"
