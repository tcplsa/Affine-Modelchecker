#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl/test_tools/compare

python3 "$ROOT/analyze_ric3_structural_feedback.py" \
  --input-glob "$ROOT/results/ric3_structural_feedback_v3/shard*.tsv" \
  --feedback-dir "$ROOT/results/ric3_structural_feedback_v2/feedback" \
  --timeout 1800 \
  --output "$ROOT/results/ric3_structural_feedback_v3/report.md"

python3 "$ROOT/analyze_ric3_aa_noise.py" \
  --input-glob "$ROOT/results/ric3_aa_noise_v1/repeat*.tsv" \
  --treatment-inputs \
    "$ROOT/results/ric3_order_concurrent_v1/seed1110001.tsv" \
    "$ROOT/results/ric3_order_concurrent_v1/seed1120001.tsv" \
    "$ROOT/results/ric3_order_concurrent_v1/seed1130001.tsv" \
  --output "$ROOT/results/ric3_aa_noise_v1/report.md"
