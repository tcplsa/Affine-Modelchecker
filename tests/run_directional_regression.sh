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

for representation in -aig -aig-compact -xag-lowered -xag -auto; do
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

constraint_symbol_output=$($MC -aig \
    "$ROOT/tests/fixtures/safe_constraint_symbol.aag" 2>&1)
if ! grep -q "result: safe" <<<"$constraint_symbol_output"; then
    echo "FAIL: AIGER constraint symbol was parsed as a comment marker"
    echo "$constraint_symbol_output"
    exit 1
fi
echo "PASS: AIGER constraint symbols are distinct from the comment marker"

for representation in -aig -aig-compact -xag-lowered -xag -auto; do
    run_case safe_reset_function.aag safe forward "$representation"
    run_case unsafe_reset_function.aag unsafe forward "$representation"
done
reset_fallback_output=$($MC --reverse-aig 1 --reverse-xag 1 \
    "$ROOT/tests/fixtures/safe_reset_function.aag" 2>&1)
if ! grep -q "converting reverse PDR lanes" <<<"$reset_fallback_output" ||
   ! grep -q "result: safe" <<<"$reset_fallback_output"; then
    echo "FAIL: reset-function reverse lanes did not fall back to forward PDR"
    echo "$reset_fallback_output"
    exit 1
fi
echo "PASS: AIGER 1.9 reset functions preserve semantics across forward representations"

reset_perturb_output=$(MC_PDR_PERTURB=latch,gate-run \
    MC_PDR_PERTURB_SEED=29 "$MC" -xag \
    "$ROOT/tests/fixtures/safe_reset_function.aag" 2>&1)
if ! grep -q "result: safe" <<<"$reset_perturb_output"; then
    echo "FAIL: reset-function literals were not preserved by variable perturbation"
    echo "$reset_perturb_output"
    exit 1
fi
echo "PASS: variable perturbation remaps AIGER 1.9 reset functions"

for representation in -aig -aig-compact -xag-lowered -xag -auto; do
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
      -auto)
        expected="mode=aig .*recognized_xors=0 .*structural_gate_vars=3 structural_gate_clauses=9"
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

xor_island_output=$(MC_PDR_SOLVER=cmsat MC_PDR_CMSAT_GAUSS=1 \
    MC_PDR_AFFINE_ISLAND_REPLACE=1 MC_PDR_AFFINE_ISLAND_MIN_XORS=2 \
    MC_PDR_AFFINE_ISLAND_VALIDATE=1 MC_PDR_STATS=1 \
    "$MC" -xag "$ROOT/tests/fixtures/unsafe_xor_chain_two.aag" 2>&1)
if ! grep -q "result: unsafe" <<<"$xor_island_output" ||
   ! grep -q "recognized_xors=2" <<<"$xor_island_output" ||
   ! grep -q "island_enabled=1 island_replace=1 .*island_count=1 .*island_replaced_gates=" \
       <<<"$xor_island_output" ||
   ! grep -q "island_validation_attempted=1 island_validation_passed=1" \
       <<<"$xor_island_output"; then
    echo "FAIL: private XOR-island replacement or validation changed semantics"
    echo "$xor_island_output"
    exit 1
fi
echo "PASS: private XOR islands are replaced and SAT-validated without changing semantics"

xor_dag_tree_output=$(MC_PDR_SOLVER=cmsat MC_PDR_CMSAT_GAUSS=1 \
    MC_PDR_AFFINE_ISLAND_REPLACE=1 MC_PDR_AFFINE_ISLAND_MIN_XORS=2 \
    MC_PDR_AFFINE_ISLAND_VALIDATE=1 MC_PDR_STATS=1 \
    "$MC" -xag "$ROOT/tests/fixtures/unsafe_xor_shared_dag.aag" 2>&1)
xor_dag_output=$(MC_PDR_SOLVER=cmsat MC_PDR_CMSAT_GAUSS=1 \
    MC_PDR_AFFINE_ISLAND_REPLACE=1 MC_PDR_AFFINE_ISLAND_DAG=1 \
    MC_PDR_AFFINE_ISLAND_MIN_XORS=2 MC_PDR_AFFINE_ISLAND_VALIDATE=1 \
    MC_PDR_STATS=1 \
    "$MC" -xag "$ROOT/tests/fixtures/unsafe_xor_shared_dag.aag" 2>&1)
if ! grep -q "result: unsafe" <<<"$xor_dag_tree_output" ||
   ! grep -q "island_xor_nodes=5" <<<"$xor_dag_tree_output" ||
   ! grep -q "result: unsafe" <<<"$xor_dag_output" ||
   ! grep -q "island_dag=1 .*island_xor_nodes=6" <<<"$xor_dag_output" ||
   ! grep -q "island_validation_attempted=1 island_validation_passed=1" \
       <<<"$xor_dag_output"; then
    echo "FAIL: reconvergent XOR DAG replacement did not expand its private shared node"
    echo "$xor_dag_tree_output"
    echo "$xor_dag_output"
    exit 1
fi
echo "PASS: private reconvergent XOR DAGs are collapsed beyond the tree boundary"

cmsat_bve_output=$(MC_PDR_SOLVER=cmsat MC_PDR_CMSAT_GAUSS=1 \
    MC_PDR_CMSAT_BOUNDARY_BVE=1 MC_PDR_STATS=1 \
    "$MC" -xag "$ROOT/tests/fixtures/safe_three_latches.aag" 2>&1)
if ! grep -q "result: safe" <<<"$cmsat_bve_output" ||
   ! grep -Eq "cmsat_boundary_bve_runs=[1-9][0-9]*" <<<"$cmsat_bve_output" ||
   ! grep -Eq "cmsat_boundary_bve_eliminated=[1-9][0-9]*" <<<"$cmsat_bve_output"; then
    echo "FAIL: boundary-frozen CMSat BVE did not simplify a private CNF cone"
    echo "$cmsat_bve_output"
    exit 1
fi
echo "PASS: boundary-frozen CMSat BVE eliminates private CNF auxiliaries"

affine_invariant_output=$(MC_PDR_SOLVER=cmsat MC_PDR_CMSAT_GAUSS=1 \
    MC_PDR_AFFINE_INVARIANTS=1 MC_PDR_AFFINE_INVARIANT_DIRECT_CHECK=1 \
    MC_PDR_STATS=1 "$MC" -xag \
    "$ROOT/tests/fixtures/safe_affine_common_invariant.aag" 2>&1)
if ! grep -q "result: safe" <<<"$affine_invariant_output" ||
   ! grep -Eq "invariant_reachable_rank=1 invariant_count=1 .*invariant_selected=1" \
       <<<"$affine_invariant_output" ||
   ! grep -q "invariant_proves_target=1" <<<"$affine_invariant_output" ||
   ! grep -q "c PDR_AFFINE_INVARIANT status=proved" \
       <<<"$affine_invariant_output"; then
    echo "FAIL: affine reachable-hull analysis did not recover the common parity invariant"
    echo "$affine_invariant_output"
    exit 1
fi
echo "PASS: affine reachable-hull analysis recovers and proves a parity invariant"

auto_aig_output=$(MC_PDR_STATS=1 "$MC" -auto \
    "$ROOT/tests/fixtures/unsafe_xor_one_step.aag" 2>&1)
auto_xag_output=$(MC_PDR_STATS=1 MC_PDR_AUTO_MIN_NEXT_DEPTH=0 \
    MC_PDR_AUTO_MIN_AND_REDUCTION=0 "$MC" -auto \
    "$ROOT/tests/fixtures/unsafe_xor_one_step.aag" 2>&1)
if ! grep -q "c PDR_SELECTOR auto_choice=aig" <<<"$auto_aig_output" ||
   ! grep -q "c PDR_SELECTOR auto_choice=xag" <<<"$auto_xag_output" ||
   ! grep -q "c PDR_REPRESENTATION mode=xag" <<<"$auto_xag_output"; then
    echo "FAIL: static AIG/XAG selector did not honor its thresholds"
    echo "$auto_aig_output"
    echo "$auto_xag_output"
    exit 1
fi
echo "PASS: static AIG/XAG selector chooses and reports both representations"

for policy in all next deep; do
    selective_output=$(MC_PDR_XAG_POLICY="$policy" MC_PDR_STATS=1 \
        "$MC" -xag "$ROOT/tests/fixtures/unsafe_xor_one_step.aag" 2>&1)
    if ! grep -q "candidate_xors=1 recognized_xors=1 .*xag_policy=$policy" \
        <<<"$selective_output" || ! grep -q "result: unsafe" <<<"$selective_output"; then
        echo "FAIL: selective XAG policy $policy did not select the next-cone XOR"
        echo "$selective_output"
        exit 1
    fi
done
for policy in bad shared; do
    selective_output=$(MC_PDR_XAG_POLICY="$policy" MC_PDR_STATS=1 \
        "$MC" -xag "$ROOT/tests/fixtures/unsafe_xor_one_step.aag" 2>&1)
    if ! grep -q "candidate_xors=1 recognized_xors=0 .*xag_policy=$policy" \
        <<<"$selective_output" || ! grep -q "result: unsafe" <<<"$selective_output"; then
        echo "FAIL: selective XAG policy $policy did not preserve the AIG XOR structure"
        echo "$selective_output"
        exit 1
    fi
done
echo "PASS: selective XAG policies choose the expected XOR subsets"

for preprocessor in minisat cadical; do
    preprocessor_output=$(MC_PDR_PREPROCESSOR="$preprocessor" \
        MC_PDR_STATS=1 "$MC" -xag \
        "$ROOT/tests/fixtures/safe_three_latches.aag" 2>&1)
    if ! grep -q "c PDR_CONFIG .*preprocessor=$preprocessor" \
        <<<"$preprocessor_output" ||
       ! grep -q "result: safe" <<<"$preprocessor_output"; then
        echo "FAIL: CNF preprocessor '$preprocessor' changed semantics or was not selected"
        echo "$preprocessor_output"
        exit 1
    fi
done
echo "PASS: interchangeable CNF preprocessors preserve semantics"

for elim_order in legacy low high sum-low sum-high; do
    elim_order_output=$(MC_PDR_MINISAT_ELIM_ORDER="$elim_order" \
        MC_PDR_STATS=1 "$MC" -xag \
        "$ROOT/tests/fixtures/safe_three_latches.aag" 2>&1)
    if ! grep -q "c PDR_CONFIG .*minisat_elim_order=$elim_order" \
        <<<"$elim_order_output" ||
       ! grep -q "result: safe" <<<"$elim_order_output"; then
        echo "FAIL: MiniSat elimination order '$elim_order' changed semantics"
        echo "$elim_order_output"
        exit 1
    fi
done
echo "PASS: deterministic MiniSat elimination orders preserve semantics"

for policy in next-low-fanout cone-low-fanout; do
    selective_output=$(MC_PDR_XAG_POLICY="$policy" \
        MC_PDR_XAG_MIN_FANOUT=2 MC_PDR_STATS=1 \
        "$MC" -xag "$ROOT/tests/fixtures/unsafe_xor_one_step.aag" 2>&1)
    if ! grep -q "candidate_xors=1 recognized_xors=1 .*xag_policy=$policy .*xag_min_fanout=2" \
        <<<"$selective_output" || ! grep -q "result: unsafe" <<<"$selective_output"; then
        echo "FAIL: cone/fanout policy $policy did not select the low-fanout next XOR"
        echo "$selective_output"
        exit 1
    fi
done
for policy in bad-low-fanout shared-low-fanout; do
    selective_output=$(MC_PDR_XAG_POLICY="$policy" \
        MC_PDR_XAG_MIN_FANOUT=2 MC_PDR_STATS=1 \
        "$MC" -xag "$ROOT/tests/fixtures/unsafe_xor_one_step.aag" 2>&1)
    if ! grep -q "candidate_xors=1 recognized_xors=0 .*xag_policy=$policy .*xag_min_fanout=2" \
        <<<"$selective_output" || ! grep -q "result: unsafe" <<<"$selective_output"; then
        echo "FAIL: cone/fanout policy $policy did not preserve the out-of-cone XOR"
        echo "$selective_output"
        exit 1
    fi
done
echo "PASS: cone/fanout intersection policies choose the expected XOR subsets"

allowlist_file=$(mktemp)
trap 'rm -f "$allowlist_file"' EXIT
printf '5\n' > "$allowlist_file"
allowlist_output=$(MC_PDR_XAG_ALLOWLIST_FILE="$allowlist_file" MC_PDR_STATS=1 \
    "$MC" -xag "$ROOT/tests/fixtures/unsafe_xor_one_step.aag" 2>&1)
printf '99\n' > "$allowlist_file"
denylist_output=$(MC_PDR_XAG_ALLOWLIST_FILE="$allowlist_file" MC_PDR_STATS=1 \
    "$MC" -xag "$ROOT/tests/fixtures/unsafe_xor_one_step.aag" 2>&1)
if ! grep -q "candidate_xors=1 recognized_xors=1 .*xag_allowlist=1 xag_allowlist_size=1" \
    <<<"$allowlist_output" ||
   ! grep -q "candidate_xors=1 recognized_xors=0 .*xag_allowlist=1 xag_allowlist_size=1" \
    <<<"$denylist_output" ||
   ! grep -q "result: unsafe" <<<"$allowlist_output" ||
   ! grep -q "result: unsafe" <<<"$denylist_output"; then
    echo "FAIL: explicit XOR allowlist did not select the requested original variable"
    echo "$allowlist_output"
    echo "$denylist_output"
    exit 1
fi
echo "PASS: explicit XOR allowlists preserve semantics and select stable gate IDs"

sample_none_output=$(MC_PDR_XAG_POLICY=sample MC_PDR_XAG_FRACTION=0 \
    MC_PDR_XAG_SEED=17 MC_PDR_STATS=1 "$MC" -xag \
    "$ROOT/tests/fixtures/unsafe_xor_one_step.aag" 2>&1)
sample_all_output=$(MC_PDR_XAG_POLICY=sample MC_PDR_XAG_FRACTION=1 \
    MC_PDR_XAG_SEED=17 MC_PDR_STATS=1 "$MC" -xag \
    "$ROOT/tests/fixtures/unsafe_xor_one_step.aag" 2>&1)
if ! grep -q "candidate_xors=1 recognized_xors=0 .*xag_policy=sample xag_fraction=0.000000 xag_seed=17" \
    <<<"$sample_none_output" ||
   ! grep -q "candidate_xors=1 recognized_xors=1 .*xag_policy=sample xag_fraction=1.000000 xag_seed=17" \
    <<<"$sample_all_output" ||
   ! grep -q "result: unsafe" <<<"$sample_none_output" ||
   ! grep -q "result: unsafe" <<<"$sample_all_output"; then
    echo "FAIL: sampled hybrid XAG did not honor fraction endpoints"
    echo "$sample_none_output"
    echo "$sample_all_output"
    exit 1
fi
echo "PASS: sampled hybrid XAG preserves semantics at fraction endpoints"

input_order_output=$(MC_PDR_INPUT_ORDER=fanout-asc MC_PDR_STATS=1 \
    "$MC" -aig "$ROOT/tests/fixtures/unsafe_two_inputs.aag" 2>&1)
if ! grep -q "c INPUT_SCORE_ASC .*map=1->2,2->1" <<<"$input_order_output" ||
   ! grep -q "c PDR_PERTURB modes=input-fanout-rev" <<<"$input_order_output" ||
   ! grep -q "result: unsafe" <<<"$input_order_output"; then
    echo "FAIL: deterministic input ordering did not preserve the counterexample"
    echo "$input_order_output"
    exit 1
fi
echo "PASS: deterministic input ordering preserves transition-system semantics"

for variable_order in first occurrence-reverse numeric state-first state-last \
    root-first leaf-first bad-first next-first shared-first xor-first xor-last \
    constraint-first; do
    variable_order_output=$(MC_PDR_CANONICAL_CNF=1 \
        MC_PDR_CADICAL_VAR_ORDER="$variable_order" MC_PDR_PHASE_STATS=1 \
        "$MC" -xag "$ROOT/tests/fixtures/unsafe_xor_one_step.aag" 2>&1)
    if ! grep -q "c PDR_VAR_ORDER .*mode=$variable_order" <<<"$variable_order_output" ||
       ! grep -q "result: unsafe" <<<"$variable_order_output"; then
        echo "FAIL: CaDiCaL variable order '$variable_order' changed semantics"
        echo "$variable_order_output"
        exit 1
    fi
done
echo "PASS: deterministic CaDiCaL variable orders preserve semantics"

phase_order_output=$(MC_PDR_CANONICAL_CNF=1 \
    MC_PDR_CADICAL_VAR_ORDER=first \
    MC_PDR_CADICAL_ORDER_TRANSLATION=numeric \
    MC_PDR_CADICAL_ORDER_LIFT=state-last \
    MC_PDR_PHASE_STATS=1 "$MC" -xag \
    "$ROOT/tests/fixtures/unsafe_xor_one_step.aag" 2>&1)
if ! grep -q "c PDR_VAR_ORDER .*phase=translation mode=numeric" <<<"$phase_order_output" ||
   ! grep -q "c PDR_VAR_ORDER .*phase=lift mode=state-last" <<<"$phase_order_output" ||
   ! grep -q "result: unsafe" <<<"$phase_order_output"; then
    echo "FAIL: phase-specific CaDiCaL variable orders were not applied"
    echo "$phase_order_output"
    exit 1
fi
echo "PASS: translation and lift CaDiCaL orders can be controlled independently"

perturb_output=$(MC_PDR_PERTURB=input,latch,gate-run MC_PDR_PERTURB_SEED=23 \
    MC_PDR_STATS=1 "$MC" -xag "$ROOT/tests/fixtures/safe_three_latches.aag" 2>&1)
if ! grep -q "c PDR_PERTURB modes=input,latch,gate-run seed=23" <<<"$perturb_output" ||
   ! grep -q "perturb_modes=input,latch,gate-run perturb_seed=23" <<<"$perturb_output" ||
   ! grep -q "result: safe" <<<"$perturb_output"; then
    echo "FAIL: combined variable perturbations changed transition-system semantics"
    echo "$perturb_output"
    exit 1
fi
echo "PASS: combined variable perturbations preserve transition-system semantics"

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

invariant_export_file=$(mktemp)
invariant_prune_file=$(mktemp)
invariant_snapshot_file=$(mktemp)
trap 'rm -f "$allowlist_file" "$invariant_export_file" "$invariant_prune_file" "$invariant_snapshot_file"' EXIT
invariant_export_output=$(MC_PDR_INVARIANT_EXPORT="$invariant_export_file" \
    MC_PDR_STATS=1 "$MC" -aig \
    "$ROOT/tests/fixtures/safe_self_inductive.aag" 2>&1)
invariant_import_output=$(MC_PDR_INVARIANT_IMPORT="$invariant_export_file" \
    MC_PDR_INVARIANT_SNAPSHOT="$invariant_snapshot_file" \
    MC_PDR_PROGRESS_SECONDS=1 \
    MC_PDR_STATS=1 "$MC" -aig \
    "$ROOT/tests/fixtures/safe_self_inductive.aag" 2>&1)
invariant_same_transition_output=$( \
    MC_PDR_INVARIANT_IMPORT="$invariant_export_file" \
    MC_PDR_INVARIANT_SAME_TRANSITION=1 MC_PDR_STATS=1 "$MC" -aig \
    "$ROOT/tests/fixtures/safe_self_inductive.aag" 2>&1)
if ! grep -q "c PDR_INVARIANT_EXPORT clauses=2" <<<"$invariant_export_output" ||
   ! grep -q "c PDR_INVARIANT_IMPORT status=accepted clauses=2 pruned=0 proves_target=1" \
       <<<"$invariant_import_output" ||
   ! grep -q "c PDR_INVARIANT_SNAPSHOT clauses=2" \
       <<<"$invariant_import_output" ||
   ! grep -q "result: safe" <<<"$invariant_import_output" ||
   ! grep -q "validation=same-transition clauses=2" \
       <<<"$invariant_same_transition_output" ||
   ! grep -q "status=accepted clauses=2 pruned=0 proves_target=1" \
       <<<"$invariant_same_transition_output" ||
   ! grep -q "result: safe" <<<"$invariant_same_transition_output"; then
    echo "FAIL: fixed-point invariant export/import did not close the validation loop"
    echo "$invariant_export_output"
    echo "$invariant_import_output"
    echo "$invariant_same_transition_output"
    exit 1
fi
echo "PASS: canonical latch invariants survive export and validated re-import"

printf 'mc-pdr-invariant-v1 2\n1 0\n2 0\n-1 0\n' > "$invariant_prune_file"
invariant_reject_output=$(MC_PDR_INVARIANT_IMPORT="$invariant_prune_file" \
    MC_PDR_STATS=1 "$MC" -aig \
    "$ROOT/tests/fixtures/safe_self_inductive.aag" 2>&1)
invariant_prune_output=$(MC_PDR_INVARIANT_IMPORT="$invariant_prune_file" \
    MC_PDR_INVARIANT_PRUNE=1 MC_PDR_STATS=1 "$MC" -aig \
    "$ROOT/tests/fixtures/safe_self_inductive.aag" 2>&1)
if ! grep -q "status=reject reason=initial-or-map" <<<"$invariant_reject_output" ||
   ! grep -q "status=accepted clauses=2 pruned=1 proves_target=1" \
       <<<"$invariant_prune_output" ||
   ! grep -q "result: safe" <<<"$invariant_prune_output"; then
    echo "FAIL: external invariant validation/pruning did not reject the bad cube"
    echo "$invariant_reject_output"
    echo "$invariant_prune_output"
    exit 1
fi
echo "PASS: external invariant pruning removes invalid cubes before installation"
