#!/usr/bin/env bash
set -u

probe_root=/home/wudl
probe_bin="$probe_root/Modelchecker-bidirectional/modelchecker/modelchecker"
probe_out="$probe_root/test_tools/compare/results/composecrc_innard_probe_v2"
mkdir -p "$probe_out"

run_probe() {
  local label="$1"
  local model="$2"
  local limit="$3"
  local log="$probe_out/$label.log"

  timeout "${limit}s" env \
    MC_PDR_SOLVER=cmsat \
    MC_PDR_CMSAT_GAUSS=1 \
    MC_PDR_INNARD_PROBE=1 \
    MC_PDR_STATS=1 \
    MC_PDR_PROGRESS_SECONDS=30 \
    MC_PDR_SEED=230901 \
    "$probe_bin" -xag "$model" > "$log" 2>&1
  echo "$?" > "$probe_out/$label.status"
}

run_probe \
  p06-control \
  "$probe_root/test_tools/hwmcc2019/data/zipversa_composecrc_prf-p06.aig" \
  60
run_probe \
  p03-hard \
  "$probe_root/test_tools/hwmcc2019/data/zipversa_composecrc_prf-p03.aig" \
  300
run_probe \
  p10-hard \
  "$probe_root/test_tools/hwmcc2020/data/2019/wolf/2019C/zipversa_composecrc_prf-p10.aig" \
  300

"$probe_root/test_tools/compare/analyze_composecrc_innard_probe.py" "$probe_out"
