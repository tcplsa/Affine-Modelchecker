# Best-Origin Replay Interpretation

## Validity

- 41,742 replay rows completed successfully.
- All 3,785 frame traces and 123 lift traces reproduce conflicts, decisions,
  propagations, restarts, SAT/UNSAT results, and mapping observations exactly
  under recorded replay.
- The clean comparison holds lift at first-occurrence order and changes only
  translation order: `first:first` versus `numeric:first`.

## Clean frame decomposition

| Representation | Metric | Internal mapping | Query-flow effect | Interaction | Total |
|---|---|---:|---:|---:|---:|
| AIG | queries | 0.00% | -21.55% | 0.00% | -21.55% |
| AIG | conflicts | -0.85% | +0.87% | +4.33% | +4.35% |
| AIG | replay time | -2.45% | -14.51% | +3.41% | -13.55% |
| XAG | queries | 0.00% | -6.67% | 0.00% | -6.67% |
| XAG | conflicts | -3.36% | -15.69% | +7.47% | -11.58% |
| XAG | replay time | -4.33% | -4.84% | +1.88% | -7.29% |

Negative values mean less work than `first:first`.

The direct frozen-workload effect is modest. The numeric translation order
changes SAT models/cores, which changes subsequent PDR obligations,
generalization, and propagation. The resulting query stream is the larger
effect. Interaction is substantial: on the numeric-origin stream, mapping the
same queries back to first occurrence reduces conflicts by 3.33% for AIG and
4.65% for XAG. Numeric is therefore not a uniformly better per-query mapping.

## Lift

Changing lift mapping has essentially zero conflict effect on a frozen lift
workload. The observed lift workload changes are inherited from the upstream
frame trajectory. Numeric lift should remain disabled.

## Random calibration

- AIG numeric has a 0.75% model-paired geometric conflict reduction. The eight
  random mappings range from -44.36% to +2.58%; numeric is not distinguished
  from random and has a lower median gain than every random seed.
- XAG numeric has a 9.90% model-paired geometric reduction, while random ranges
  from -6.95% to +15.07%. Numeric protects aggregate tail cost better than all
  eight random mappings, but its paired central tendency remains inside the
  random distribution.

This supports diversity and tail-risk interpretations, not a universal static
numeric-order optimization rule.

## Scope limitations

The mechanism set was selected from earlier XAG order sensitivity. It is not a
representative AIG subset: only seven AIG model/runs overlap the completed
four-lane phase, and numeric/first is 8.03% worse on that subset despite being
25.17% better in the full AIG penalized aggregate.

The trace experiment is single-lane for deterministic replay, while the main
performance phase uses four cooperative lanes. Single-lane trace outcomes are
also tail-sensitive: AIG gains two solves but is 6.30% slower on jointly solved
traces; XAG is 11.53% faster jointly but loses two solves. The replay explains
how an isolated trajectory changes, not the final four-lane portfolio speedup.

## Research consequence

The next mechanism instrumentation should tag each SAT query with PDR semantic
context: query kind, frame index, obligation/cube size, assumption count,
SAT/UNSAT result, failed-core size, and generalized-cube size. Comparing the
first trajectory divergence under first and numeric mappings can then connect
SAT model/core changes to fewer or harder downstream queries. Static circuit
features alone cannot identify that causal transition from the current data.
