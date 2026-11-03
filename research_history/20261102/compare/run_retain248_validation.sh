#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^(server-a|server-b|all)$ ]]; then
    echo "usage: $0 server-a|server-b|all" >&2
    exit 2
fi

SHARD="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESIGN="${RETAIN248_DESIGN:-${SCRIPT_DIR}/results/retain248_validation_design_v1}"
OUT="${RETAIN248_OUT:-${SCRIPT_DIR}/results/retain248_validation_${SHARD}_v1}"
BINARY="${RETAIN248_BINARY:-/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker-xor-ablation}"
WORKERS="${RETAIN248_WORKERS:-28}"
LANES="${RETAIN248_LANES:-4}"
TIMEOUT="${RETAIN248_TIMEOUT:-600}"
RUNS="${RETAIN248_RUNS:-1,2,3,4}"
CTG_DEPTH="${RETAIN248_CTG_DEPTH:-1}"
CHILD_PID=""

mkdir -p "${OUT}"
STATUS="${OUT}/status.tsv"
if [[ ! -s "${STATUS}" ]]; then
    printf 'timestamp\tstatus\tdetail\n' > "${STATUS}"
fi
status() {
    printf '%s\t%s\t%s\n' "$(date -Iseconds)" "$1" "$2" >> "${STATUS}"
}
cleanup() {
    if [[ -n "${CHILD_PID}" ]] && kill -0 "${CHILD_PID}" 2>/dev/null; then
        kill -TERM "${CHILD_PID}" 2>/dev/null || true
        wait "${CHILD_PID}" 2>/dev/null || true
    fi
}
cancelled() {
    cleanup
    status cancelled "signal received"
    exit 130
}
failed() {
    code="$?"
    cleanup
    status failed "exit=${code} line=${BASH_LINENO[0]}"
    exit "${code}"
}
trap cancelled INT TERM
trap failed ERR

[[ -s "${DESIGN}/manifest.json" ]]
[[ -x "${BINARY}" ]]
status running "shard=${SHARD} runs=${RUNS} workers=${WORKERS} lanes=${LANES} timeout=${TIMEOUT}"
python3 "${SCRIPT_DIR}/run_retain248_validation.py" \
    --manifest "${DESIGN}/manifest.json" \
    --shard "${SHARD}" \
    --binary "${BINARY}" \
    --output "${OUT}/results.tsv" \
    --runs "${RUNS}" \
    --workers "${WORKERS}" \
    --lanes "${LANES}" \
    --timeout "${TIMEOUT}" \
    --ctg-depth "${CTG_DEPTH}" &
CHILD_PID="$!"
wait "${CHILD_PID}"
CHILD_PID=""
status completed "${OUT}/results.tsv"
echo "completed ${SHARD}: ${OUT}/results.tsv"
