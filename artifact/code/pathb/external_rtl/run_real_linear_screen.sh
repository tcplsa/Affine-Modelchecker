#!/usr/bin/env bash
set -euo pipefail

# Pure-solver screen for fixed-parameter, application-style linear datapaths.
# Each model retains a sequential serial-reference wrapper.  This is intentionally
# not a mixed portfolio: every row isolates one SAT backend/mode.

ROOT=/home/wudl
BIN="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker"
MODEL_DIR="$ROOT/test_tools/compare/results/pathb_real_linear_rtl_v1"
OUT="${1:-$MODEL_DIR/screen_120s}"
LIMIT="${2:-120}"
SEED="${3:-991001}"

mkdir -p "$OUT"

models=(
    crc32_parallel_serial_refinement_w32
    crc32_parallel_serial_refinement_w64
    crc32_parallel_serial_refinement_w128
    scrambler_64b66b_parallel_serial_refinement_w64
    scrambler_pcie_gen3_parallel_serial_refinement_w32
)

# A follow-up may isolate a predeclared subset without changing backend modes.
# Example: MODELS='crc32_parallel_serial_refinement_w32 crc32_parallel_serial_refinement_w64'.
if [[ -n "${MODELS:-}" ]]; then
    read -r -a models <<<"$MODELS"
fi

run_case() {
    local model=$1
    local solver=$2
    local gauss=$3
    local log="$OUT/${model}__${solver}${gauss}.log"

    set +e
    env MC_PDR_STATS=1 MC_PDR_PHASE_STATS=1 MC_PDR_PROGRESS_SECONDS=15 \
        MC_PDR_SEED="$SEED" MC_PDR_CMSAT_SEED="$SEED" \
        MC_PDR_SOLVER="$solver" MC_PDR_CMSAT_GAUSS="$gauss" \
        MC_PDR_CMSAT_SIMPLIFY=0 \
        timeout --kill-after=10s --signal=TERM "$LIMIT" \
        "$BIN" --forward-xag 1 "$MODEL_DIR/${model}.aag" >"$log" 2>&1
    local status=$?
    set -e
    if [[ $status -eq 124 || $status -eq 137 ]]; then
        printf 'c SCREEN_STATUS timeout\n' >>"$log"
    elif [[ $status -ne 0 ]]; then
        printf 'c SCREEN_STATUS error exit=%s\n' "$status" >>"$log"
    else
        printf 'c SCREEN_STATUS complete\n' >>"$log"
    fi
}

for model in "${models[@]}"; do
    run_case "$model" cadical 0 &
    run_case "$model" cmsat 0 &
    run_case "$model" cmsat 1 &
    wait
done

python3 "$ROOT/test_tools/compare/pathb/external_rtl/summarize_real_linear_screen.py" \
    "$OUT" >"$OUT/report.md"
