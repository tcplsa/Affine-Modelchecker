#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
WORKERS=${FULL_AX_WORKERS:-28}
LANES=${FULL_AX_LANES:-4}
TIMEOUT=${FULL_AX_TIMEOUT:-1800}
BINARY=${FULL_AX_BINARY:-$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker-full-aig-xag}
MANIFEST=${FULL_AX_MANIFEST:-$ROOT/test_tools/compare/results/full_aig_xag_all_years_v1/manifest.json}
OUTPUT=${FULL_AX_OUTPUT:-$ROOT/test_tools/compare/results/full_aig_xag_all_years_v1/results.tsv}

exec python3 "$ROOT/test_tools/compare/run_representation_simplification.py" \
  --manifest "$MANIFEST" \
  --binary "$BINARY" \
  --output "$OUTPUT" \
  --shard all \
  --configs aig_native,xag_native \
  --runs 1 \
  --workers "$WORKERS" \
  --lanes "$LANES" \
  --timeout "$TIMEOUT"
