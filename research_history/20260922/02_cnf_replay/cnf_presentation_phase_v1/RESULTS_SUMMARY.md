# CNF Presentation Phase v1 Results

## Scope

- 7,020 live PDR tasks over 195 holdout models.
- XAG: runs 1-6, four presentation cells per model/run.
- AIG: runs 4-6, four presentation cells per model/run.
- Each live task uses four PDR lanes and a 300 second timeout.
- Timeout scoring uses 450 seconds; cells where every treatment timed out are excluded.
- 90 mechanism-trace tasks and 11,384 SAT replay rows were collected.

## Live PDR result

The best cell is `numeric translation + first-occurrence lift` for both
representations, but its meaning differs sharply between AIG and XAG.

| Representation | Baseline first/first | Best numeric/first | Penalized reduction | Joint-solved reduction | Median speedup | Extra solves |
|---|---:|---:|---:|---:|---:|---:|
| AIG | 11,398.13 s | 8,642.25 s | 25.17% | 8.12% | 1.69% | 6 |
| XAG | 21,021.12 s | 20,430.29 s | 3.07% | -2.70% | -1.57% | 4 |

For AIG, numeric translation is positive in runs 4, 5, and 6. The paired
geometric-mean speedup is 8.82%, with a model-cluster bootstrap interval of
1.10% to 19.11%. The much larger penalized reduction is still tail-driven:
six additional solves and a small number of expensive models contribute most
of the aggregate gain.

For XAG, numeric translation is not a stable per-instance speed optimization.
Its per-run penalized changes range from a 22.79% gain to a 17.08% loss. The
paired geometric-mean change is a 3.42% slowdown, with a model-cluster interval
of -8.68% to +1.14%. Its small aggregate benefit comes from additional solves,
not consistently cheaper jointly solved cases.

Numeric lift ordering is not supported as a useful treatment. It is neutral
or harmful in aggregate, and combining numeric translation with numeric lift
introduces a large antagonistic interaction. On AIG, the interaction adds
about 2,795 penalized seconds; on XAG it adds about 900 seconds.

## Frozen-query indication

On the selected mechanism subset, changing only the variable mapping while
holding the first-origin frame workload fixed has a modest effect:

- AIG numeric mapping: replay time improves 1.95%, while conflicts increase
  0.93%.
- XAG numeric mapping: replay time improves 4.24% and conflicts improve 2.57%.

For uncensored origin pairs, the numeric-origin live run generates a much
smaller or easier frame-query stream:

| Representation | Paired runs | Frame-query count reduction | Replay conflict reduction | Replay time reduction |
|---|---:|---:|---:|---:|
| AIG | 4 | 35.52% | 30.80% | 25.97% |
| XAG | 12 | 11.74% | 32.66% | 28.03% |

This points toward trajectory effects dominating direct CDCL mapping effects
on the selected sensitive models. The sample is too small and selected to
support a population claim.

## Replay validity warning

All 11,376 successful replay rows reproduce every recorded SAT/UNSAT result;
the eight errors are two empty trace files replayed in four modes. However,
recorded frame replay does not yet reproduce all internal counters exactly:
about 90% of frame files have exactly matching conflicts, with an aggregate
absolute conflict difference around 2.8%.

The trace protocol records add, assume, solve, and explicit variable order, but
not `val` and `failed`. Those calls can introduce an external variable into the
canonical mapping before its later clause/assumption occurrence, so omitting
them changes downstream internal IDs. Mechanism claims based on exact conflict
differences therefore remain provisional until a v2 trace records and replays
these calls.

## Current conclusion

1. Apply numeric ordering to the translation solver only; do not apply it to
   lift.
2. AIG has a reproducible but tail-amplified benefit on this holdout.
3. XAG does not show a stable single-configuration benefit across seeds; its
   value is currently better interpreted as search diversification.
4. Query-stream changes appear larger than frozen-workload mapping changes,
   but v2 replay and random-permutation calibration are required before making
   that the paper-level mechanism claim.
