#!/usr/bin/env bash
set -euo pipefail

ROLE=${1:-}
ROOT=/home/wudl
TOOLS="$ROOT/test_tools/compare"
BINARY="$ROOT/Modelchecker-bidirectional/modelchecker/modelchecker-variable-order-v1"
DESIGN_ROOT="$TOOLS/results/variable_order_overnight_design_v1"
WORKERS=${VAR_ORDER_WORKERS:-30}
LANES=${VAR_ORDER_LANES:-4}
TIMEOUT=${VAR_ORDER_TIMEOUT:-300}

cleanup() {
    pkill -TERM -P $$ 2>/dev/null || true
    wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

python3 "$TOOLS/build_variable_order_overnight.py"

case "$ROLE" in
server-a)
    MANIFEST="$TOOLS/results/initial_cnf_final_holdout_design_v1/manifest.json"
    OUTPUT="$TOOLS/results/variable_order_overnight_server-a_v1/results.tsv"
    CONFIGS=xag_canonical-cnf
    ORDERS=first,occurrence-reverse,numeric,state-first,state-last,root-first,leaf-first,bad-first,next-first,shared-first,xor-first,xor-last,constraint-first
    RUNS=1,2,3
    SEED_BASE=110000
    ;;
server-b)
    MANIFEST="$DESIGN_ROOT/manifest_server-b.json"
    OUTPUT="$TOOLS/results/variable_order_overnight_server-b_v1/results.tsv"
    CONFIGS=xag_canonical-cnf
    ORDERS=first,occurrence-reverse,numeric,state-first,state-last,root-first,leaf-first,bad-first,next-first,shared-first,xor-first,xor-last,constraint-first
    RUNS=1,2
    SEED_BASE=210000
    ;;
server-c)
    MANIFEST="$TOOLS/results/initial_cnf_final_holdout_design_v1/manifest.json"
    OUTPUT="$TOOLS/results/variable_order_overnight_server-c_v1/results.tsv"
    CONFIGS=aig_canonical-cnf,xag_canonical-cnf
    ORDERS=first,state-first,state-last,root-first,leaf-first,xor-first,xor-last
    RUNS=4,5,6
    SEED_BASE=310000
    ;;
*)
    echo "usage: $0 server-a|server-b|server-c" >&2
    exit 2
    ;;
esac

if [[ ! -x "$BINARY" ]]; then
    echo "missing executable snapshot: $BINARY" >&2
    exit 2
fi

mkdir -p "$(dirname "$OUTPUT")"
python3 "$TOOLS/run_variable_order_campaign.py" \
    --manifest "$MANIFEST" --binary "$BINARY" --output "$OUTPUT" \
    --configs "$CONFIGS" --orders "$ORDERS" --runs "$RUNS" \
    --workers "$WORKERS" --lanes "$LANES" --timeout "$TIMEOUT" \
    --seed-base "$SEED_BASE"

trap - INT TERM EXIT
