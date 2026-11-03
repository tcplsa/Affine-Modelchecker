#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 "$SCRIPT_DIR/compare_mc_input_swap.py" \
  --all-hwmcc2015 \
  --mode xag \
  --mc-pdr "${MC_PDR_THREADS:-1}" \
  --workers "${MC_SWAP_WORKERS:-80}" \
  --timeout "${MC_SWAP_TIMEOUT:-180}" \
  --max-pairs "${MC_SWAP_MAX_PAIRS:-12}" \
  --sample "${MC_SWAP_SAMPLE:-first}" \
  --sample-seed "${MC_SWAP_SAMPLE_SEED:-1}" \
  --repeats "${MC_SWAP_REPEATS:-1}" \
  --summary-every "${MC_SWAP_SUMMARY_EVERY:-50}" \
  --skip-existing \
  --output "$SCRIPT_DIR/results/compare_mc_input_swap_hwmcc2015.tsv" \
  --summary-output "$SCRIPT_DIR/results/compare_mc_input_swap_hwmcc2015_summary.tsv" \
  "$@"
