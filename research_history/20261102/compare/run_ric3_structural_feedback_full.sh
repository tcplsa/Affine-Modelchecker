#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl/test_tools/compare
RESULTS="$ROOT/results/ric3_structural_feedback_v2"
SELECTION="$ROOT/results/bve_aig_hard_domain_v1/selection.json"
BINARY=/home/wudl/rIC3/target/release/ric3

mkdir -p "$RESULTS/feedback"

python3 "$ROOT/run_ric3_structural_feedback.py" \
  --phase scout \
  --selection "$SELECTION" \
  --binary "$BINARY" \
  --feedback-dir "$RESULTS/feedback" \
  --output "$RESULTS/scout.tsv" \
  --workers 57 \
  --timeout 300 \
  --seed 1700001

python3 "$ROOT/run_ric3_structural_feedback.py" \
  --phase specialist \
  --selection "$SELECTION" \
  --binary "$BINARY" \
  --feedback-dir "$RESULTS/feedback" \
  --output "$RESULTS/specialist.tsv" \
  --workers 4 \
  --timeout 1800 \
  --seed 1800001 \
  --replicas 4

python3 "$ROOT/analyze_ric3_structural_feedback.py" \
  --input "$RESULTS/specialist.tsv" \
  --feedback-dir "$RESULTS/feedback" \
  --timeout 1800 \
  --output "$RESULTS/report.md"
