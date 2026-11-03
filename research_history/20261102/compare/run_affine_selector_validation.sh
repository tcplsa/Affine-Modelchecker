#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OUT=${AFFINE_SELECTOR_OUT:-$ROOT/test_tools/compare/results/pathb_affine_selector_validation_v1}
MANIFEST=$OUT/manifest.json
BINARY=${AFFINE_SELECTOR_BINARY:-$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker-gauss-auto-v1}

mkdir -p "$OUT"
python3 "$ROOT/test_tools/compare/pathb/build_affine_selector_validation.py" \
  --input "$ROOT/test_tools/compare/results/pathb_affine_full_scope_v1/manifest.json" \
  --external-manifest "$ROOT/test_tools/compare/results/pathb_public_affine_rtl_v1/manifest.json" \
  --output "$MANIFEST"
sha256sum "$MANIFEST" > "$OUT/manifest.sha256"
python3 "$ROOT/test_tools/compare/pathb/run_affine_selector_oracle.py" \
  --manifest "$MANIFEST" \
  --binary "$BINARY" \
  --output "$OUT/oracle_120s.tsv" \
  --timeout "${AFFINE_SELECTOR_TIMEOUT:-120}" \
  --workers "${AFFINE_SELECTOR_WORKERS:-24}" \
  --seed "${AFFINE_SELECTOR_SEED:-996101}" \
  ${AFFINE_SELECTOR_EXTRA_ARGS:-}
python3 "$ROOT/test_tools/compare/pathb/run_affine_selector_oracle.py" \
  --manifest "$MANIFEST" \
  --binary "$BINARY" \
  --output "$OUT/online_default_120s.tsv" \
  --timeout "${AFFINE_SELECTOR_TIMEOUT:-120}" \
  --workers "${AFFINE_SELECTOR_WORKERS:-24}" \
  --seed "${AFFINE_SELECTOR_SEED:-996101}" \
  --mode online
python3 "$ROOT/test_tools/compare/pathb/analyze_affine_selector_validation.py" \
  --input "$OUT/oracle_120s.tsv" \
  --online-input "$OUT/online_default_120s.tsv" \
  --report "$OUT/report.md" \
  --summary "$OUT/summary.json" \
  --timeout "${AFFINE_SELECTOR_TIMEOUT:-120}"
