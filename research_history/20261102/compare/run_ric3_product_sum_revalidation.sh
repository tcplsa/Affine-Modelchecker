#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SEED=${1:?usage: run_ric3_product_sum_revalidation.sh seed}

export BVE_WIDTH_RESULT_DIR=${RIC3_PRODUCT_SUM_REVALIDATION_RESULT_DIR:-$SCRIPT_DIR/results/ric3_product_sum_revalidation_v1}
export BVE_WIDTH_SELECTION=${RIC3_PRODUCT_SUM_REVALIDATION_SELECTION:-$SCRIPT_DIR/results/bve_width_blind_v1/selection.json}
export BVE_WIDTH_TIMEOUT=${RIC3_PRODUCT_SUM_REVALIDATION_TIMEOUT:-1800}
export BVE_WIDTH_WORKERS=${RIC3_PRODUCT_SUM_REVALIDATION_WORKERS:-28}
export BVE_WIDTH_REPLICAS=4
export BVE_WIDTH_WEIGHTS="0"
export BVE_WIDTH_RIC3_ORDER=legacy

exec "$SCRIPT_DIR/run_bve_width_screen.sh" ric3 "$SEED"
