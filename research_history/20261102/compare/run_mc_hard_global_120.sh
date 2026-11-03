#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
DEEP_RESULT="$ROOT/test_tools/compare/results/mc_ric3_hard_gap_v1/aig_baseline_progress_600.tsv"

while [[ ! -f "$DEEP_RESULT" ]] || (( $(wc -l < "$DEEP_RESULT") < 111 )); do
  sleep 30
done

export MC_PDR_PROGRESS_SECONDS="${MC_PDR_PROGRESS_SECONDS:-30}"
exec python3 "$ROOT/test_tools/compare/run_mc_hard_diagnostic.py" \
  --manifest "$ROOT/test_tools/compare/results/ric3_hard_3600_v1/analysis/ric3_4_hard_3600.json" \
  --binary "$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker" \
  --output "$ROOT/test_tools/compare/results/mc_ric3_hard_global_v1/aig_baseline_progress_120.tsv" \
  --timeout "${MC_GLOBAL_TIMEOUT:-120}" \
  --workers "${MC_GLOBAL_WORKERS:-28}" \
  --seed "${MC_GLOBAL_SEED:-730001}" \
  --strategy baseline
