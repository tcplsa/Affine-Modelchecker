#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
export MC_PDR_PROGRESS_SECONDS="${MC_PDR_PROGRESS_SECONDS:-60}"

exec python3 "$ROOT/test_tools/compare/run_mc_hard_diagnostic.py" \
  --manifest "$ROOT/test_tools/compare/results/mc_ric3_hard_gap_v1/mc_hard_diagnostic_cohort.json" \
  --binary "$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker" \
  --output "${MC_HARD_OUTPUT:-$ROOT/test_tools/compare/results/mc_ric3_hard_gap_v1/aig_baseline_progress_600.tsv}" \
  --timeout "${MC_HARD_TIMEOUT:-600}" \
  --workers "${MC_HARD_WORKERS:-28}" \
  --seed "${MC_HARD_SEED:-730001}" \
  --strategy "${MC_HARD_STRATEGY:-baseline}"
