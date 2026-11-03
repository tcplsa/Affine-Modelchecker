#!/usr/bin/env bash
set -euo pipefail

SESSION=${SOURCE_PHASE_SESSION:-source-phase-v1}
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "tmux session already exists: $SESSION"
    exit 1
fi
tmux new-session -d -s "$SESSION" -c /home/wudl
tmux send-keys -t "$SESSION":0 \
    'SOURCE_PHASE_MODEL_WORKERS=6 test_tools/compare/run_source_directed_portfolio.sh' C-m
echo "started: $SESSION"
echo "attach with: tmux attach -t $SESSION"
