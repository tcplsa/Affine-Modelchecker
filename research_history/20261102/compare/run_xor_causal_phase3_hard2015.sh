#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${XOR_CAUSAL_HARD_OUT:-${SCRIPT_DIR}/results/xor_causal_phase3_hard2015_v1}"
DESIGN="${OUT}/design"
PRIOR="${SCRIPT_DIR}/results/mechanism_xor_hard2015_validate_v1"
BINARY="${XOR_CAUSAL_BINARY:-/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker-xor-ablation}"
WORKERS="${XOR_CAUSAL_HARD_WORKERS:-80}"
TIMEOUT="${XOR_CAUSAL_HARD_TIMEOUT:-600}"
CTG_DEPTH="${XOR_CAUSAL_CTG_DEPTH:-1}"
STATUS="${OUT}/status.tsv"
SEEDS=(1 2 3)
BUCKETS=(
    f23_next_only f23_shared
    f23_near f23_far
    f23_private_impl f23_reused_impl
    f23_shallow f23_deep
    f23_isolated f23_adjacent
    f23_support_disjoint f23_support_overlap
)
CHILD_PID=""

mkdir -p "${OUT}" "${DESIGN}/candidates" "${DESIGN}/final"
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
status "pipeline" "running" "hard2015 seeds=1,2,3 timeout=${TIMEOUT} workers=${WORKERS}"
status "selection" "running" "balanced AIG/XAG historical directions"
python3 "${SCRIPT_DIR}/build_xor_causal_hard2015_groups.py" \
    --results-pattern "${PRIOR}/hwmcc2015_screen_promote_hardxor_s*.tsv" \
    --structure "${SCRIPT_DIR}/results/xag_struct_2015.tsv" \
    --data-dir "${SCRIPT_DIR}/../hwmcc2015/data" \
    --output-dir "${DESIGN}/candidates" \
    --per-direction 12 \
    --candidate-multiplier 2

mapfile -t models < "${DESIGN}/candidates/hard2015_paths.txt"
python3 "${SCRIPT_DIR}/extract_xor_gate_features.py" "${models[@]}" \
    --output "${DESIGN}/xor_gate_features_2015.tsv" \
    --workers 4
python3 "${SCRIPT_DIR}/build_xor_causal_hard2015_groups.py" \
    --results-pattern "${PRIOR}/hwmcc2015_screen_promote_hardxor_s*.tsv" \
    --structure "${SCRIPT_DIR}/results/xag_struct_2015.tsv" \
    --data-dir "${SCRIPT_DIR}/../hwmcc2015/data" \
    --output-dir "${DESIGN}/final" \
    --per-direction 12 \
    --gate-features "${DESIGN}/xor_gate_features_2015.tsv"
python3 "${SCRIPT_DIR}/build_xor_bucket_allowlists.py" \
    --features "${DESIGN}/xor_gate_features_2015.tsv" \
    --output-dir "${OUT}/allowlists/2015" \
    --manifest "${DESIGN}/xor_buckets_2015.json" \
    --buckets "${BUCKETS[@]}"
status "selection" "completed" "${DESIGN}/final/hwmcc2015_groups_xor_causal_hard.json"

for seed in "${SEEDS[@]}"; do
    output="${OUT}/hwmcc2015_xor_causal_hard_f23_s${seed}.tsv"
    status "run_2015_s${seed}" "running" "24 models x 26 configurations"
    python3 "${SCRIPT_DIR}/collect_xor_causal_phase2.py" \
        --year 2015 \
        --group hard_phase3 \
        --groups-file "${DESIGN}/final/hwmcc2015_groups_xor_causal_hard.json" \
        --allowlist-dir "${OUT}/allowlists/2015" \
        --binary "${BINARY}" \
        --output "${output}" \
        --timeout "${TIMEOUT}" \
        --workers "${WORKERS}" \
        --seed "${seed}" \
        --ctg-depth "${CTG_DEPTH}" &
    CHILD_PID="$!"
    wait "${CHILD_PID}"
    CHILD_PID=""
    status "run_2015_s${seed}" "completed" "${output}"
done

results=("${OUT}"/hwmcc2015_xor_causal_hard_f23_s*.tsv)
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
    --min-gap 2 \
    --buckets "${BUCKETS[@]}"
status "analysis" "completed" "${OUT}/analysis/causal_report.md"
status "pipeline" "completed" "hard-2015 conditional XOR validation"

