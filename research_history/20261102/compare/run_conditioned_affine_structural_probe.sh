#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
MC="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker"
MANIFEST="$TOOLS/results/pathb_affine_full_scope_v1/manifest.json"
OUTPUT="${CONDITIONED_AFFINE_PROBE_OUTPUT:-$TOOLS/results/conditioned_affine_structural_probe_v1}"
LIMIT="${CONDITIONED_AFFINE_PROBE_LIMIT:-30}"
RESUME="${CONDITIONED_AFFINE_PROBE_RESUME:-0}"

mkdir -p "$OUTPUT/logs"
SUMMARY="$OUTPUT/summary.tsv"
if [[ "$RESUME" != 1 || ! -f "$SUMMARY" ]]; then
    printf 'family\tscope\tmodel\tstatus\twall_s\tguarded_controls\tguarded_next\tconditioned\treachable_modes\trank\tinvariants\tmax_support\n' > "$SUMMARY"
fi

while IFS=$'\t' read -r family scope model; do
    stem=$(basename "$model" .aag)
    prefix="$family"$'\t'"$scope"$'\t'"$stem"$'\t'
    if [[ "$RESUME" == 1 ]] && rg -Fq "$prefix" "$SUMMARY"; then
        continue
    fi
    log="$OUTPUT/logs/$stem.log"
    started=$(date +%s.%N)
    set +e
    timeout "$LIMIT" env \
        MC_PDR_SOLVER=cmsat \
        MC_PDR_GUARDED_AFFINE_MAX_CONTROLS=2 \
        MC_PDR_GUARDED_AFFINE_VALIDATE=1 \
        MC_PDR_AFFINE_INVARIANTS=1 \
        MC_PDR_PREPROCESS_ONLY=1 \
        MC_PDR_STATS=1 \
        "$MC" -xag "$model" > "$log" 2>&1
    status=$?
    set -e
    ended=$(date +%s.%N)
    wall=$(awk -v start="$started" -v end="$ended" 'BEGIN { printf "%.3f", end - start }')
    affine=$(rg 'c PDR_AFFINE ' "$log" | tail -1 || true)
    controls=$(sed -n 's/.*guarded_controls=\([0-9]*\).*/\1/p' <<<"$affine")
    guarded=$(sed -n 's/.*guarded_next_count=\([0-9]*\).*/\1/p' <<<"$affine")
    conditioned=$(sed -n 's/.*invariant_conditioned=\([01]\).*/\1/p' <<<"$affine")
    modes=$(sed -n 's/.*invariant_reachable_modes=\([0-9]*\).*/\1/p' <<<"$affine")
    rank=$(sed -n 's/.*invariant_reachable_rank=\([0-9]*\).*/\1/p' <<<"$affine")
    invariants=$(sed -n 's/.*invariant_count=\([0-9]*\).*/\1/p' <<<"$affine")
    max_support=$(sed -n 's/.*invariant_support_max=\([0-9]*\).*/\1/p' <<<"$affine")
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$family" "$scope" "$stem" "$status" "$wall" "${controls:-0}" \
        "${guarded:-0}" "${conditioned:-0}" "${modes:-0}" "${rank:-0}" \
        "${invariants:-0}" "${max_support:-0}" >> "$SUMMARY"
done < <(python3 - "$MANIFEST" <<'PY'
import json
import sys
from collections import defaultdict

models = json.load(open(sys.argv[1]))['models']
groups = defaultdict(list)
for model in models:
    groups[(model['family'], model['scope'])].append(model['path'])
for (family, scope), paths in sorted(groups.items()):
    paths.sort()
    indexes = sorted({len(paths) // 3, (2 * len(paths)) // 3})
    for index in indexes:
        print(f'{family}\t{scope}\t{paths[index]}')
PY
)

python3 - "$SUMMARY" <<'PY'
import csv
import sys
from collections import defaultdict

rows = list(csv.DictReader(open(sys.argv[1]), delimiter='\t'))
stats = defaultdict(lambda: [0, 0, 0])
for row in rows:
    key = f"{row['scope']}:{row['family']}"
    stats[key][0] += 1
    stats[key][1] += row['conditioned'] == '1'
    stats[key][2] += int(row['invariants']) > 0
for key, (total, conditioned, nonempty) in sorted(stats.items()):
    print(f'{key}: conditioned={conditioned}/{total}, nonempty={nonempty}/{total}')
PY
