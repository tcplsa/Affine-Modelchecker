#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
OLD_DIR="${RESULTS_DIR}/initial_state_large"
SEED_DIR="${RESULTS_DIR}/initial_state_seed345"
VALID_DIR="${RESULTS_DIR}/initial_state_portfolio4_2024"
MODEL="${SEED_DIR}/selector_seed1_5.json"
STATUS="${RESULTS_DIR}/initial_state_overnight_status.tsv"

mkdir -p "${SEED_DIR}" "${VALID_DIR}"

write_status() {
    local phase="$1"
    local state="$2"
    local detail="$3"
    printf '%s\t%s\t%s\t%s\n' \
        "$(date -Iseconds)" "${phase}" "${state}" "${detail}" >> "${STATUS}"
}

on_error() {
    local line="$1"
    local code="$2"
    write_status "pipeline" "failed" "line=${line} exit=${code}"
    exit "${code}"
}
trap 'on_error "${LINENO}" "$?"' ERR

printf 'timestamp\tphase\tstatus\tdetail\n' > "${STATUS}"
write_status "pipeline" "started" "seed345 then portfolio4_2024"

echo "[phase 1/4] collect unseen solver seeds 3, 4, 5"
write_status "seed345" "running" "190 states, one lane, <=128 processes"
python3 "${SCRIPT_DIR}/run_large_initial_state_campaign.py" \
    --years 2015 2017 2019 2020 \
    --tiers fast_unique medium_unique slow_unique \
    --design-seeds 1 2 3 \
    --solver-seeds 3 4 5 \
    --candidates 64 \
    --lanes-per-state 1 \
    --core-budget 128 \
    --output-dir "${SEED_DIR}"
write_status "seed345" "completed" "${SEED_DIR}"

old_results=("${OLD_DIR}"/hwmcc*_unique_broad64_d*_s*.tsv)
new_results=("${SEED_DIR}"/hwmcc*_unique_broad64_d*_s*.tsv)
train_features=(
    "${RESULTS_DIR}/xag_struct_2015.tsv"
    "${RESULTS_DIR}/xag_struct_2017.tsv"
    "${RESULTS_DIR}/xag_struct_2019.tsv"
    "${RESULTS_DIR}/xag_struct_2020.tsv"
)

echo "[phase 2/4] analyze and fit solver seeds 1 through 5"
write_status "fit_seed1_5" "running" "span>1s, worst-seed aggregation"
python3 "${SCRIPT_DIR}/analyze_large_initial_state_campaign.py" \
    --results "${old_results[@]}" "${new_results[@]}" \
    --output-dir "${SEED_DIR}/analysis_seed1_5" \
    --baseline state_000 \
    --timeout-multiplier 1.5 \
    --min-gap 1 \
    --metric algorithm

python3 "${SCRIPT_DIR}/fit_large_initial_state_selector.py" \
    --results "${old_results[@]}" "${new_results[@]}" \
    --features "${train_features[@]}" \
    --baseline state_000 \
    --top-states 16 \
    --max-per-family 4 \
    --max-depth 5 \
    --min-leaf 8 \
    --cv-folds 5 \
    --timeout-multiplier 1.5 \
    --switch-penalty-percent 1 \
    --minimum-cv-gain-percent 1 \
    --min-action-span 1 \
    --minimum-year-gain-percent 0 \
    --minimum-seed-transfer-gain-percent 0 \
    --seed-aggregation max \
    --metric algorithm \
    --model-output "${MODEL}" \
    --report-output "${SEED_DIR}/selector_seed1_5.md"
write_status "fit_seed1_5" "completed" "${MODEL}"

candidate_ids="$(
    python3 - "${MODEL}" <<'PY'
import json
import sys

model = json.load(open(sys.argv[1], encoding="utf-8"))
configs = model["action_configs"]
ids = {"state_000"}
for action in model["actions"]:
    config = configs[action]
    ids.add(config.get("source_id", "state_000"))
print(",".join(sorted(ids)))
PY
)"
candidate_count="$(
    python3 - "${candidate_ids}" <<'PY'
import sys
print(len([item for item in sys.argv[1].split(",") if item]))
PY
)"
write_status "portfolio4_2024" "selected" \
    "states=${candidate_count} ids=${candidate_ids}"

echo "[phase 3/4] validate frozen candidates on HWMCC 2024 with four lanes"
write_status "portfolio4_2024" "running" \
    "${candidate_count} states x 4 lanes, root seeds 101/211/307"
python3 "${SCRIPT_DIR}/run_large_initial_state_campaign.py" \
    --years 2024 \
    --tiers fast_unique medium_unique slow_unique \
    --design-seeds 1 2 3 \
    --solver-seeds 101 211 307 \
    --candidates 64 \
    --candidate-ids "${candidate_ids}" \
    --lanes-per-state 4 \
    --core-budget 128 \
    --output-dir "${VALID_DIR}"
write_status "portfolio4_2024" "completed" "${VALID_DIR}"

validation_results=("${VALID_DIR}"/hwmcc*_unique_broad64_d*_s*.tsv)

echo "[phase 4/4] analyze held-out year and evaluate frozen decision tree"
write_status "evaluate_2024" "running" "candidate tree, span>1s"
python3 "${SCRIPT_DIR}/analyze_large_initial_state_campaign.py" \
    --results "${validation_results[@]}" \
    --output-dir "${VALID_DIR}/analysis" \
    --baseline state_000 \
    --timeout-multiplier 1.5 \
    --min-gap 1 \
    --metric algorithm

python3 "${SCRIPT_DIR}/evaluate_large_initial_state_selector.py" \
    --model "${MODEL}" \
    --features "${RESULTS_DIR}/xag_struct_2024.tsv" \
    --results "${validation_results[@]}" \
    --tree candidate \
    --timeout-multiplier 1.5 \
    --min-action-span 1 \
    --metric algorithm \
    --output "${VALID_DIR}/candidate_selector_eval.tsv" \
    --report-output "${VALID_DIR}/candidate_selector_eval.md"
write_status "evaluate_2024" "completed" \
    "${VALID_DIR}/candidate_selector_eval.md"
write_status "pipeline" "completed" "HWMCC 2025 remains blind"

echo "overnight pipeline completed"
echo "report: ${VALID_DIR}/candidate_selector_eval.md"
