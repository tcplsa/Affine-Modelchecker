#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RESULT_DIR=${BVE_FULL_OUTPUT_DIR:-$SCRIPT_DIR/results/bve_full_campaign_v1}
SHARDS=${BVE_FULL_SHARDS:-3}
EXPECTED_PER_SHARD=${BVE_FULL_EXPECTED_PER_SHARD:-660}

for tool in mc ric3; do
    inputs=()
    for ((shard = 0; shard < SHARDS; shard++)); do
        path="$RESULT_DIR/${tool}_shard_${shard}_of_${SHARDS}.tsv"
        [[ -f "$path" ]] || { echo "missing $path" >&2; exit 1; }
        rows=$(( $(wc -l < "$path") - 1 ))
        if (( rows != EXPECTED_PER_SHARD )); then
            echo "incomplete $path: $rows/$EXPECTED_PER_SHARD" >&2
            exit 1
        fi
        inputs+=("$path")
    done
    python3 "$SCRIPT_DIR/analyze_bve_full_campaign.py" \
        --inputs "${inputs[@]}" \
        --output "$RESULT_DIR/${tool}_full_report.md"
done

mc_inputs=()
ric3_inputs=()
for ((shard = 0; shard < SHARDS; shard++)); do
    mc_inputs+=("$RESULT_DIR/mc_shard_${shard}_of_${SHARDS}.tsv")
    ric3_inputs+=("$RESULT_DIR/ric3_shard_${shard}_of_${SHARDS}.tsv")
done
python3 "$SCRIPT_DIR/analyze_mc_vs_ric3_full.py" \
    --mc "${mc_inputs[@]}" \
    --ric3 "${ric3_inputs[@]}" \
    --output "$RESULT_DIR/mc_vs_ric3_full_report.md"

echo "final reports:"
echo "  $RESULT_DIR/mc_full_report.md"
echo "  $RESULT_DIR/ric3_full_report.md"
echo "  $RESULT_DIR/mc_vs_ric3_full_report.md"
