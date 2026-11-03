#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 "$SCRIPT_DIR/run_ric3_hwmcc2015.py" \
  --year "${HWMCC_YEAR:-2017}" \
  --engine "${RIC3_ENGINE:-ic3}" \
  --workers "${RIC3_WORKERS:-1}" \
  --timeout "${RIC3_TIMEOUT:-300}" \
  --skip-existing \
  "$@"
