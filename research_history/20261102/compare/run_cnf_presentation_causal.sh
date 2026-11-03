#!/usr/bin/env bash
set -euo pipefail

ROLE=${1:-}
ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
MC="$ROOT/Modelchecker-bidirectional/modelchecker"
BINARY="$MC/modelchecker-cnf-presentation-v1"
REPLAY="$TOOLS/sat_query_replay"
HOLDOUT="$TOOLS/results/initial_cnf_final_holdout_design_v1/manifest.json"
CAUSAL_DESIGN="$TOOLS/results/cnf_presentation_causal_design_v1"
RESULTS="$TOOLS/results/cnf_presentation_phase_v1"
PHASE_WORKERS=${CNF_PHASE_WORKERS:-30}
TRACE_WORKERS=${CNF_TRACE_WORKERS:-8}
REPLAY_WORKERS=${CNF_REPLAY_WORKERS:-20}
LANES=${CNF_PRESENTATION_LANES:-4}
TRACE_LANES=${CNF_TRACE_LANES:-1}
PHASE_TIMEOUT=${CNF_PHASE_TIMEOUT:-300}
TRACE_TIMEOUT=${CNF_TRACE_TIMEOUT:-60}
TRACE_MAX_MB=${CNF_TRACE_MAX_MB:-128}

cleanup() {
    pkill -TERM -P $$ 2>/dev/null || true
    wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

case "$ROLE" in
server-a)
    CONFIGS=xag_canonical-cnf
    TRACE_CONFIGS=xag_canonical-cnf
    RUNS=1,2,3
    SEED_BASE=110000
    ;;
server-b)
    CONFIGS=xag_canonical-cnf
    TRACE_CONFIGS=xag_canonical-cnf
    RUNS=4,5,6
    SEED_BASE=310000
    ;;
server-c)
    CONFIGS=aig_canonical-cnf
    TRACE_CONFIGS=aig_canonical-cnf
    RUNS=4,5,6
    SEED_BASE=310000
    ;;
*)
    echo "usage: $0 server-a|server-b|server-c" >&2
    exit 2
    ;;
esac

for required in "$BINARY" "$REPLAY" "$HOLDOUT" "$CAUSAL_DESIGN/manifest_$ROLE.json"; do
    if [[ ! -e "$required" ]]; then
        echo "missing required experiment artifact: $required" >&2
        exit 2
    fi
done

mkdir -p "$RESULTS/$ROLE"

python3 "$TOOLS/run_phase_order_campaign.py" \
    --manifest "$HOLDOUT" --binary "$BINARY" \
    --output "$RESULTS/$ROLE/phase_results.tsv" \
    --configs "$CONFIGS" --runs "$RUNS" \
    --treatments first:first,numeric:first,first:numeric,numeric:numeric \
    --workers "$PHASE_WORKERS" --lanes "$LANES" --timeout "$PHASE_TIMEOUT" \
    --seed-base "$SEED_BASE"

python3 "$TOOLS/run_cnf_query_trace.py" \
    --manifest "$CAUSAL_DESIGN/manifest_$ROLE.json" --binary "$BINARY" \
    --output "$RESULTS/$ROLE/trace_summary.tsv" \
    --trace-root "$RESULTS/$ROLE/traces" \
    --configs "$TRACE_CONFIGS" \
    --origins first:first,numeric:numeric \
    --workers "$TRACE_WORKERS" --lanes "$TRACE_LANES" --timeout "$TRACE_TIMEOUT" \
    --max-trace-mb "$TRACE_MAX_MB"

python3 "$TOOLS/run_cnf_query_replay.py" \
    --trace-summary "$RESULTS/$ROLE/trace_summary.tsv" \
    --trace-root "$RESULTS/$ROLE/traces" --replay-binary "$REPLAY" \
    --output "$RESULTS/$ROLE/replay_results.tsv" \
    --workers "$REPLAY_WORKERS" --timeout "$TRACE_TIMEOUT"

trap - INT TERM EXIT
