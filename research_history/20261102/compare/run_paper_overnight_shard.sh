#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! $1 =~ ^[012]$ ]]; then
  echo "usage: $0 SHARD_INDEX  # 0, 1, or 2" >&2
  exit 2
fi

SHARD=$1
ROOT=/home/wudl/test_tools/compare
RIC3=/home/wudl/rIC3/target/release/ric3
STRUCTURAL="$ROOT/results/ric3_structural_feedback_v3"
NOISE="$ROOT/results/ric3_aa_noise_v1"
SELECTION="$ROOT/results/bve_aig_hard_domain_v1/selection.json"
FEEDBACK="$ROOT/results/ric3_structural_feedback_v2/feedback"
MANIFEST="$ROOT/results/full_aig_xag_all_years_v1/manifest.json"
AA_SELECTION="$NOISE/selection.json"
REPEAT=$((SHARD + 1))

mkdir -p "$STRUCTURAL" "$NOISE"

children=()
cleanup() {
  for pid in "${children[@]:-}"; do
    kill -TERM -- "-$pid" 2>/dev/null || true
  done
}
trap cleanup INT TERM EXIT

setsid python3 "$ROOT/run_ric3_structural_feedback.py" \
  --phase specialist \
  --selection "$SELECTION" \
  --binary "$RIC3" \
  --feedback-dir "$FEEDBACK" \
  --output "$STRUCTURAL/shard${SHARD}.tsv" \
  --workers 4 \
  --timeout 1800 \
  --seed 1800001 \
  --replicas 4 \
  --shard-index "$SHARD" \
  --shard-count 3 &
children+=("$!")

setsid python3 "$ROOT/run_ric3_aa_noise.py" \
  --manifest "$MANIFEST" \
  --selection "$AA_SELECTION" \
  --binary "$RIC3" \
  --output "$NOISE/repeat${REPEAT}.tsv" \
  --seed 1900001 \
  --workers 1 \
  --timeout 300 &
children+=("$!")

status=0
for pid in "${children[@]}"; do
  wait "$pid" || status=$?
done
trap - INT TERM EXIT
exit "$status"
