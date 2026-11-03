#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PHASE2_STATUS="${SCRIPT_DIR}/results/xor_causal_phase2_f23_v1/status.tsv"
SCHEDULER_STATUS="${SCRIPT_DIR}/results/xor_causal_phase3_hard2015_v1/scheduler_status.tsv"
POLL_SECONDS="${XOR_CAUSAL_SCHEDULER_POLL:-30}"

mkdir -p "$(dirname "${SCHEDULER_STATUS}")"
printf 'timestamp\tstatus\tdetail\n' > "${SCHEDULER_STATUS}"
record() {
    printf '%s\t%s\t%s\n' "$(date -Iseconds)" "$1" "$2" >> "${SCHEDULER_STATUS}"
}
record "waiting" "${PHASE2_STATUS}"

while true; do
    state=""
    if [[ -s "${PHASE2_STATUS}" ]]; then
        state="$(awk -F '\t' '$2 == "pipeline" {value=$3} END {print value}' "${PHASE2_STATUS}")"
    fi
    case "${state}" in
        completed)
            record "triggered" "phase2 completed"
            exec "${SCRIPT_DIR}/run_xor_causal_phase3_hard2015.sh"
            ;;
        failed|cancelled)
            record "aborted" "phase2 ${state}"
            exit 1
            ;;
    esac
    sleep "${POLL_SECONDS}"
done

