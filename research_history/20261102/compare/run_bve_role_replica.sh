#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RESULT_DIR=${BVE_ROLE_REPLICA_RESULT_DIR:-$SCRIPT_DIR/results/bve_hard_specialization_v1}
BASELINE_DIR=${BVE_ROLE_REPLICA_BASELINE_DIR:-$SCRIPT_DIR/results/bve_full_campaign_v1}
MANIFEST=${BVE_ROLE_REPLICA_MANIFEST:-$SCRIPT_DIR/results/full_aig_xag_all_years_v1/manifest.json}
SELECTION=${BVE_ROLE_REPLICA_SELECTION:-$RESULT_DIR/selection.json}
OUTPUT=${BVE_ROLE_REPLICA_OUTPUT:-$RESULT_DIR/role_replica.tsv}
BINARY=${BVE_ROLE_REPLICA_MC:-/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker}
WORKERS=${BVE_ROLE_REPLICA_WORKERS:-30}
TIMEOUT=${BVE_ROLE_REPLICA_TIMEOUT:-1800}
SEED=${BVE_ROLE_REPLICA_SEED:-830001}
LOCK_DIR=${OUTPUT}.lock
RUNNER_PID=

cleanup() {
    if [[ -n "${RUNNER_PID:-}" ]] && kill -0 "$RUNNER_PID" 2>/dev/null; then
        kill -TERM "$RUNNER_PID" 2>/dev/null || true
        wait "$RUNNER_PID" 2>/dev/null || true
    fi
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup HUP INT TERM EXIT

if [[ ! -x "$BINARY" ]]; then
    echo "missing executable: $BINARY" >&2
    exit 1
fi
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "role replica is already running (lock exists): $LOCK_DIR" >&2
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
    --config-set role-replica \
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
        "$RESULT_DIR/role.tsv" \
        "$RESULT_DIR/portfolio.tsv" \
        "$RESULT_DIR/coverage.tsv" \
        "$OUTPUT" \
    --output "$RESULT_DIR/role_replica_report.md"

rmdir "$LOCK_DIR"
trap - HUP INT TERM EXIT
