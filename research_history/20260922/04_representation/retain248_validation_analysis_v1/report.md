# retain248 Cross-Year Held-Out Validation

The policy was frozen before these runs. Each observation is one real 4-lane portfolio;
each model/configuration score is the median of four independent portfolio repeats.
Unsolved repeats cost 1.5 times their timeout. Models unsolved by every
configuration are excluded from aggregate time, but are counted below.

## Coverage

- Recorded task rows: 4112
- Models in result files: 257
- Primary models (at least one configuration solved): 144
- All-configuration unsolved models: 113
- Incomplete model/config cells: 0
- Outcome conflicts: 0

## Configuration totals

| Configuration | Sum of per-model median penalized cost (s) | Solved runs | Models solved at least once | Models solved all 4 runs |
|---|---:|---:|---:|---:|
| aig | 10761.30 | 549 | 139 | 135 |
| compact_aig | 10387.21 | 552 | 140 | 136 |
| full_xag | 11920.86 | 549 | 141 | 134 |
| retain248 | 11434.16 | 549 | 140 | 135 |

## retain248 against frozen baselines

Differences within 2.0 seconds are neutral.

| Baseline | Wins | Losses | Neutral | Aggregate improvement | Geometric speedup |
|---|---:|---:|---:|---:|---:|
| aig | 23 | 17 | 104 | -5.88% | 1.074x |
| compact_aig | 25 | 16 | 103 | -9.16% | 1.059x |
| full_xag | 23 | 22 | 99 | +4.26% | 0.981x |

See `strata.tsv` for year and difficulty-group breakdowns and `per_model.tsv` for audit data.
