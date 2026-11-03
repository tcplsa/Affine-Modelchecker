#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODELS="${SCRIPT_DIR}/xor_shapley_phase4_models.json"
OUT="${XOR_SHAPLEY_DESIGN_OUT:-${SCRIPT_DIR}/results/xor_shapley_phase4_design_v1}"
FEATURES="${OUT}/xor_gate_features.tsv"
MANIFEST="${OUT}/manifest.json"

mkdir -p "${OUT}"
mapfile -t paths < <(python3 -c '
import json, sys
for model in json.load(open(sys.argv[1], encoding="utf-8"))["models"]:
    print(model["path"])
' "${MODELS}")

python3 "${SCRIPT_DIR}/extract_xor_gate_features.py" "${paths[@]}" \
    --output "${FEATURES}" \
    --workers "${XOR_SHAPLEY_FEATURE_WORKERS:-2}" \
    --support-limit 1
python3 "${SCRIPT_DIR}/build_xor_shapley_design.py" \
    --models "${MODELS}" \
    --features "${FEATURES}" \
    --output-dir "${OUT}/allowlists" \
    --manifest "${MANIFEST}"

echo "prepared ${MANIFEST}"
