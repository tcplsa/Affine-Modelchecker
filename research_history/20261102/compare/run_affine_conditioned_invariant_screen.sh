#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
MC="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker"
OUTPUT="${AFFINE_CONDITIONED_INVARIANT_OUTPUT:-$TOOLS/results/pathb_affine_conditioned_invariant_v1}"
LIMIT="${AFFINE_CONDITIONED_INVARIANT_LIMIT:-60}"

mkdir -p "$OUTPUT/logs"
SUMMARY="$OUTPUT/summary.tsv"
printf 'model\tstatus\tresult\twall_s\trank\treachable_modes\tinvariants\tselected\tproved\n' > "$SUMMARY"

while IFS= read -r model; do
    stem=$(basename "$model" .aag)
    log="$OUTPUT/logs/$stem.log"
    started=$(date +%s.%N)
    set +e
    timeout "$LIMIT" env \
        MC_PDR_SOLVER=cmsat \
        MC_PDR_CMSAT_GAUSS=1 \
        MC_PDR_GUARDED_AFFINE=1 \
        MC_PDR_GUARDED_AFFINE_MAX_CONTROLS=2 \
        MC_PDR_GUARDED_AFFINE_VALIDATE=1 \
        MC_PDR_AFFINE_INVARIANTS=1 \
        MC_PDR_AFFINE_INVARIANT_DIRECT_CHECK=1 \
        MC_PDR_STATS=1 \
        "$MC" -xag "$model" > "$log" 2>&1
    status=$?
    set -e
    ended=$(date +%s.%N)
    wall=$(awk -v start="$started" -v end="$ended" 'BEGIN { printf "%.3f", end - start }')
    result=$(rg -o 'result: (safe|unsafe|unknown)' "$log" | tail -1 | cut -d' ' -f2 || true)
    affine=$(rg 'c PDR_AFFINE ' "$log" | tail -1 || true)
    rank=$(sed -n 's/.*invariant_reachable_rank=\([0-9]*\).*/\1/p' <<<"$affine")
    modes=$(sed -n 's/.*invariant_reachable_modes=\([0-9]*\).*/\1/p' <<<"$affine")
    invariants=$(sed -n 's/.*invariant_count=\([0-9]*\).*/\1/p' <<<"$affine")
    selected=$(sed -n 's/.*invariant_selected=\([0-9]*\).*/\1/p' <<<"$affine")
    proved=$(sed -n 's/.*invariant_proves_target=\([01]\).*/\1/p' <<<"$affine")
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$stem" "$status" "${result:-timeout}" "$wall" "${rank:-0}" \
        "${modes:-0}" "${invariants:-0}" "${selected:-0}" \
        "${proved:-0}" >> "$SUMMARY"
done < <(find \
    "$TOOLS/results/pathb_affine_phase_sync_v1/benchmarks" \
    "$TOOLS/results/pathb_affine_phase_sync_frontier_v1/benchmarks" \
    -maxdepth 1 -type f -name '*.aag' | sort)

python3 - "$SUMMARY" <<'PY'
import csv
import sys

rows = list(csv.DictReader(open(sys.argv[1]), delimiter='\t'))
proved = [row for row in rows if row['proved'] == '1' and row['result'] == 'safe']
failed = [row for row in rows if row not in proved]
print(f'conditioned-invariant: {len(proved)}/{len(rows)} direct SAFE proofs')
print(f'non-proofs: {len(failed)}')
PY
