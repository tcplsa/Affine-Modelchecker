#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
MC=${MC:-$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker}
MERGE=$ROOT/test_tools/compare/merge_pdr_invariants.py
BASE=$ROOT/test_tools/compare/results/vgasim_invariant_transfer_v1
ROUND=${ROUND:-$BASE/harvest-round1}
LIMIT=${LIMIT:-600}
P075_BASE=${P075_BASE:-$BASE/p070.inv}
P088_BASE=${P088_BASE:-$BASE/transferable-union.inv}

mkdir -p "$ROUND"

run_target() {
  local name=$1
  local model=$2
  local invariant=$3
  timeout "${LIMIT}s" env \
    MC_PDR_SEED=740001 \
    MC_PDR_STATS=1 \
    MC_PDR_PROGRESS_SECONDS=30 \
    MC_PDR_INVARIANT_IMPORT="$invariant" \
    MC_PDR_INVARIANT_SNAPSHOT="$ROUND/$name-thread-%t.inv" \
    MC_PDR_MIC_ORDER_LANES=legacy,feedback,distance-feedback,distance-near \
    MC_PDR_OBLIGATION_ORDER_LANES=legacy,legacy,legacy,source-far \
    MC_PDR_CERTIFY_EARLY_LANES=0,1,1,1 \
    MC_PDR_CERTIFY_EARLY_MAX_CUBE=16 \
    MC_PDR_SHARE_INDUCTIVE_BUDGET=16 \
    "$MC" --forward-aig 4 "$model" > "$ROUND/$name.log" 2>&1 || true
}

p075_model=$ROOT/test_tools/hwmcc2020/data/2019/wolf/2019C/vgasim_imgfifo-p075.aig
p088_model=$ROOT/test_tools/hwmcc2020/data/2019/wolf/2019C/vgasim_imgfifo-p088.aig

run_target p075 "$p075_model" "$P075_BASE" &
p075_pid=$!
run_target p088 "$p088_model" "$P088_BASE" &
p088_pid=$!
wait "$p075_pid"
wait "$p088_pid"

"$MERGE" --output "$ROUND/p075-merged.inv" \
  "$P075_BASE" "$ROUND"/p075-thread-*.inv
"$MERGE" --output "$ROUND/p088-merged.inv" \
  "$P088_BASE" "$ROUND"/p088-thread-*.inv

for name in p075 p088; do
  model=$p075_model
  if [[ $name == p088 ]]; then
    model=$p088_model
  fi
  timeout 20s env \
    MC_PDR_STATS=1 \
    MC_PDR_INVARIANT_IMPORT="$ROUND/$name-merged.inv" \
    MC_PDR_INVARIANT_PRUNE=1 \
    "$MC" -aig "$model" > "$ROUND/$name-closure-check.log" 2>&1 || true
  status=$(sed -n 's/.*PDR_INVARIANT_IMPORT status=\([^ ]*\).*/\1/p' \
    "$ROUND/$name-closure-check.log" | tail -n 1)
  proof=$(sed -n 's/.*proves_target=\([01]\).*/\1/p' \
    "$ROUND/$name-closure-check.log" | tail -n 1)
  clauses=$(awk 'NR > 1 && $1 != "c" { count++ } END { print count + 0 }' \
    "$ROUND/$name-merged.inv")
  printf '%s\tclauses=%s\tstatus=%s\tproves_target=%s\n' \
    "$name" "$clauses" "${status:-unknown}" "${proof:-0}"
done
