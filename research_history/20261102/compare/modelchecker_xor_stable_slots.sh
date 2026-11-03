#!/usr/bin/env bash
set -euo pipefail

export MC_PDR_XAG_STABLE_SLOTS=1
exec /home/wudl/Modelchecker-bidirectional/modelchecker/modelchecker-xor-stable-causal "$@"
