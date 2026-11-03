#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OUT=${HWMCC_GAUSS_OUT:-$ROOT/test_tools/compare/results/hwmcc_gauss_full_v1}
MANIFEST=${HWMCC_GAUSS_MANIFEST:-$ROOT/test_tools/compare/results/full_aig_xag_all_years_v1/manifest.json}
BINARY=${HWMCC_GAUSS_BINARY:-$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker}

mkdir -p "$OUT"
exec python3 "$ROOT/test_tools/compare/pathb/run_hwmcc_gauss_full.py" \
  --manifest "$MANIFEST" \
  --binary "$BINARY" \
  --output "$OUT/results.tsv" \
  --timeout "${HWMCC_GAUSS_TIMEOUT:-1800}" \
  --workers "${HWMCC_GAUSS_WORKERS:-28}" \
  --lanes "${HWMCC_GAUSS_LANES:-4}" \
  --seed "${HWMCC_GAUSS_SEED:-997001}" \
  ${HWMCC_GAUSS_EXTRA_ARGS:-}
