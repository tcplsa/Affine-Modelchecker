#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${XOR_CAUSAL_F23_OUT:-${SCRIPT_DIR}/results/xor_causal_phase2_f23_v1}"
PHASE1="${SCRIPT_DIR}/results/xor_causal_phase1_v1"
DESIGN="${OUT}/design"
BINARY="${XOR_CAUSAL_BINARY:-/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker-xor-ablation}"
WORKERS="${XOR_CAUSAL_WORKERS:-80}"
TIMEOUT="${XOR_CAUSAL_TIMEOUT:-120}"
CTG_DEPTH="${XOR_CAUSAL_CTG_DEPTH:-1}"
STATUS="${OUT}/status.tsv"
YEARS=(2015 2017 2019 2020)
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

mkdir -p "${OUT}" "${DESIGN}"
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
status "pipeline" "running" "seeds=1,2,3 timeout=${TIMEOUT} workers=${WORKERS} ctg_depth=${CTG_DEPTH}"

status "setup" "running" "filter phase-1 set and build deterministic allowlists"
python3 "${SCRIPT_DIR}/build_xor_causal_phase2_groups.py" \
    --phase1-design "${PHASE1}/design" \
    --features-pattern "${PHASE1}/design/xor_gate_features_{year}.tsv" \
    --output-dir "${DESIGN}"
for year in "${YEARS[@]}"; do
    python3 "${SCRIPT_DIR}/build_xor_bucket_allowlists.py" \
        --features "${PHASE1}/design/xor_gate_features_${year}.tsv" \
        --output-dir "${OUT}/allowlists/${year}" \
        --manifest "${DESIGN}/xor_buckets_${year}.json" \
        --buckets "${BUCKETS[@]}"
done
status "setup" "completed" "${DESIGN}/selection.json"

for seed in "${SEEDS[@]}"; do
    for year in "${YEARS[@]}"; do
        groups="${DESIGN}/hwmcc${year}_groups_xor_causal_phase2.json"
        output="${OUT}/hwmcc${year}_xor_causal_f23_s${seed}.tsv"
        status "run_${year}_s${seed}" "running" "26 configurations"
        python3 "${SCRIPT_DIR}/collect_xor_causal_phase2.py" \
            --year "${year}" \
            --groups-file "${groups}" \
            --allowlist-dir "${OUT}/allowlists/${year}" \
            --binary "${BINARY}" \
            --output "${output}" \
            --timeout "${TIMEOUT}" \
            --workers "${WORKERS}" \
            --seed "${seed}" \
            --ctg-depth "${CTG_DEPTH}" &
        CHILD_PID="$!"
        wait "${CHILD_PID}"
        CHILD_PID=""
        status "run_${year}_s${seed}" "completed" "${output}"
    done
done

results=("${OUT}"/hwmcc*_xor_causal_f23_s*.tsv)
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
status "pipeline" "completed" "fanout-2/3 conditional causal experiment"

