#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SEED=${1:?usage: run_bve_width_confirm.sh seed}

export BVE_WIDTH_RESULT_DIR=${BVE_WIDTH_CONFIRM_RESULT_DIR:-$SCRIPT_DIR/results/bve_width_confirm_v1}
export BVE_WIDTH_SELECTION=${BVE_WIDTH_CONFIRM_SELECTION:-$BVE_WIDTH_RESULT_DIR/selection.json}
export BVE_WIDTH_TIMEOUT=${BVE_WIDTH_CONFIRM_TIMEOUT:-1800}
export BVE_WIDTH_WORKERS=${BVE_WIDTH_CONFIRM_WORKERS:-14}
export BVE_WIDTH_WEIGHTS="0 2"

exec "$SCRIPT_DIR/run_bve_width_screen.sh" ric3 "$SEED"
