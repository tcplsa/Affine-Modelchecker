#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
args=(
  --host "${MC_COMPARE_HOST:-0.0.0.0}"
  --port "${MC_COMPARE_PORT:-8765}"
)
if [[ -n "${MC_COMPARE_PID_FILE:-}" ]]; then
  args+=(--pid-file "$MC_COMPARE_PID_FILE")
fi
exec python3 "$SCRIPT_DIR/compare_ui/server.py" "${args[@]}" "$@"
