#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SHARD=${1:-server-a}
BINARY=${REP_SIMPL_BINARY:-$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker-representation-simplification}

if [[ $SHARD == server-a ]]; then
  MANIFEST="$ROOT/test_tools/compare/results/xor_stable_slot_design_v1/manifest.json"
else
  MANIFEST="$ROOT/test_tools/compare/results/xor_stable_slot_design_server-b_v1/manifest.json"
fi
PRE_DIR="$ROOT/test_tools/compare/results/xor_precanonical_${SHARD}_v1"
mkdir -p "$PRE_DIR"

python3 "$ROOT/test_tools/compare/run_xor_canonical_mechanism.py" \
  --manifest "$MANIFEST" \
  --binary "$BINARY" \
  --output "$PRE_DIR/results.tsv" \
  --modes precanonical_compact,precanonical_stable \
  --runs 1,2,3,4 \
  --workers 28 \
  --lanes 4 \
  --timeout 600

REP_SIMPL_SHARD="$SHARD" "$ROOT/test_tools/compare/run_representation_simplification.sh"
