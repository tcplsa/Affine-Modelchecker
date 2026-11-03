#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
MANIFEST=${BVE_COVERAGE_MANIFEST:-$SCRIPT_DIR/results/full_aig_xag_all_years_v1/manifest.json}
BASELINE_DIR=${BVE_COVERAGE_BASELINE_DIR:-$SCRIPT_DIR/results/bve_full_campaign_v1}
OUTPUT=${BVE_COVERAGE_OUTPUT:-$SCRIPT_DIR/results/bve_hard_specialization_v1/coverage.tsv}
SELECTION=${BVE_COVERAGE_SELECTION:-$SCRIPT_DIR/results/bve_hard_specialization_v1/selection.json}
BINARY=${BVE_COVERAGE_MC:-/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker}
WORKERS=${BVE_COVERAGE_WORKERS:-10}
TIMEOUT=${BVE_COVERAGE_TIMEOUT:-1800}
SEED=${BVE_COVERAGE_SEED:-730001}
RUNNER_PID=

cleanup() {
    if [[ -n "${RUNNER_PID:-}" ]] && kill -0 "$RUNNER_PID" 2>/dev/null; then
        kill -TERM "$RUNNER_PID" 2>/dev/null || true
        wait "$RUNNER_PID" 2>/dev/null || true
    fi
}
trap cleanup HUP INT TERM EXIT

if [[ ! -x "$BINARY" ]]; then
    echo "missing executable: $BINARY" >&2
    exit 1
fi

python3 "$SCRIPT_DIR/run_bve_hard_specialization.py" \
    --manifest "$MANIFEST" \
    --baseline-inputs \
        "$BASELINE_DIR/mc_shard_0_of_3.tsv" \
        "$BASELINE_DIR/mc_shard_1_of_3.tsv" \
        "$BASELINE_DIR/mc_shard_2_of_3.tsv" \
    --binary "$BINARY" \
    --output "$OUTPUT" \
    --selection "$SELECTION" \
    --config-set coverage \
    --workers "$WORKERS" \
    --timeout "$TIMEOUT" \
    --seed "$SEED" &
RUNNER_PID=$!
wait "$RUNNER_PID"
RUNNER_PID=

python3 "$SCRIPT_DIR/analyze_bve_hard_specialization.py" \
    --baseline-inputs \
        "$BASELINE_DIR/mc_shard_0_of_3.tsv" \
        "$BASELINE_DIR/mc_shard_1_of_3.tsv" \
        "$BASELINE_DIR/mc_shard_2_of_3.tsv" \
    --candidate \
        "$SCRIPT_DIR/results/bve_hard_specialization_v1/role.tsv" \
        "$SCRIPT_DIR/results/bve_hard_specialization_v1/portfolio.tsv" \
        "$OUTPUT" \
    --output "$SCRIPT_DIR/results/bve_hard_specialization_v1/coverage_report.md"

trap - HUP INT TERM EXIT
