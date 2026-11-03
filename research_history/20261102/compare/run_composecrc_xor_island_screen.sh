#!/usr/bin/env bash
set -u

root=/home/wudl
binary="$root/Modelchecker-bidirectional/modelchecker/modelchecker"
out="$root/test_tools/compare/results/composecrc_xor_island_screen_v2"
mkdir -p "$out"

models=(
  "$root/test_tools/hwmcc2020/data/2019/wolf/2019C/zipversa_composecrc_prf-p03.aig"
  "$root/test_tools/hwmcc2020/data/2019/wolf/2019C/zipversa_composecrc_prf-p10.aig"
)

run_case() {
  local model="$1"
  local mode="$2"
  local stem
  stem=$(basename "$model" .aig)
  local log="$out/${stem}.${mode}.log"
  local env_file="$out/${stem}.${mode}.env"

  {
    echo "model=$model"
    echo "mode=$mode"
    echo "limit_seconds=180"
    echo "seed=230901"
  } > "$env_file"

  case "$mode" in
    base)
      timeout 180s env MC_PDR_SOLVER=cmsat MC_PDR_CMSAT_GAUSS=1 \
        MC_PDR_STATS=1 MC_PDR_PROGRESS_SECONDS=30 MC_PDR_SEED=230901 \
        "$binary" -xag "$model" > "$log" 2>&1
      ;;
    summary)
      timeout 180s env MC_PDR_SOLVER=cmsat MC_PDR_CMSAT_GAUSS=1 \
        MC_PDR_AFFINE_ISLAND_SUMMARY=1 MC_PDR_AFFINE_ISLAND_MIN_XORS=4 \
        MC_PDR_AFFINE_ISLAND_VALIDATE=1 MC_PDR_STATS=1 \
        MC_PDR_PROGRESS_SECONDS=30 MC_PDR_SEED=230901 \
        "$binary" -xag "$model" > "$log" 2>&1
      ;;
    replace)
      timeout 180s env MC_PDR_SOLVER=cmsat MC_PDR_CMSAT_GAUSS=1 \
        MC_PDR_AFFINE_ISLAND_REPLACE=1 MC_PDR_AFFINE_ISLAND_MIN_XORS=4 \
        MC_PDR_AFFINE_ISLAND_VALIDATE=1 MC_PDR_STATS=1 \
        MC_PDR_PROGRESS_SECONDS=30 MC_PDR_SEED=230901 \
        "$binary" -xag "$model" > "$log" 2>&1
      ;;
    dag-replace)
      timeout 180s env MC_PDR_SOLVER=cmsat MC_PDR_CMSAT_GAUSS=1 \
        MC_PDR_AFFINE_ISLAND_REPLACE=1 MC_PDR_AFFINE_ISLAND_DAG=1 \
        MC_PDR_AFFINE_ISLAND_MIN_XORS=4 MC_PDR_AFFINE_ISLAND_VALIDATE=1 \
        MC_PDR_STATS=1 MC_PDR_PROGRESS_SECONDS=30 MC_PDR_SEED=230901 \
        "$binary" -xag "$model" > "$log" 2>&1
      ;;
  esac
  echo "$?" > "$out/${stem}.${mode}.status"
}

for model in "${models[@]}"; do
  for mode in base summary replace dag-replace; do
    run_case "$model" "$mode"
  done
done

"$root/test_tools/compare/analyze_composecrc_xor_island_screen.py" "$out"
