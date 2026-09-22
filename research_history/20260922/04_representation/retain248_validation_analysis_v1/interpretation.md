# retain248 Held-Out Validation: Interpretation

## Verdict

`retain248` is not a stable universal replacement for either AIG or Full-XAG.
The frozen rule does expose a real and sometimes very large causal effect, but the
sign of that effect changes across closely related circuits. The current structural
buckets are therefore insufficient to predict which XORs should be retained.

## Experimental scope

- 257 HWMCC 2024/2025 models on which the frozen rule changes at least one XOR.
- 4 representations: AIG, Compact-AIG, Full-XAG, and retain248.
- 4 independent real four-lane portfolios per model/representation.
- 4,112 complete task rows; no missing cells and no SAFE/UNSAFE conflicts.
- 600 second timeout; unsolved observations receive a 900 second penalty.
- 113 models were unsolved by every representation and excluded from primary time totals.
- The 7 exit-9 rows belong to 3 models unsolved by every representation, so they do
  not affect any primary aggregate or pairwise result.

## Primary result

| Baseline | retain248 wins | Losses | Neutral (<=2 s) | Aggregate change | Geometric speedup |
|---|---:|---:|---:|---:|---:|
| AIG | 23 | 17 | 104 | 5.88% slower | 1.074x |
| Compact-AIG | 25 | 16 | 103 | 9.16% slower | 1.059x |
| Full-XAG | 23 | 22 | 99 | 4.26% faster | 0.981x |

The aggregate and geometric results disagree because a few timeout-scale reversals
dominate total time. On typical small jointly solved models retain248 is often a
little faster than AIG, but its rare losses can be catastrophic.

## Domain split

Against Full-XAG, retain248 is 30.30% faster on the 2024 primary subset and 13.62%
slower on 2025. Against AIG it is essentially tied on 2024 (+0.16%) and 10.04%
slower on 2025. This is a strong year/family shift, not a stable cross-year effect.

The difficulty split also changes sign:

| Group | Models in primary set | vs AIG | vs Full-XAG |
|---|---:|---:|---:|
| fast | 42 | +11.40% | -7.60% |
| medium | 54 | +6.13% | -5.04% |
| slow | 21 | -58.84% | -48.36% |
| old-MC timeout | 27 | +1.82% | +12.95% |

All 42 fast comparisons are within the two-second neutral threshold, so their
percentage changes should not be treated as practically meaningful. The slow and
hard groups contain the decisive observations.

## Decisive paired counterexample

Two adjacent AllInterval instances show that the effect is real but not captured by
the current buckets:

| Model | Full-XAG | retain248 | Removed XORs | Result |
|---|---:|---:|---:|---|
| AllInterval-019 | 4/4 timeout | about 60 s, 4/4 solved | 36 / 15,462 | retain helps dramatically |
| AllInterval-020 | about 190 s, 4/4 solved | 4/4 timeout | 19 / 14,516 | retain hurts dramatically |

In both models every removed XOR belongs to the same
`fanout_2_3__far_gt8__isolated` bucket. Both properties have depth 1 and require only
3-4 SAT queries. The timeout reversal therefore does not come from a long IC3 frame
search; a tiny representation change sends the SAT encoding/simplification into a
different internal path.

The 2024 Full-XAG aggregate gain is also not broad. AllInterval-019 contributes
about 840 seconds and `xepic_a17-p02` about 512 seconds of the total 487-second net
gain. The latter is from the same x-epic generator family as the phase-5 a16 model,
so it is not a strict family-held-out success. After removing AllInterval-019,
AllInterval-020, and xepic_a17-p02, retain248 is 1.52% slower than Full-XAG.

Model-level bootstrap uncertainty for the Full-XAG aggregate improvement is wide:
approximately -15.6% to +33.2% at 95%. The removed-XOR fraction has almost no linear
relationship with log speedup (Pearson r = -0.074).

## What is established

1. Selective XOR representation can reproducibly change solvability by hundreds of seconds.
2. The effect is not explained by CNF size, removed-XOR count, or the current fanout/distance/adjacency bucket alone.
3. Multi-lane randomness does not explain the AllInterval reversal: each direction repeats 4/4 times.
4. retain248 is useful as a causal probe, but is not ready to become the default representation policy.

## Next experiment

Use AllInterval-019 and AllInterval-020 as a matched causal pair. Run deterministic
leave-one-XOR-out and add-one-XOR-back interventions over their 36 and 19 affected
XORs, followed by small combinations of the individually influential gates. Record
solver construction, simplification, first predecessor query, conflicts, decisions,
propagations, and learned clauses separately. This can identify whether one specific
XOR, its variable position, or an interaction among XORs triggers the reversal.

That experiment is much more informative than adding more random seeds or fitting a
new classifier to the same coarse buckets: it targets the first confirmed structural
counterexample where nearly identical bucket statistics produce opposite outcomes.
