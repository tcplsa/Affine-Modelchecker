#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
MC="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker"
SOURCE="$ROOT/test_tools/compare/results/pathb_crc_gauss_boundary_1800_confirm_v1/seed985011.tsv"
BENCH="$ROOT/test_tools/compare/results/pathb_crc_gauss_boundary_v1/benchmarks"
OUT="${AFFINE_INVARIANT_OUT:-$ROOT/test_tools/compare/results/pathb_affine_invariant_probe_v1}"
mkdir -p "$OUT/logs"

tail -n +2 "$SOURCE" | cut -f1 | while read -r name; do
  model="$BENCH/$name.aag"
  for config in baseline invariant; do
    enabled=0
    if [[ $config == invariant ]]; then
      enabled=1
    fi
    log="$OUT/logs/${name}__${config}.log"
    echo "RUN $name $config"
    set +e
    timeout 45s env \
      MC_PDR_SEED=985011 \
      MC_PDR_SOLVER=cmsat \
      MC_PDR_CMSAT_GAUSS=1 \
      MC_PDR_GUARDED_AFFINE=1 \
      MC_PDR_GUARDED_AFFINE_MAX_CONTROLS=2 \
      MC_PDR_GUARDED_AFFINE_VALIDATE=1 \
      MC_PDR_AFFINE_INVARIANTS="$enabled" \
      MC_PDR_AFFINE_INVARIANT_MAX_WIDTH=32 \
      MC_PDR_STATS=1 \
      /usr/bin/time -f 'PROBE_WALL=%e PROBE_RSS_KB=%M' \
      "$MC" -xag "$model" >"$log" 2>&1
    status=$?
    set -e
    echo "PROBE_STATUS=$status" >>"$log"
  done
done

{
  printf 'model\tconfig\tstatus\tresult\twall_s\trank\tinvariants\tselected\tmax_width\tgauss_checks\tgauss_row_xors\n'
  for log in "$OUT"/logs/*.log; do
    file=$(basename "$log" .log)
    config=${file##*__}
    model=${file%__*}
    status=$(sed -n 's/^PROBE_STATUS=//p' "$log" | tail -1)
    result=$(sed -n 's/^result: //p' "$log" | tail -1)
    wall=$(sed -n 's/.*PROBE_WALL=\([^ ]*\).*/\1/p' "$log" | tail -1)
    affine=$(grep 'c PDR_AFFINE ' "$log" | tail -1 || true)
    gauss=$(grep 'c CMSAT_GAUSS_TOTAL ' "$log" | tail -1 || true)
    rank=$(sed -n 's/.* invariant_reachable_rank=\([0-9]*\).*/\1/p' <<<"$affine")
    invariants=$(sed -n 's/.* invariant_count=\([0-9]*\).*/\1/p' <<<"$affine")
    selected=$(sed -n 's/.* invariant_selected=\([0-9]*\).*/\1/p' <<<"$affine")
    max_width=$(sed -n 's/.* invariant_support_max=\([0-9]*\).*/\1/p' <<<"$affine")
    checks=$(sed -n 's/.* checks=\([0-9]*\).*/\1/p' <<<"$gauss")
    row_xors=$(sed -n 's/.* row_xors=\([0-9]*\).*/\1/p' <<<"$gauss")
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$model" "$config" "$status" "$result" "$wall" "$rank" \
      "$invariants" "$selected" "$max_width" "$checks" "$row_xors"
  done
} >"$OUT/summary.tsv"

column -t -s $'\t' "$OUT/summary.tsv" 2>/dev/null || cat "$OUT/summary.tsv"
