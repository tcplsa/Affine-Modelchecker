#!/usr/bin/env bash
set -euo pipefail

# Small, deterministic checks for the affine-invariant front end:
#   1) a conditioned invariant closes a phase-gated property at startup;
#   2) the same rows can be replayed into PDR when direct completion is off;
#   3) a partial affine cone in CRC RTL remains a sound ordinary-PDR fallback.
ROOT=/home/wudl
MC="${AFFINE_FRONTEND_MC:-$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker}"
LIMIT="${AFFINE_FRONTEND_LIMIT:-60}"
PHASE="$ROOT/test_tools/compare/results/pathb_affine_phase_sync_v1/benchmarks/affine_phase_sync_delay2_inputs4_rounds2_seed840001_topologybalanced_weight19_width24.aag"
CRC="$ROOT/test_tools/compare/results/pathb_crc_frame_residue_v1/benchmarks/crc_frame_residue_fcs_topologybalanced_payload_cycles2_polynomial4129_seed985922_symbol_bits32_width16.aag"

# Keep the common solver setup explicit: this is the supported native-XOR lane.
COMMON=(MC_PDR_SOLVER=cmsat MC_PDR_CMSAT_GAUSS=1
    MC_PDR_GUARDED_AFFINE=1 MC_PDR_GUARDED_AFFINE_MAX_CONTROLS=2
    MC_PDR_GUARDED_AFFINE_VALIDATE=1 MC_PDR_AFFINE_INVARIANTS=1
    MC_PDR_STATS=1)

direct_log=$(mktemp "${TMPDIR:-/tmp}/affine-front-end.direct.XXXXXX.log")
timeout "$LIMIT" env "${COMMON[@]}" MC_PDR_AFFINE_INVARIANT_DIRECT_CHECK=1 \
    "$MC" -xag "$PHASE" > "$direct_log" 2>&1
rg -q 'c PDR_AFFINE_INVARIANT status=proved' "$direct_log"
rg -q 'result: safe' "$direct_log"
rm -f "$direct_log"

feedback_log=$(mktemp "${TMPDIR:-/tmp}/affine-front-end.feedback.XXXXXX.log")
timeout "$LIMIT" env "${COMMON[@]}" MC_PDR_AFFINE_INVARIANT_DIRECT_CHECK=0 \
    MC_PDR_AFFINE_INVARIANT_CONDITIONED_FEEDBACK=1 \
    "$MC" -xag "$PHASE" > "$feedback_log" 2>&1
rg --quiet -e 'invariant_conditioned_encoded=[1-9][0-9]*' "$feedback_log"
rg -q 'result: safe' "$feedback_log"
rm -f "$feedback_log"

fallback_log=$(mktemp "${TMPDIR:-/tmp}/affine-front-end.fallback.XXXXXX.log")
timeout "$LIMIT" env "${COMMON[@]}" MC_PDR_AFFINE_INVARIANT_DIRECT_CHECK=1 \
    "$MC" -xag "$CRC" > "$fallback_log" 2>&1
rg -q 'invariant_partial=1' "$fallback_log"
if rg -q 'c PDR_AFFINE_INVARIANT status=proved' "$fallback_log"; then
    echo 'FAIL: partial CRC cone unexpectedly used the startup proof path' >&2
    exit 1
fi
rg -q 'result: safe' "$fallback_log"
rm -f "$fallback_log"

echo 'PASS: affine front end direct proof, conditioned feedback, and partial fallback'
