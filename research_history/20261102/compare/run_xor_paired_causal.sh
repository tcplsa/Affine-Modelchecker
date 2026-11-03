#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 || ! "$1" =~ ^(server-a|server-b|all)$ ]]; then
    echo "usage: $0 server-a|server-b|all" >&2
    exit 2
fi
SHARD="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESIGN="${XOR_PAIRED_DESIGN:-${SCRIPT_DIR}/results/xor_paired_causal_design_v1}"
OUT="${XOR_PAIRED_OUT:-${SCRIPT_DIR}/results/xor_paired_causal_${SHARD}_v1}"
BINARY="${XOR_PAIRED_BINARY:-/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker-xor-causal}"
CHILD_PID=""
mkdir -p "${OUT}"
STATUS="${OUT}/status.tsv"
[[ -s "${STATUS}" ]] || printf 'timestamp\tstatus\tdetail\n' > "${STATUS}"
status(){ printf '%s\t%s\t%s\n' "$(date -Iseconds)" "$1" "$2" >> "${STATUS}"; }
cleanup(){
    if [[ -n "${CHILD_PID}" ]] && kill -0 "${CHILD_PID}" 2>/dev/null; then
        kill -TERM "${CHILD_PID}" 2>/dev/null || true
        wait "${CHILD_PID}" 2>/dev/null || true
    fi
}
trap 'cleanup; status cancelled signal; exit 130' INT TERM
trap 'code=$?; cleanup; status failed "exit=${code}"; exit ${code}' ERR
status running "shard=${SHARD} workers=${XOR_PAIRED_WORKERS:-12} lanes=${XOR_PAIRED_LANES:-4}"
python3 "${SCRIPT_DIR}/run_xor_paired_causal.py" \
    --manifest "${DESIGN}/manifest.json" --shard "${SHARD}" --binary "${BINARY}" \
    --output "${OUT}/results.tsv" --runs "${XOR_PAIRED_RUNS:-1,2,3,4}" \
    --workers "${XOR_PAIRED_WORKERS:-12}" --lanes "${XOR_PAIRED_LANES:-4}" \
    --timeout "${XOR_PAIRED_TIMEOUT:-600}" --ctg-depth "${XOR_PAIRED_CTG_DEPTH:-1}" &
CHILD_PID="$!"
wait "${CHILD_PID}"
CHILD_PID=""
status completed "${OUT}/results.tsv"
