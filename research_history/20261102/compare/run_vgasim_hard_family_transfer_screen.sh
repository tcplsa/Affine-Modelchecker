#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
MC=${MC:-$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker}
BASE=$ROOT/test_tools/compare/results/vgasim_invariant_transfer_v1
OUT=${OUT:-$ROOT/test_tools/compare/results/vgasim_hard_family_transfer_v1}
LIMIT=${LIMIT:-600}
INVARIANT=${INVARIANT:-$BASE/easy-sibling-union.inv}

mkdir -p "$OUT/snapshots"

models=(
  "2019-p039|$ROOT/test_tools/hwmcc2019/data/vgasim_imgfifo-p039.aig"
  "2019-p051|$ROOT/test_tools/hwmcc2019/data/vgasim_imgfifo-p051.aig"
  "2019-p088|$ROOT/test_tools/hwmcc2019/data/vgasim_imgfifo-p088.aig"
  "2019-p091|$ROOT/test_tools/hwmcc2019/data/vgasim_imgfifo-p091.aig"
  "2019-p107|$ROOT/test_tools/hwmcc2019/data/vgasim_imgfifo-p107.aig"
  "2019-p111|$ROOT/test_tools/hwmcc2019/data/vgasim_imgfifo-p111.aig"
  "2020-p036|$ROOT/test_tools/hwmcc2020/data/2019/wolf/2019C/vgasim_imgfifo-p036.aig"
  "2020-p075|$ROOT/test_tools/hwmcc2020/data/2019/wolf/2019C/vgasim_imgfifo-p075.aig"
  "2020-p088|$ROOT/test_tools/hwmcc2020/data/2019/wolf/2019C/vgasim_imgfifo-p088.aig"
  "2020-p110|$ROOT/test_tools/hwmcc2020/data/2019/wolf/2019C/vgasim_imgfifo-p110.aig"
  "2020-p111|$ROOT/test_tools/hwmcc2020/data/2019/wolf/2019C/vgasim_imgfifo-p111.aig"
)

pids=()
for item in "${models[@]}"; do
  name=${item%%|*}
  model=${item#*|}
  (
    timeout "${LIMIT}s" env \
      MC_PDR_SEED=750001 \
      MC_PDR_STATS=1 \
      MC_PDR_PROGRESS_SECONDS=30 \
      MC_PDR_INVARIANT_IMPORT="$INVARIANT" \
      MC_PDR_INVARIANT_PRUNE=1 \
      MC_PDR_INVARIANT_SNAPSHOT="$OUT/snapshots/$name-thread-%t.inv" \
      "$MC" --forward-aig 4 "$model" > "$OUT/$name.log" 2>&1 || true
  ) &
  pids+=("$!")
done

for pid in "${pids[@]}"; do
  wait "$pid"
done

printf 'model\tresult\tinstalled\tpruned\tproves_target\tbest_depth\n'
for item in "${models[@]}"; do
  name=${item%%|*}
  log=$OUT/$name.log
  result=$(sed -n 's/^result: //p' "$log" | tail -n 1)
  import=$(rg 'PDR_INVARIANT_IMPORT status=accepted' "$log" | head -n 1 || true)
  installed=$(sed -n 's/.*clauses=\([0-9][0-9]*\).*/\1/p' <<< "$import")
  pruned=$(sed -n 's/.*pruned=\([0-9][0-9]*\).*/\1/p' <<< "$import")
  proof=$(sed -n 's/.*proves_target=\([01]\).*/\1/p' <<< "$import")
  best_depth=$(sed -n 's/.*depth=\([-0-9][0-9]*\).*/\1/p' "$log" \
    | sort -n | tail -n 1)
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "${result:-timeout}" \
    "${installed:-0}" "${pruned:-0}" "${proof:-0}" "${best_depth:--1}"
done
