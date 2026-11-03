#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RESULT_DIR=${BVE_PROBE_DIR:-$SCRIPT_DIR/results/bve_preprocess_probe_v1}
MANIFEST=${BVE_PROBE_MANIFEST:-$SCRIPT_DIR/results/full_aig_xag_all_years_v1/manifest.json}
BINARY=${BVE_PROBE_BINARY:-/home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker-bve-probe-v1}
OUTPUT=${BVE_PROBE_OUTPUT:-$RESULT_DIR/results.tsv}
WORKERS=${BVE_PROBE_WORKERS:-16}
TIMEOUT=${BVE_PROBE_TIMEOUT:-300}
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
    echo "probe already running: $LOCK_DIR" >&2
    exit 1
}

setsid python3 "$SCRIPT_DIR/run_bve_preprocess_probe.py" \
    --manifest "$MANIFEST" --binary "$BINARY" --output "$OUTPUT" \
    --workers "$WORKERS" --timeout "$TIMEOUT" &
RUNNER_PID=$!
wait "$RUNNER_PID"
RUNNER_PID=

rmdir "$LOCK_DIR"
trap - HUP INT TERM EXIT
