#!/usr/bin/env bash
set -euo pipefail

STRUCTURAL_SESSION=ric3_pred_full
NOISE_SESSION=ric3_aa_noise
STRUCTURAL_TSV=/home/wudl/test_tools/compare/results/ric3_structural_feedback_v2/specialist.tsv

# Let the current expensive batch produce at least one more durable row before
# lowering model concurrency. The TSV includes one header line.
while tmux has-session -t "$STRUCTURAL_SESSION" 2>/dev/null; do
  lines=$(wc -l < "$STRUCTURAL_TSV" 2>/dev/null || printf '0')
  if (( lines > 6 )); then
    tmux send-keys -t "$STRUCTURAL_SESSION" C-c
    break
  fi
  sleep 20
done

while tmux has-session -t "$STRUCTURAL_SESSION" 2>/dev/null; do
  sleep 2
done

tmux new-session -d -s "$STRUCTURAL_SESSION" \
  /home/wudl/test_tools/compare/run_ric3_structural_feedback_full.sh

if ! tmux has-session -t "$NOISE_SESSION" 2>/dev/null; then
  tmux new-session -d -s "$NOISE_SESSION" \
    /home/wudl/test_tools/compare/run_ric3_aa_noise_full.sh
fi
