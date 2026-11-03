#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
    echo "usage: $0 <full.aig> <slice.aag> <output-dir> <seconds>" >&2
    exit 2
fi

full_model=$1
slice_model=$2
output_dir=$3
seconds=$4
root=/home/wudl
mc="$root/Modelchecker-bidirectional/modelchecker/modelchecker"

mkdir -p "$output_dir/full-trace" "$output_dir/slice-trace"

env MC_PDR_SEED=760001 MC_PDR_STATS=1 MC_PDR_PROGRESS_SECONDS=30 \
    MC_PDR_SEMANTIC_TRACE_DIR="$output_dir/full-trace" \
    MC_PDR_SEMANTIC_TRACE_MAX_EVENTS=30000 \
    timeout --signal=TERM "$seconds" "$mc" --forward-aig 1 "$full_model" \
    >"$output_dir/full.log" 2>&1 &
full_pid=$!

env MC_PDR_SEED=760001 MC_PDR_STATS=1 MC_PDR_PROGRESS_SECONDS=30 \
    MC_PDR_SEMANTIC_TRACE_DIR="$output_dir/slice-trace" \
    MC_PDR_SEMANTIC_TRACE_MAX_EVENTS=30000 \
    timeout --signal=TERM "$seconds" "$mc" --forward-aig 1 "$slice_model" \
    >"$output_dir/slice.log" 2>&1 &
slice_pid=$!

wait "$full_pid" || true
wait "$slice_pid" || true

python3 "$root/test_tools/compare/analyze_pdr_semantic_trace.py" \
    "$output_dir/full-trace" "$output_dir/slice-trace" \
    >"$output_dir/semantic_summary.tsv"
