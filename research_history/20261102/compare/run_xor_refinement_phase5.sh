#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^(server-a|server-b|benefit|harm)$ ]]; then
    echo "usage: $0 server-a|server-b|benefit|harm" >&2
    exit 2
fi

TARGET="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESIGN="${XOR_REFINEMENT_DESIGN_OUT:-${SCRIPT_DIR}/results/xor_refinement_phase5_design_v1}"
OUT="${XOR_REFINEMENT_OUT:-${SCRIPT_DIR}/results/xor_refinement_phase5_${TARGET}_train_v1}"
BINARY="${XOR_REFINEMENT_BINARY:-/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker-xor-ablation}"
WORKERS="${XOR_REFINEMENT_WORKERS:-28}"
TIMEOUT="${XOR_REFINEMENT_TIMEOUT:-300}"
CTG_DEPTH="${XOR_REFINEMENT_CTG_DEPTH:-1}"
LANES="${XOR_REFINEMENT_LANES:-4}"
read -r -a RUNS <<< "${XOR_REFINEMENT_RUNS:-1 2 3 4}"
STATUS="${OUT}/status.tsv"
CHILD_PID=""

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

case "${TARGET}" in
    server-a)
        ARM_SPECS=(
            "benefit:"
            "harm:yosyshq_appnote_123_veer_axi-p31"
        )
        ;;
    server-b)
        ARM_SPECS=(
            "harm:6s344rb150,6s385rb444,mentorbm1and,a16-p139,zonotope_2"
        )
        ;;
    benefit|harm)
        ARM_SPECS=("${TARGET}:")
        ;;
esac

status "pipeline" "running" "target=${TARGET} runs=${RUNS[*]} lanes=${LANES} timeout=${TIMEOUT} workers=${WORKERS}"
for context in add retain; do
    manifest="${DESIGN}/manifest_${context}.json"
    [[ -s "${manifest}" ]]
    for spec in "${ARM_SPECS[@]}"; do
        arm="${spec%%:*}"
        model_filter="${spec#*:}"
        for run in "${RUNS[@]}"; do
            suffix="${arm}"
            if [[ -n "${model_filter}" ]]; then
                suffix="${arm}_subset"
            fi
            output="${OUT}/${context}_${suffix}_run${run}.tsv"
            status "${context}_${arm}_run_${run}" "running" "${output}"
            model_args=()
            if [[ -n "${model_filter}" ]]; then
                model_args=(--models "${model_filter}")
            fi
            python3 "${SCRIPT_DIR}/run_xor_shapley_tasks.py" \
                --manifest "${manifest}" \
                --arm "${arm}" \
                --binary "${BINARY}" \
                --output "${output}" \
                --seed "${run}" \
                --timeout "${TIMEOUT}" \
                --workers "${WORKERS}" \
                --ctg-depth "${CTG_DEPTH}" \
                --lanes "${LANES}" \
                "${model_args[@]}" &
            CHILD_PID="$!"
            wait "${CHILD_PID}"
            CHILD_PID=""
            status "${context}_${arm}_run_${run}" "completed" "${output}"
        done
    done
done
status "pipeline" "completed" "target=${TARGET}"
echo "completed ${TARGET}: ${OUT}"
