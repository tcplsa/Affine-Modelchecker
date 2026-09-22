# Structure-Aware BVE Claim Audit

This is the short evidence ledger for the paper draft. A claim may appear in the
abstract or conclusion only when marked **supported**.

| Claim | Status | Evidence | Allowed wording |
|---|---|---|---|
| `product-sum-high` improves typical multiplicative rIC3 runtime | **supported** | 556 models, 3 seed blocks, concurrent 4-replica control; common-solve geo 0.972, clustered 95% CI 0.950--0.995 | "reduces common-solve geometric-mean runtime by 2.8%" |
| `product-sum-high` lowers summed common-solve rIC3 time | **refuted** | Legacy totals 32,524.7 s and candidate totals 33,680.7 s on 1,482 common solves; ratio 1.036 | "summed common-solve time regresses by 3.6% because a small tail of slowdowns dominates" |
| `product-sum-high` improves penalized rIC3 cost | **supported** | Concurrent report: PAR-1.5 0.955 | "improves informative PAR-1.5 by 4.5%" |
| `product-sum-high` solves more rIC3 instances | **not supported** | 1,486/1,486 aggregate; only/lost 4/4 | "coverage-neutral in the primary confirmation" |
| Improvement is caused by fewer clauses | **refuted** | Residual clauses 0.995, literals 1.000, simplify time 1.002 | "not explained by final CNF size" |
| The policy changes the retained BVE resolvent profile | **supported** | Kept resolvents 0.874, resolvent literals 1.064, max width 1.233 | "changes the number, width, and literal mass of retained resolvents" |
| Changed resolvents cause changed CDCL behavior | **not identified** | Existing role-aware MC observables concern a related intervention; frame propagations/decisions and SAT-query counts correlate with runtime but do not isolate this treatment | Hypothesis only; requires frozen-query factorial replay |
| Changed CDCL behavior causes a changed PDR trajectory | **not identified** | No exact-treatment trace currently connects learned clauses/cores to predecessor cubes, obligations, and lemmas | Hypothesis only; requires semantic-event alignment and first-divergence analysis |
| XAG is universally beneficial | **refuted** | Static audit has no accepted cross-family selector; result varies by year/seed | Do not claim |
| Fill-aware direction transfers to the compact checker | **supported; multi-seed confirmation running** | 1,907 concurrent models: 1,071/1,069 solved, common-solve geo 0.963, family-cluster CI 0.940--0.988, summed common-runtime ratio 0.984, PAR 0.929; separate 108-model holdout geo 0.911 | "improves compact-checker geometric, summed-common, and penalized runtime metrics in a large single-seed campaign and a disjoint holdout" |
| LPP phase diversity improves a true four-lane portfolio | **refuted** | Native shared-termination screen: 474 vs 476 for 2PPP+2LPP | Do not claim |
| Per-instance static choice is solved | **not supported** | Current selector has zero accepted cross-family gain | Future work only |

## Exact report locations

- Main strict rIC3 result: `results/ric3_order_concurrent_v1/report.md`
- BVE telemetry: `results/ric3_order_mechanism_v1/report.md`
- Native portfolio correction: `results/ric3_phase_allocation_v1/report.md`
- Seed-layout control: `results/ric3_phase_pairing_v1/report.md`
- Large compact-checker result: `results/bve_full_campaign_v1/mc_partial_stopped_report.md`
- Compact-checker multi-seed confirmation: `results/mc_sumhigh_concurrent_v1/report.md`
