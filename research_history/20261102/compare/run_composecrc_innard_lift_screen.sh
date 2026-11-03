#!/usr/bin/env bash
set -u

root=/home/wudl
binary="$root/Modelchecker-bidirectional/modelchecker/modelchecker"
out="$root/test_tools/compare/results/composecrc_innard_lift_screen_v1"
mkdir -p "$out"

run_one() {
  local label="$1"
  local model="$2"
  local lift="$3"
  local limit="$4"
  local log="$out/$label.log"

  timeout "${limit}s" env \
    MC_PDR_SOLVER=cmsat \
    MC_PDR_CMSAT_GAUSS=1 \
    MC_PDR_INNARD_PROBE=1 \
    MC_PDR_INNARD_LIFT="$lift" \
    MC_PDR_STATS=1 \
    MC_PDR_PROGRESS_SECONDS=30 \
    MC_PDR_SEED=230901 \
    "$binary" -xag "$model" > "$log" 2>&1
  echo "$?" > "$out/$label.status"
}

p03="$root/test_tools/hwmcc2019/data/zipversa_composecrc_prf-p03.aig"
p10="$root/test_tools/hwmcc2020/data/2019/wolf/2019C/zipversa_composecrc_prf-p10.aig"

run_one p03-base "$p03" 0 180 &
pid_p03_base=$!
run_one p03-lift "$p03" 1 180 &
pid_p03_lift=$!
run_one p10-base "$p10" 0 180 &
pid_p10_base=$!
run_one p10-lift "$p10" 1 180 &
pid_p10_lift=$!

wait "$pid_p03_base"
wait "$pid_p03_lift"
wait "$pid_p10_base"
wait "$pid_p10_lift"
