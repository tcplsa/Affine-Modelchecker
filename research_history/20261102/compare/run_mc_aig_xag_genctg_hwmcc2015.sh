#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

args=(
  --pdr "${MC_AXG_PDR:-1}"
  --workers "${MC_AXG_WORKERS:-80}"
  --timeout "${MC_AXG_TIMEOUT:-1800}"
  --group-file "${MC_AXG_GROUP_FILE:-$SCRIPT_DIR/hwmcc2015_groups_ric3_1800.json}"
  --group "${MC_AXG_GROUP:-all}"
)

if [[ "${MC_AXG_SKIP_EXISTING:-1}" != "0" ]]; then
  args+=(--skip-existing)
fi

python3 "$SCRIPT_DIR/run_mc_aig_xag_genctg_hwmcc2015.py" "${args[@]}" "$@"
