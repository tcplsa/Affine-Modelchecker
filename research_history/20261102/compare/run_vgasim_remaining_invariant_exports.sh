#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
MC=${MC:-$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker}
OUT=${OUT:-$ROOT/test_tools/compare/results/vgasim_invariant_transfer_v1}
LIMIT=${LIMIT:-300}

mkdir -p "$OUT"

models=(
  "p036|$ROOT/test_tools/hwmcc2020/data/2019/wolf/2019C/vgasim_imgfifo-p036.aig"
  "p110|$ROOT/test_tools/hwmcc2020/data/2019/wolf/2019C/vgasim_imgfifo-p110.aig"
  "p111|$ROOT/test_tools/hwmcc2020/data/2019/wolf/2019C/vgasim_imgfifo-p111.aig"
  "p039|$ROOT/test_tools/hwmcc2019/data/vgasim_imgfifo-p039.aig"
  "p051|$ROOT/test_tools/hwmcc2019/data/vgasim_imgfifo-p051.aig"
  "p058|$ROOT/test_tools/hwmcc2019/data/vgasim_imgfifo-p058.aig"
  "p085|$ROOT/test_tools/hwmcc2019/data/vgasim_imgfifo-p085.aig"
  "p091|$ROOT/test_tools/hwmcc2019/data/vgasim_imgfifo-p091.aig"
  "p107|$ROOT/test_tools/hwmcc2019/data/vgasim_imgfifo-p107.aig"
)

pids=()
for item in "${models[@]}"; do
  name=${item%%|*}
  model=${item#*|}
  (
    timeout "${LIMIT}s" env \
      MC_PDR_SEED=730001 \
      MC_PDR_STATS=1 \
      MC_PDR_INVARIANT_EXPORT="$OUT/$name.inv" \
      "$MC" -aig "$model" > "$OUT/$name-export.log" 2>&1 || true
  ) &
  pids+=("$!")
done

for pid in "${pids[@]}"; do
  wait "$pid"
done

for item in "${models[@]}"; do
  name=${item%%|*}
  if [[ -s $OUT/$name.inv ]]; then
    clauses=$(awk 'NR > 1 && $1 != "c" { count++ } END { print count + 0 }' \
      "$OUT/$name.inv")
    result=$(sed -n 's/^result: //p' "$OUT/$name-export.log" | tail -n 1)
    printf '%s\t%s\t%s\n' "$name" "${result:-unknown}" "$clauses"
  else
    printf '%s\tunknown\t0\n' "$name"
  fi
done
