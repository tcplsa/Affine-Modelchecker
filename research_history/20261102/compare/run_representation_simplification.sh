#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SHARD=${REP_SIMPL_SHARD:-server-a}
WORKERS=${REP_SIMPL_WORKERS:-28}
LANES=${REP_SIMPL_LANES:-4}
TIMEOUT=${REP_SIMPL_TIMEOUT:-300}
RUNS=${REP_SIMPL_RUNS:-1,2}
DESIGN=${REP_SIMPL_DESIGN:-$ROOT/test_tools/compare/results/representation_simplification_design_v1/manifest.json}
BINARY=${REP_SIMPL_BINARY:-$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker-representation-simplification}
OUTPUT=${REP_SIMPL_OUTPUT:-$ROOT/test_tools/compare/results/representation_simplification_${SHARD}_v1/results.tsv}

exec python3 "$ROOT/test_tools/compare/run_representation_simplification.py" \
  --manifest "$DESIGN" \
  --binary "$BINARY" \
  --output "$OUTPUT" \
  --shard "$SHARD" \
  --workers "$WORKERS" \
  --lanes "$LANES" \
  --timeout "$TIMEOUT" \
  --runs "$RUNS"
