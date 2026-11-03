#!/usr/bin/env bash
set -euo pipefail

for session in convergence_certify convergence_order convergence_full \
               convergence_order_clean; do
    while tmux has-session -t "$session" 2>/dev/null; do
        sleep 30
    done
done

ROOT=/home/wudl/test_tools/compare
python3 "$ROOT/analyze_convergence_auto_screen.py" \
    --mic-results "$ROOT/results/mc_distance_mic_screen_v1" \
    --obligation-results "$ROOT/results/mc_distance_obligation_screen_v1" \
    --results "$ROOT/results/mc_convergence_auto_screen_v1" \
    --manifest "$ROOT/results/mc_hard_breakthrough_screen_v1/diagnostic_progress_candidates.json" \
    --output "$ROOT/results/mc_convergence_auto_screen_v1/report.md"
