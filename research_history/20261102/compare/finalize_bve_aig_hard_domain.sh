#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RESULT_DIR=${BVE_AIG_HARD_RESULT_DIR:-$SCRIPT_DIR/results/bve_aig_hard_domain_v1}

for tool in mc ric3; do
    inputs=("$RESULT_DIR"/${tool}_seed*_shard*_of_*.tsv)
    if [[ ! -e "${inputs[0]}" ]]; then
        echo "no $tool result files under $RESULT_DIR" >&2
        continue
    fi
    python3 "$SCRIPT_DIR/analyze_bve_aig_hard_domain.py" \
        --tool "$tool" --inputs "${inputs[@]}" \
        --output "$RESULT_DIR/${tool}_report.md"
done
