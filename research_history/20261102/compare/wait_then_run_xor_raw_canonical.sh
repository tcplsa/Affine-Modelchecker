#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^(server-a|server-b)$ ]]; then
  echo "usage: $0 server-a|server-b" >&2
  exit 2
fi
SHARD="$1"
ROOT=/home/wudl
CURRENT="$ROOT/test_tools/compare/results/xor_canonical_mechanism_${SHARD}_v1/status.tsv"

while [[ ! -s "$CURRENT" ]]; do
  sleep 60
done

exec "$ROOT/test_tools/compare/run_xor_raw_canonical.sh" "$SHARD"
