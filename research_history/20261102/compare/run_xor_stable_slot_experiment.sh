#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
DESIGN="$TOOLS/results/xor_stable_slot_design_v1"
RESULTS="$TOOLS/results/xor_stable_slot_local_v2"
MANIFEST="$DESIGN/manifest.json"
RUNNER="$TOOLS/run_xor_paired_causal.py"
BINARY="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker-xor-stable-causal"
STABLE_WRAPPER="$TOOLS/modelchecker_xor_stable_slots.sh"

mkdir -p "$RESULTS"
python3 "$TOOLS/build_xor_stable_slot_design.py" \
  --manifest "$TOOLS/results/xor_paired_causal_design_v1/manifest.json" \
  --results "$TOOLS/results/xor_paired_causal_server-a_v1/results.tsv" \
  --output-dir "$DESIGN"

cleanup() {
  trap - INT TERM EXIT
  kill "${compact_pid:-}" "${stable_pid:-}" 2>/dev/null || true
  wait "${compact_pid:-}" "${stable_pid:-}" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

python3 "$RUNNER" --manifest "$MANIFEST" --shard all --binary "$BINARY" \
  --output "$RESULTS/compact.tsv" --runs 1,2,3,4 --workers 6 --lanes 4 \
  --timeout 600 --ctg-depth 1 >"$RESULTS/compact.progress" 2>&1 &
compact_pid=$!

python3 "$RUNNER" --manifest "$MANIFEST" --shard all --binary "$STABLE_WRAPPER" \
  --output "$RESULTS/stable.tsv" --runs 1,2,3,4 --workers 6 --lanes 4 \
  --timeout 600 --ctg-depth 1 >"$RESULTS/stable.progress" 2>&1 &
stable_pid=$!

compact_status=0
stable_status=0
wait "$compact_pid" || compact_status=$?
wait "$stable_pid" || stable_status=$?
trap - INT TERM EXIT
printf 'compact_status=%s stable_status=%s\n' "$compact_status" "$stable_status" >"$RESULTS/status.txt"
exit "$((compact_status || stable_status))"
