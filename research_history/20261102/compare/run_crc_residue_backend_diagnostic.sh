#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
MODEL="$ROOT/test_tools/compare/results/pathb_crc_frame_residue_v1/benchmarks/crc_frame_residue_fcs_topologybalanced_payload_cycles4_polynomial79764919_seed987524_symbol_bits32_width32.aag"
OUT="${CRC_RESIDUE_DIAG_OUT:-$ROOT/test_tools/compare/results/pathb_crc_residue_backend_diag_v1}"
BIN="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker"

mkdir -p "$OUT"
run_case() {
    local name=$1
    shift
    env MC_PDR_STATS=1 MC_PDR_PHASE_STATS=1 MC_PDR_PROGRESS_SECONDS=30 \
        MC_PDR_SEED=984555 MC_PDR_CMSAT_SEED=984555 "$@" \
        timeout --signal=TERM 300 "$BIN" --forward-xag 1 "$MODEL" \
        >"$OUT/${name}.log" 2>&1 || true
}

run_case cadical MC_PDR_SOLVER=cadical &
run_case cmsat_no_gauss_nosimp MC_PDR_SOLVER=cmsat MC_PDR_CMSAT_GAUSS=0 MC_PDR_CMSAT_SIMPLIFY=0 &
run_case cmsat_gauss_nosimp MC_PDR_SOLVER=cmsat MC_PDR_CMSAT_GAUSS=1 MC_PDR_CMSAT_SIMPLIFY=0 &
run_case cmsat_gauss_simplify MC_PDR_SOLVER=cmsat MC_PDR_CMSAT_GAUSS=1 MC_PDR_CMSAT_SIMPLIFY=1 &
wait
