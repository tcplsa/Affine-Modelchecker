#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/wudl
MC="$ROOT/Modelchecker-bidirectional/modelchecker"
SOURCE="$ROOT/test_tools/compare/sat_query_replay.cpp"
OUTPUT=${SAT_QUERY_REPLAY_OUTPUT:-"$ROOT/test_tools/compare/sat_query_replay"}

g++ -std=c++0x -O3 -g -I"$MC" "$SOURCE" -L"$MC" -lcadical -lpthread \
    -o "$OUTPUT.tmp"
mv "$OUTPUT.tmp" "$OUTPUT"
echo "$OUTPUT"
