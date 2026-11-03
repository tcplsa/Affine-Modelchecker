#!/usr/bin/env bash
set -euo pipefail

SESSION=${RIC3_BASELINE_SESSION:-ric3-4core-base}
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "tmux session already exists: $SESSION"
    echo "attach with: tmux attach -t $SESSION"
    exit 1
fi

tmux new-session -d -s "$SESSION" -c /home/wudl
tmux send-keys -t "$SESSION":0 \
    'RIC3_BASELINE_MODEL_WORKERS=6 test_tools/compare/run_ric3_four_core_baseline.sh' C-m
echo "started: $SESSION"
echo "attach with: tmux attach -t $SESSION"
