#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RESULT_DIR=${BVE_ROLE_OBS_RESULT_DIR:-$SCRIPT_DIR/results/bve_role_observables_v1}
BASELINE_DIR=${BVE_ROLE_OBS_BASELINE_DIR:-$SCRIPT_DIR/results/bve_full_campaign_v1}
MANIFEST=${BVE_ROLE_OBS_MANIFEST:-$SCRIPT_DIR/results/full_aig_xag_all_years_v1/manifest.json}
SELECTION=${BVE_ROLE_OBS_SELECTION:-$SCRIPT_DIR/results/bve_hard_specialization_v1/selection.json}
BINARY=${BVE_ROLE_OBS_MC:-/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker-bve-observables-v1}
OUTPUT=${BVE_ROLE_OBS_OUTPUT:-$RESULT_DIR/results.tsv}
WORKERS=${BVE_ROLE_OBS_WORKERS:-15}
TIMEOUT=${BVE_ROLE_OBS_TIMEOUT:-1800}
SEED=${BVE_ROLE_OBS_SEED:-730001}
LOCK_DIR=${OUTPUT}.lock
RUNNER_PID=

mkdir -p "$RESULT_DIR"

cleanup() {
    if [[ -n "${RUNNER_PID:-}" ]] && kill -0 "$RUNNER_PID" 2>/dev/null; then
        kill -TERM -- "-$RUNNER_PID" 2>/dev/null || true
        wait "$RUNNER_PID" 2>/dev/null || true
    fi
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup HUP INT TERM EXIT

[[ -x "$BINARY" ]] || { echo "missing executable: $BINARY" >&2; exit 1; }
mkdir "$LOCK_DIR" 2>/dev/null || {
    echo "experiment already running: $LOCK_DIR" >&2
    exit 1
}

setsid python3 "$SCRIPT_DIR/run_bve_hard_specialization.py" \
    --manifest "$MANIFEST" \
    --baseline-inputs \
        "$BASELINE_DIR/mc_shard_0_of_3.tsv" \
        "$BASELINE_DIR/mc_shard_1_of_3.tsv" \
        "$BASELINE_DIR/mc_shard_2_of_3.tsv" \
    --binary "$BINARY" \
    --output "$OUTPUT" \
    --selection "$SELECTION" \
    --config-set observable \
    --workers "$WORKERS" --timeout "$TIMEOUT" --seed "$SEED" &
RUNNER_PID=$!
wait "$RUNNER_PID"
RUNNER_PID=

python3 "$SCRIPT_DIR/analyze_bve_role_observables.py" \
    --input "$OUTPUT" --output "$RESULT_DIR/report.md"

rmdir "$LOCK_DIR"
trap - HUP INT TERM EXIT
