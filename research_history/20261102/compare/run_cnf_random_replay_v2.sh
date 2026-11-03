#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
DESIGN="$TOOLS/results/cnf_presentation_causal_design_v1"
RESULTS="$TOOLS/results/cnf_presentation_random_replay_v2"
BINARY="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker-cnf-presentation-v2"
REPLAY="$TOOLS/sat_query_replay-v2"

ROLE=${CNF_V2_ROLE:-all}
TRACE_WORKERS=${CNF_V2_TRACE_WORKERS:-12}
REPLAY_WORKERS=${CNF_V2_REPLAY_WORKERS:-60}
TRACE_TIMEOUT=${CNF_V2_TRACE_TIMEOUT:-60}
TRACE_MAX_MB=${CNF_V2_TRACE_MAX_MB:-128}
MODES=recorded,first,numeric,random-1,random-2,random-3,random-4,random-5,random-6,random-7,random-8

case "$ROLE" in
    all) ROLES=(server-a server-b server-c) ;;
    server-a|server-b|server-c) ROLES=("$ROLE") ;;
    *) echo "CNF_V2_ROLE must be all, server-a, server-b, or server-c" >&2; exit 2 ;;
esac

mkdir -p "$RESULTS"
for shard in "${ROLES[@]}"; do
    if [[ "$shard" == server-c ]]; then
        config=aig_canonical-cnf
    else
        config=xag_canonical-cnf
    fi
    out="$RESULTS/$shard"
    mkdir -p "$out"
    python3 "$TOOLS/run_cnf_query_trace.py" \
        --manifest "$DESIGN/manifest_$shard.json" --binary "$BINARY" \
        --output "$out/trace_summary.tsv" --trace-root "$out/traces" \
        --configs "$config" --origins first:first,numeric:numeric \
        --workers "$TRACE_WORKERS" --lanes 1 --timeout "$TRACE_TIMEOUT" \
        --max-trace-mb "$TRACE_MAX_MB"
    python3 "$TOOLS/run_cnf_query_replay.py" \
        --trace-summary "$out/trace_summary.tsv" --trace-root "$out/traces" \
        --replay-binary "$REPLAY" --output "$out/replay_results.tsv" \
        --modes "$MODES" --roles frame,lift \
        --workers "$REPLAY_WORKERS" --timeout 180
done

replays=()
for shard in server-a server-b server-c; do
    if [[ -s "$RESULTS/$shard/replay_results.tsv" ]]; then
        replays+=("$RESULTS/$shard/replay_results.tsv")
    fi
done
python3 "$TOOLS/analyze_cnf_random_replay.py" "${replays[@]}" \
    --output "$RESULTS/random_replay_report.md"
