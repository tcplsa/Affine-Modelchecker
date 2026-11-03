#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^(server-a|server-b)$ ]]; then
  echo "usage: $0 server-a|server-b" >&2
  exit 2
fi

SHARD="$1"
ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
BINARY="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker-xor-canonical-mechanism"
if [[ "$SHARD" == server-a ]]; then
  MANIFEST="$TOOLS/results/xor_stable_slot_design_v1/manifest.json"
  OUT="$TOOLS/results/xor_canonical_mechanism_server-a_v1"
else
  MANIFEST="$TOOLS/results/xor_stable_slot_design_server-b_v1/manifest.json"
  OUT="$TOOLS/results/xor_canonical_mechanism_server-b_v1"
fi
mkdir -p "$OUT"

python3 "$TOOLS/run_xor_canonical_mechanism.py" \
  --manifest "$MANIFEST" --binary "$BINARY" --output "$OUT/results.tsv" \
  --modes compact,stable,canonical_compact,canonical_stable \
  --runs 1,2,3,4 --workers "${XOR_CANONICAL_WORKERS:-28}" \
  --lanes "${XOR_CANONICAL_LANES:-4}" --timeout "${XOR_CANONICAL_TIMEOUT:-600}" \
  --ctg-depth 1 >"$OUT/progress.txt" 2>&1

python3 "$TOOLS/analyze_xor_canonical_mechanism.py" "$OUT/results.tsv" \
  --output "$OUT/report.md" >"$OUT/analysis.txt"
printf 'completed\t%s\n' "$(date -Iseconds)" >"$OUT/status.tsv"
