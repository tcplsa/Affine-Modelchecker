#!/usr/bin/env bash
set -euo pipefail

SESSION=${RIC3_REAL4_SESSION:-ric3-real4-v2}
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "tmux session already exists: $SESSION"
    exit 1
fi
tmux new-session -d -s "$SESSION" -c /home/wudl
tmux send-keys -t "$SESSION":0 \
    'RIC3_REAL4_MODEL_WORKERS=9 test_tools/compare/run_ric3_real_four_core.sh' C-m
echo "started: $SESSION"
echo "attach with: tmux attach -t $SESSION"
