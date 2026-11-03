#!/usr/bin/env bash
set -euo pipefail

SESSION=${PRE_PHASE_SESSION:-pre-phase-v1}
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "tmux session already exists: $SESSION"
    exit 1
fi
tmux new-session -d -s "$SESSION" -c /home/wudl
tmux send-keys -t "$SESSION":0 \
    'PRE_PHASE_MODEL_WORKERS=5 test_tools/compare/run_predecessor_phase_portfolio.sh' C-m
echo "started: $SESSION"
echo "attach with: tmux attach -t $SESSION"
