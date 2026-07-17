#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MC="$ROOT/modelchecker"

run_case() {
    local fixture=$1
    local expected=$2
    local engine=$3
    local representation=$4
    local output

    if [[ $engine == bidirectional ]]; then
        output=$($MC --forward-aig 1 --forward-xag 1 --reverse-aig 1 --reverse-xag 1 \
            "$ROOT/tests/fixtures/$fixture" 2>&1)
    else
        output=$($MC "$representation" -engine "$engine" "$ROOT/tests/fixtures/$fixture" 2>&1)
    fi
    if ! grep -q "result: $expected" <<<"$output"; then
        echo "FAIL: $fixture repr=$representation engine=$engine expected=$expected"
        echo "$output"
        return 1
    fi
    echo "PASS: $fixture repr=$representation engine=$engine result=$expected"
}

for representation in -aig -aig-compact -xag-lowered -xag; do
  for engine in forward reverse bidirectional; do
    run_case unsafe_at_init.aag unsafe "$engine" "$representation"
    run_case unsafe_one_step.aag unsafe "$engine" "$representation"
    run_case unsafe_distinct_bad_transition_inputs.aag unsafe "$engine" "$representation"
    run_case unsafe_three_steps.aag unsafe "$engine" "$representation"
    run_case unsafe_cycle_meeting.aag unsafe "$engine" "$representation"
    run_case safe_input_bad.aag safe "$engine" "$representation"
    run_case safe_three_latches.aag safe "$engine" "$representation"
    run_case safe_self_inductive.aag safe "$engine" "$representation"
    run_case unsafe_xor_one_step.aag unsafe "$engine" "$representation"
  done
done

for representation in -aig -aig-compact -xag-lowered -xag; do
    xor_output=$(MC_PDR_STATS=1 "$MC" "$representation" \
        "$ROOT/tests/fixtures/unsafe_xor_one_step.aag" 2>&1)
    case "$representation" in
      -xag)
        expected="mode=xag .*recognized_xors=1 .*structural_gate_vars=1 structural_gate_clauses=4"
        ;;
      -xag-lowered)
        expected="mode=xag-lowered .*recognized_xors=1 .*structural_gate_vars=3 structural_gate_clauses=9"
        ;;
      -aig-compact)
        expected="mode=aig-compact .*recognized_xors=0 .*structural_gate_vars=3 structural_gate_clauses=9"
        ;;
      *)
        expected="mode=aig .*recognized_xors=0 .*structural_gate_vars=3 structural_gate_clauses=9"
        ;;
    esac
    if ! grep -Eq "c PDR_REPRESENTATION $expected" <<<"$xor_output"; then
        echo "FAIL: $representation did not produce the expected XOR ablation structure"
        echo "$xor_output"
        exit 1
    fi
done
echo "PASS: XOR ablation modes produce distinct expected CNF structures"

meeting_output=$(MC_PDR_STATS=1 MC_BIDIR_MEET_INTERVAL=1 MC_BIDIR_BRIDGE_BUDGET=32 \
    "$MC" --forward-aig 1 --reverse-xag 1 \
    "$ROOT/tests/fixtures/unsafe_cycle_meeting.aag" 2>&1)
if ! grep -q "c BIDIR_MEET result=unsafe bridge_queries=.*prefix_frames=" <<<"$meeting_output"; then
    echo "FAIL: cooperative middle meeting was not exercised"
    echo "$meeting_output"
    exit 1
fi
echo "PASS: cooperative middle meeting produced a joined counterexample"

sharing_output=$(MC_PDR_SEED=1 MC_PDR_STATS=1 MC_PDR_SHARE=1 \
    MC_BIDIR_BRIDGE_BUDGET=0 "$MC" --forward-aig 4 --forward-xag 4 \
    "$ROOT/tests/fixtures/safe_self_inductive.aag" 2>&1)
if ! grep -q "result: safe" <<<"$sharing_output" ||
   ! grep -Eq "c BIDIR_MEET .*shared_published=[1-9][0-9]*" <<<"$sharing_output" ||
   ! grep -Eq "c PDR_SHARE .*certified=[1-9][0-9]*" <<<"$sharing_output" ||
   grep -Eq "c PDR_SHARE .*rejected=[1-9][0-9]*" <<<"$sharing_output"; then
    echo "FAIL: mixed AIG/XAG inductive lemma exchange was not exercised"
    echo "$sharing_output"
    exit 1
fi
echo "PASS: mixed AIG/XAG lanes certified and published permanent inductive lemmas"

fallback_output=$(MC_PDR_STATS=1 "$MC" --forward-aig 0 --forward-xag 0 \
    --reverse-aig 0 --reverse-xag 0 "$ROOT/tests/fixtures/safe_three_latches.aag" 2>&1)
if ! grep -q "result: safe" <<<"$fallback_output" ||
   ! grep -q "c PDR_STATS thread=-1 direction=forward" <<<"$fallback_output" ||
   grep -q "c BIDIR_MEET" <<<"$fallback_output"; then
    echo "FAIL: zero lane counts did not fall back to single forward PDR"
    echo "$fallback_output"
    exit 1
fi
echo "PASS: zero lane counts fall back to single forward PDR"

count_output=$(MC_PDR_STATS=1 MC_BIDIR_BRIDGE_BUDGET=0 \
    "$MC" --forward-aig 2 --reverse-xag 1 \
    "$ROOT/tests/fixtures/unsafe_twenty_steps.aag" 2>&1)
if ! grep -q "result: unsafe" <<<"$count_output" ||
   ! grep -q "c BIDIR_MEET .*parallel=3" <<<"$count_output"; then
    echo "FAIL: custom lane counts were not honored"
    echo "$count_output"
    exit 1
fi
echo "PASS: custom lane counts start the requested number of workers"

single_seed_output=$(MC_PDR_STATS=1 "$MC" "$ROOT/tests/fixtures/safe_three_latches.aag" 2>&1)
if ! grep -q "c PDR_CONFIG .*seed=1 seed_mode=fixed" <<<"$single_seed_output"; then
    echo "FAIL: single PDR did not use the fixed default seed"
    echo "$single_seed_output"
    exit 1
fi
echo "PASS: single PDR uses a fixed seed"

explicit_single_seed_output=$(MC_PDR_STATS=1 "$MC" --reverse-aig 1 \
    "$ROOT/tests/fixtures/safe_three_latches.aag" 2>&1)
if ! grep -q "c PDR_CONFIG .*seed=1 seed_mode=fixed" <<<"$explicit_single_seed_output"; then
    echo "FAIL: an explicit single reverse lane did not use the fixed default seed"
    echo "$explicit_single_seed_output"
    exit 1
fi
echo "PASS: an explicit single reverse lane uses a fixed seed"

if ! grep -Eq "c PDR_REVERSE_LIFT attempted=[1-9][0-9]* succeeded=[1-9][0-9]* .*restarts=1 enabled=0" \
    <<<"$explicit_single_seed_output" || ! grep -q "result: safe" <<<"$explicit_single_seed_output"; then
    echo "FAIL: reverse lifting did not preserve the exact-witness fallback path"
    echo "$explicit_single_seed_output"
    exit 1
fi
echo "PASS: reverse lifting falls back to exact search after a spurious witness"

random_seed_output=$(MC_PDR_STATS=1 MC_BIDIR_BRIDGE_BUDGET=0 \
    "$MC" --forward-aig 2 "$ROOT/tests/fixtures/unsafe_twenty_steps.aag" 2>&1)
random_seed_count=$(sed -n 's/.*seed=\([0-9][0-9]*\) seed_mode=random.*/\1/p' <<<"$random_seed_output" | sort -u | wc -l)
if [[ $random_seed_count -lt 2 ]]; then
    echo "FAIL: parallel PDR lanes did not receive distinct random seeds"
    echo "$random_seed_output"
    exit 1
fi
echo "PASS: parallel PDR lanes use distinct random seeds"

fixed_seed_output=$(MC_PDR_STATS=1 MC_PDR_SEED=77 MC_BIDIR_BRIDGE_BUDGET=0 \
    "$MC" --forward-aig 2 "$ROOT/tests/fixtures/unsafe_twenty_steps.aag" 2>&1)
if ! grep -q "c PDR_CONFIG .*seed=77 seed_mode=fixed" <<<"$fixed_seed_output" ||
   ! grep -q "c PDR_CONFIG .*seed=79 seed_mode=fixed" <<<"$fixed_seed_output"; then
    echo "FAIL: MC_PDR_SEED did not restore deterministic parallel seeds"
    echo "$fixed_seed_output"
    exit 1
fi
echo "PASS: MC_PDR_SEED restores deterministic parallel seeds"
