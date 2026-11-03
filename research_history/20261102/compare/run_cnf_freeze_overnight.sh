#!/usr/bin/env bash
set -euo pipefail

ROLE="${1:-current}"
ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
MANIFEST="$TOOLS/results/initial_cnf_final_holdout_design_v1/manifest.json"
BINARY="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker-cnf-freeze-v1"

run_one() {
  local suite="$1" seed="$2" timeout="$3" workers="$4" tag="$5"
  local dir="$TOOLS/results/cnf_freeze_${tag}_v1"
  mkdir -p "$dir"
  python3 "$TOOLS/run_cnf_freeze_campaign.py" \
    --suite "$suite" --manifest "$MANIFEST" --binary "$BINARY" \
    --output "$dir/results.tsv" --workers "$workers" \
    --timeout "$timeout" --seed "$seed"
  python3 "$TOOLS/analyze_cnf_freeze_campaign.py" \
    --suite "$suite" --manifest "$MANIFEST" --input "$dir/results.tsv" \
    --output "$dir/report.md"
}

case "$ROLE" in
  current)
    run_one hard 830001 180 2 hard_seed_a
    run_one hard 930001 180 2 hard_seed_b
    python3 "$TOOLS/analyze_cnf_freeze_campaign.py" \
      --suite hard --manifest "$MANIFEST" \
      --input "$TOOLS/results/cnf_freeze_hard_seed_a_v1/results.tsv" \
              "$TOOLS/results/cnf_freeze_hard_seed_b_v1/results.tsv" \
      --output "$TOOLS/results/cnf_freeze_hard_combined_v1_report.md"
    ;;
  server-b)
    run_one screen 810001 45 2 screen_seed_a
    run_one screen 910001 45 2 screen_seed_b
    python3 "$TOOLS/analyze_cnf_freeze_campaign.py" \
      --suite screen --manifest "$MANIFEST" \
      --input "$TOOLS/results/cnf_freeze_screen_seed_a_v1/results.tsv" \
              "$TOOLS/results/cnf_freeze_screen_seed_b_v1/results.tsv" \
      --output "$TOOLS/results/cnf_freeze_screen_combined_v1_report.md"
    ;;
  *)
    echo "usage: $0 {current|server-b}" >&2
    exit 2
    ;;
esac
