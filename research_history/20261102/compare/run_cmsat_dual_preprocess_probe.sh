#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
MC="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker"
OUT="${CMSAT_DUAL_PREPROCESS_OUT:-$ROOT/test_tools/compare/results/cmsat_dual_preprocess_probe_v1}"
mkdir -p "$OUT/logs"

models=(
  "$ROOT/test_tools/compare/results/pathb_public_affine_rtl_v1/aiger/verilog_lfsr_style_crc32c_w32_d16.aag"
  "$ROOT/test_tools/compare/results/pathb_public_affine_rtl_v1/aiger/opentitan_prim_lfsr_transition_w64_e8.aag"
  "$ROOT/test_tools/compare/results/pathb_crc_frame_residue_v1/benchmarks/crc_frame_residue_fcs_topologybalanced_payload_cycles4_polynomial79764919_seed987524_symbol_bits32_width32.aag"
)
configs=(base tree dag bve tree_bve dag_bve)

for model in "${models[@]}"; do
  name=$(basename "$model" .aag)
  for config in "${configs[@]}"; do
    island=0
    dag=0
    bve=0
    if [[ $config == tree || $config == tree_bve || $config == dag || $config == dag_bve ]]; then
      island=1
    fi
    if [[ $config == dag || $config == dag_bve ]]; then
      dag=1
    fi
    if [[ $config == bve || $config == tree_bve || $config == dag_bve ]]; then
      bve=1
    fi
    log="$OUT/logs/${name}__${config}.log"
    echo "RUN model=$name config=$config"
    set +e
    timeout 120s env \
      MC_PDR_SOLVER=cmsat \
      MC_PDR_CMSAT_GAUSS=1 \
      MC_PDR_AFFINE_ISLAND_REPLACE="$island" \
      MC_PDR_AFFINE_ISLAND_DAG="$dag" \
      MC_PDR_AFFINE_ISLAND_MIN_XORS=4 \
      MC_PDR_AFFINE_ISLAND_VALIDATE=1 \
      MC_PDR_CMSAT_BOUNDARY_BVE="$bve" \
      MC_PDR_STATS=1 \
      /usr/bin/time -f 'PROBE_WALL=%e PROBE_RSS_KB=%M' \
      "$MC" -xag "$model" >"$log" 2>&1
    status=$?
    set -e
    printf 'PROBE_STATUS=%s\n' "$status" >>"$log"
  done
done

{
  printf 'model\tconfig\tstatus\tresult\twall_s\tislands\txor_nodes\tbve_eliminated\n'
  for log in "$OUT"/logs/*.log; do
    file=$(basename "$log" .log)
    config=${file##*__}
    model=${file%__*}
    status=$(sed -n 's/^PROBE_STATUS=//p' "$log" | tail -1)
    result=$(sed -n 's/^result: //p' "$log" | tail -1)
    wall=$(sed -n 's/.*PROBE_WALL=\([^ ]*\).*/\1/p' "$log" | tail -1)
    affine=$(grep 'c PDR_AFFINE ' "$log" | tail -1 || true)
    islands=$(sed -n 's/.* island_count=\([0-9]*\).*/\1/p' <<<"$affine")
    xor_nodes=$(sed -n 's/.* island_xor_nodes=\([0-9]*\).*/\1/p' <<<"$affine")
    eliminated=$(sed -n 's/.* cmsat_boundary_bve_eliminated=\([0-9]*\).*/\1/p' <<<"$affine")
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$model" "$config" "$status" "$result" "$wall" \
      "$islands" "$xor_nodes" "$eliminated"
  done
} >"$OUT/summary.tsv"

column -t -s $'\t' "$OUT/summary.tsv" 2>/dev/null || cat "$OUT/summary.tsv"
