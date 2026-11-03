#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

args=(
  --mode "${MC_CTG_MODE:-xag}" \
  --pdr "${MC_CTG_PDR:-1}" \
  --workers "${MC_CTG_WORKERS:-100}" \
  --timeout "${MC_CTG_TIMEOUT:-1800}" \
  --group-file "${MC_CTG_GROUP_FILE:-$SCRIPT_DIR/hwmcc2015_groups_ric3_1800.json}" \
  --group "${MC_CTG_GROUP:-all}"
)

if [[ "${MC_CTG_SKIP_EXISTING:-1}" != "0" ]]; then
  args+=(--skip-existing)
fi

python3 "$SCRIPT_DIR/run_mc_ctg_hwmcc2015.py" "${args[@]}" "$@"
