# Structure-Aware CNF Elimination for PDR

## Research question

The optimization target is not XAG in isolation. It is the representation of the
transition relation presented to the PDR SAT solvers after preprocessing. The study
tests whether a structural representation and a deterministic bounded-variable-
elimination (BVE) order can improve both a research MC implementation and rIC3.

The causal chain under test is:

1. AIG or XAG encoding determines auxiliary variables and local defining clauses.
2. BVE chooses an order in which non-frozen auxiliary variables are removed.
3. Earlier removals change occurrence counts and resolvents seen by later removals.
4. The resulting CNF changes propagation, learnt clauses, and the cost of every PDR
   predecessor, generalization, and propagation query.
5. Those per-query changes can also alter the PDR query trajectory.

## Mathematical mechanism

For an eliminable variable `v`, let

- `p(v)` be the number of clauses containing `v`;
- `n(v)` be the number of clauses containing `not v`.

Eliminating `v` resolves each positive clause against each negative clause. Before
tautology and subsumption filtering, the number of candidate resolvents is bounded by

`fill(v) <= p(v) * n(v)`.

The product is therefore a local upper bound on resolution work and a first-order
proxy for fill-in. It is not a predictor of total PDR time: resolvent lengths,
tautologies, subsumption, BCP, CDCL branching, and the PDR query trajectory still
matter. It is nevertheless available before PDR and directly tied to the operation
being optimized.

The candidate MC policy orders variables lexicographically by

`(p(v) * n(v), p(v) + n(v), -id(v))`.

This is called `sum-high`: prefer low estimated fill, then low total incidence, then
the higher variable ID. In a topologically numbered AIG/XAG, higher gate IDs usually
refer to later or more output-proximal definitions. Removing these local definitions
before lower, more widely shared variables is expected to reduce cross-cone
resolvents. That final interpretation is a testable structural hypothesis, not a
general theorem about arbitrary DIMACS numbering.

rIC3's legacy BVE order differs from MiniSat's: it primarily uses `p(v) + n(v)`.
The migrated candidate `product-high` changes it to `(p(v) * n(v), -id(v))`. Thus the
rIC3 experiment tests transfer of the fill-aware principle, rather than blindly
copying an implementation-specific enum value.

## Why semantics are preserved

BVE replaces clauses containing an auxiliary pivot by their resolvents. This is
equisatisfiable after existentially quantifying that pivot. State variables and other
observable transition-system variables remain frozen, so the state-level transition
relation needed by PDR is preserved. Only candidate priority changes; the existing
acceptance limits, frozen-variable rules, and proof obligations are unchanged.

Regression evidence currently includes:

- the full MC directional regression for all five elimination orders;
- rIC3 workspace tests;
- 30 direct rIC3 checks from 3 safe/unsafe fixtures, 2 encodings, and 5 orders;
- no outcome conflict in the completed MC development/validation experiments.

## Evidence available before the full campaign

### MC, four deterministic diverse lanes

The development and disjoint validation sets contain 108 models in total. On the 63
models jointly solved by XAG `sum-high` and XAG legacy, the geometric runtime ratio is
0.911 with a 95% bootstrap interval of 0.847--0.984. The median ratio is 0.927 and the
greater-than-2-second win/loss count is 19/6. Both configurations solve 64 models.

Against AIG legacy, XAG `sum-high` has a geometric runtime ratio of 0.842 with a 95%
bootstrap interval of 0.787--0.899 on 63 common solves. It solves 64 versus 65 models,
so the final claim must jointly consider runtime and coverage rather than runtime
alone.

These results support a stable average improvement on the sampled population, but do
not yet establish all-year hard-instance coverage.

The later all-year campaign provides much larger same-machine evidence. It completed
1,907 of 1,980 models before the common-timeout tail was stopped. Within every model,
four-lane XAG legacy and four-lane XAG `sum-high` were launched concurrently with
matched explicit lane seeds. `sum-high` solves 1,071 models versus 1,069 for legacy,
with 14 unique solves and 12 losses. On 1,057 common solves, its geometric runtime
ratio is 0.963 with a family-clustered 95% interval of 0.940--0.988; its informative
PAR-1.5 ratio is 0.929. Thus the large single-seed-block result supports both expected
runtime and penalized-cost improvement, but it is not yet a multi-seed confirmation.

The strict follow-up reuses the same 556-model, year/tier-stratified selection as the
rIC3 confirmation. It compares only four-lane XAG legacy and four-lane XAG `sum-high`,
uses three disjoint explicit seed blocks, a 1,800-second timeout, and concurrent launch
within each model. This test determines whether the 1,907-model effect survives solver
seed variation and permits a direct compact-checker/rIC3 comparison.

### rIC3 screening and four-core validation

On a 48-model single-IC3 screen, XAG `product-high` solves 31 models versus 30 for XAG
legacy, loses none, and has a common-solve geometric runtime ratio of 0.915.

On a disjoint 60-model real four-core portfolio validation, `product-high` solves 43
models versus 42 for XAG legacy, with two unique solves and one loss. Its common-solve
geometric ratio is 0.945 and median ratio is 0.919. However, its greater-than-2-second
win/loss count is 1/3 and its penalized cost is 1810.4 versus 1806.6 for XAG legacy.
AIG legacy solves 43 models and has the lowest penalized cost, 1740.0. No configuration
produces an outcome conflict.

The transferable conclusion is therefore limited: fill-aware ordering improves the
typical common-solve runtime and changes coverage in rIC3, but it is not yet a stable
portfolio-level win. The all-year rIC3 campaign is a boundary/transfer test, not a
confirmation run for a result already assumed true.

### Current distance from stock rIC3

An interim historical join is useful only as a scale estimate. On 426 currently
completed MC models that overlap the old 2015/2017/2019 single-IC3 records, four-lane
MC is about 3.05 times slower geometrically than stock rIC3. On 99 overlaps with an
older four-way rIC3 race, the observed gap is larger. These are not final comparisons:
they mix versions, server loads, experiment dates, and a completion-biased MC subset.

The final campaign therefore performs an exact model join between four-lane MC XAG
`sum-high`, four-core stock rIC3 Native legacy, and four-core rIC3 Native-local, all
with the same 1,800-second limit. The resulting report treats common-solve speed and
unilateral hard-instance coverage as separate outcomes.

## Final experiment protocol

The frozen manifest contains 1,980 exact-content-deduplicated HWMCC models:

| Year | Models |
|---|---:|
| 2015 | 490 |
| 2017 | 217 |
| 2019 | 310 |
| 2020 | 324 |
| 2024 | 319 |
| 2025 | 320 |

Historical tiers contain 142 trivial, 242 fast, 247 medium, 136 slow, 1,212 timeout,
and 1 error model. Three stable shards contain exactly 660 models each and are balanced
within every year/tier stratum.

MC compares `4xAIG legacy`, `4xXAG legacy`, and `4xXAG sum-high`. The final rIC3 study
uses its stock Native/Optimized encoder, which recognizes both structural XOR and ITE,
and compares `Native legacy`, `Native product-high`, and `Native native-local` in
the same four-core control portfolio. The earlier explicit-XAG runs are retained only
as transfer screening and are not part of the final rIC3 claim. All configurations for
one model run concurrently, use the same master seed, and have a 1,800-second limit.

`native-local` retains the product fill estimate as its primary key. When products tie,
it postpones a structurally recognized XOR/ITE output that feeds multiple later
definitions, then uses total incidence and high variable ID. This preserves shared
propagation-complete parity/multiplexer boundaries without freezing them or overriding
the existing exact BVE acceptance test.

The primary outcome is solved count. Informative PAR-1.5, where pairs unsolved by
both sides are removed, is the first tie-break and also identifies useful Pareto
tradeoffs that solve slightly fewer models but remain cheaper after timeout penalties.
Common-solve paired log runtime ratios, bootstrap intervals, greater-than-2-second
wins/losses, year strata, and historical difficulty strata are secondary outcomes.
MC also records raw/simplified variables, clauses, literals, SAT queries, and PDR
depth for mechanism analysis.

## Claims permitted after the campaign

The strongest claim requires all of the following:

1. XAG `sum-high` improves MC informative PAR-1.5 without a material coverage loss.
2. The paired geometric-mean interval against XAG legacy remains below 1.0.
3. Improvement is not confined to one year or only sub-second models.
4. At least the fill-aware direction transfers to rIC3, or rIC3 clearly identifies the
   implementation boundary that prevents transfer.
5. Mechanism statistics distinguish smaller/friendlier simplified CNF from merely a
   lucky change in the PDR query trajectory.

If rIC3 does not improve, the valid conclusion is narrower but still useful: the
`p*n` elimination score is portable as a preprocessing principle, while the high-ID
tie break depends on encoding and simplifier conventions. If MC gains disappear on
the all-year set, the method remains a portfolio-diversification candidate rather than
a default preprocessing replacement.

## Hard-tail specialization

The interim full-campaign hard tail rules out treating `sum-high` as an unconditional
replacement. On completed historical-timeout models, XAG `sum-high` is typically close
to XAG legacy, but each order has five unilateral solves. Across all three MC
configurations, the union currently solves nine more models than the best individual
configuration. This is useful diversity, but it is not yet a four-core improvement.

The mechanism is not a meaningful reduction in simplified CNF size. On common solves
where `sum-high` beats legacy by more than two seconds, its SAT-query count has a
geometric ratio near 0.78; on losses the ratio is about 1.53. Simplified-clause ratios
remain near 1.0 in both groups. The elimination tie break therefore changes both CDCL
cost and, more importantly on the tail, the sequence of predecessor models, cores,
obligations, and lemmas generated by PDR.

MC previously used one elimination order for two different CNF roles. The translation
CNF supplies the transition relation used by frame, predecessor, and inductiveness
queries. The lift CNF is used when extracting and lifting predecessor states. The new
experiment exposes independent, backward-compatible order controls:

- `MC_PDR_MINISAT_TRANSLATION_ELIM_ORDER`;
- `MC_PDR_MINISAT_LIFT_ELIM_ORDER`.

The frozen hard-tail development experiment evaluated the two off-diagonal cells
`sum-high/legacy` and `legacy/sum-high`, plus a fixed four-lane 2+2 order portfolio.
On all 101 models, `legacy/sum-high` solves 55, versus 51 for AIG legacy and 50 for
each homogeneous XAG baseline. Its informative PAR ratio is 0.874 against AIG,
0.773 against XAG legacy, and 0.794 against homogeneous XAG sum-high. It therefore
improves both the primary coverage objective and penalized cost. The opposite role
assignment solves only 45, isolating the benefit to the lift role rather than a global
preprocessing change.

On common solves, `legacy/sum-high` performs about 5.5% more SAT queries than XAG
legacy while taking about 6.1% less wall time. The result is consequently not explained
by fewer PDR queries or a smaller translation CNF. The plausible mechanism is that
fill-aware elimination changes assumption dependencies and UNSAT cores in the lift
solver; those cores determine predecessor cubes and thereby alter later obligations and
lemmas. Keeping translation on legacy preserves the main predecessor search trajectory.

The role-specialized configuration does not yet exceed the 59-model union of all old
baselines. The next fixed-budget experiment allocates one or two of four lanes to AIG
or legacy-XAG rescue while retaining two or three role-specialized XAG lanes. A disjoint
four-seed replication separately tests whether the 55-solve result is stable. Full-set
and rIC3 transfer claims remain gated on those validations.

## Concurrent multi-seed confirmation

The original full-set product-sum-high run covered all 1,980 models, but reused
Native-legacy results from an earlier campaign. A stricter confirmation therefore
launched Native legacy and Native product-sum-high concurrently within each model.
It used 556 year/tier-stratified models, three new master seeds, four IC3 replicas per
configuration, and a 1,800-second timeout. The resulting 1,668 paired observations
had no outcome conflicts.

| Metric | Product-sum-high | Native legacy |
|---|---:|---:|
| Solved observations | 1,486 | 1,486 |
| Configuration-only observations | 4 | 4 |
| Common-solve geometric ratio | 0.972 | 1.000 |
| Model-clustered 95% interval | 0.950--0.995 | - |
| Informative PAR-1.5 ratio | 0.955 | 1.000 |

This confirms a small but statistically stable average speed improvement under
same-machine, same-load execution. It does not establish strict coverage dominance:
aggregate coverage is equal, and individual seeds differ by 0, -1, and +1 solved
observations. Historical-timeout observations are also coverage-neutral (184/184)
with a 0.930 common-solve ratio and a 0.942 PAR ratio.

The effect is asymmetric. SAFE observations gain three unilateral solves and have a
0.968 common-solve ratio, whereas UNSAFE observations lose three net solves and have a
0.990 ratio. Year 2025 contributes all three net unilateral gains, while 2019, 2020,
and 2024 each lose one. The defensible claim is therefore improved expected runtime
and penalized cost, not universal instance-level or hard-instance dominance.

## Elimination telemetry

An instrumented build was run on 75 models selected from stable wins, stable losses,
neutral cases, and coverage-discordant cases. Instrumentation only counted BVE work;
it did not change candidate order or acceptance. Product-sum-high / legacy geometric
ratios are:

| Observable | Ratio |
|---|---:|
| BVE attempts | 0.988 |
| Variables eliminated | 1.012 |
| Growth rejections | 0.957 |
| Clauses removed | 0.913 |
| Kept resolvents | 0.874 |
| Resolvent literals | 1.064 |
| Estimated merge checks | 0.980 |
| Residual clauses | 0.995 |
| Residual literals | 1.000 |
| Maximum resolvent width | 1.233 |
| Simplification time | 1.002 |

Thus the gain is not explained by a materially smaller final CNF or cheaper
preprocessing. The fill-aware order creates fewer retained resolvents, but those
resolvents are wider; final clause and literal counts are almost unchanged. On the
stable-fast group, resolvent count is 0.897 while maximum width is 1.499 and resolvent
literals are 1.093. On stable losses, the corresponding ratios are 0.912, 1.052, and
0.970. The distinguishing signal is therefore not clause count alone: successful
runs more strongly trade many narrow local resolvents for fewer wider dependency
clauses.

The current mechanistic hypothesis is that this changes auxiliary-variable
connectivity, CDCL implication paths, and assumption-core composition. PDR then sees
different predecessor cubes and lemmas even though the state-level transition relation
and aggregate CNF size are preserved. This is directly consistent with the earlier
observation that SAT-query count, rather than simplified CNF size, separates MC wins
from losses. A future instrumented run should add clause-width histograms, assumption
core sizes, and frame/lift CDCL counters to test this final link.

## Phase-specific elimination order

rIC3 invokes BVE at three semantically different points: initial preprocessing,
post-SCorr preprocessing, and post-FrTs preprocessing. An eight-cell deterministic
screen assigned legacy (L) or product-sum-high (P) independently to those phases on
the same 556-model selection. Every cell used one IC3 replica, one common seed, and a
300-second timeout.

PPP is the best homogeneous default in this screen. Relative to LLL, it solves one
additional model, has a 0.958 common-solve geometric ratio, and a 0.898 informative
PAR-1.5 ratio. PLP solves two additional models and has a 0.924 PAR ratio, but is not
faster than PPP. No mixed order dominates PPP as an individual configuration.

The coverage sets are nevertheless complementary. The one-replica union of PPP and
PLP solves three models missed by PPP, while PPP and LPP solves four. Those ideal
unions are not evidence for a usable improvement because they spend twice the compute.
The follow-up experiment therefore compares equal four-replica budgets:

- four PPP replicas;
- four LLL replicas;
- two PPP plus two LPP replicas;
- two PPP plus two PLP replicas.

A mixed portfolio advances only if it does not reduce solved count, lowers informative
PAR-1.5, and adds net solves in the slow or historical-timeout tiers. Passing this
screen triggers a three-seed, 1,800-second confirmation; otherwise PPP remains the
default and phase diversification is rejected as an inefficient use of four cores.

The equal-budget screen passed that gate. On 556 models with a 600-second timeout,
four PPP replicas solve 488 models. Two PPP plus two PLP replicas solve 489, with two
unique solves, one lost solve, a 0.989 common-solve geometric ratio, and a 0.945
informative PAR-1.5 ratio. The net new solve is in the historical-timeout tier; the
portfolio additionally converts `ILA_Ridecore_SLT_sanity`, an UNSAFE instance, from a
timeout to a 380-second solve. Its only lost model is a 21-second PPP solve, so the
coverage result is not produced by sub-second noise.

Two PPP plus two LPP replicas are coverage-neutral overall but solve one additional
historical-timeout model and have a 0.818 PAR ratio in that tier. They lose one slow
model. This supports role diversity but does not yet establish a default replacement.
The screen used only one seed block, so the next confirmation uses three disjoint seed
blocks, the same 556 models, and a 1,800-second timeout. It compares the two mixed
portfolios directly with four PPP replicas under the same four-replica budget.

That three-seed confirmation contains 1,668 paired observations and no outcome
conflicts. Four PPP replicas solve 1,485 observations. The two-PPP/two-LPP portfolio
solves 1,487, with three unique solves and one loss. Its common-solve geometric ratio
is 0.978, with a model-clustered 95% interval of 0.962--0.995, and its informative
PAR-1.5 ratio is 0.841. Historical-timeout observations improve from 183 to 185 solves
and have a 0.843 PAR ratio. The improvement covers both outcomes: SAFE gains one solve
without a loss, while UNSAFE gains two and loses one.

Two PPP plus two PLP replicas solve 1,486 observations, but their common-solve ratio is
0.999 with a clustered interval of 0.981--1.017. PLP therefore retains some coverage
diversity but does not reproduce a stable runtime gain. LPP is the surviving phase
specialization.

The confirmation represented each mixed candidate as two independently terminated
two-replica sub-portfolios. This gives the correct time-to-first-answer but leaves the
losing subgroup running after its sibling subgroup succeeds. A deployment-quality
portfolio should terminate all four heterogeneous lanes together. The next experiment
adds native heterogeneous replicas to the common runner and screens all PPP/LPP
allocations from 4+0 through 0+4 on the slow and historical-timeout tiers. This both
removes residual load bias and determines whether one, two, or three specialized lanes
best trades baseline seed diversity for structural diversity.

## Native heterogeneous-portfolio correction

The native shared-termination allocation screen rejects LPP as a default portfolio
lane. Across 217 slow and historical-timeout models and three fresh seed blocks,
four PPP lanes solve 476 observations. Replacing one PPP lane by LPP solves 475;
the 2+2 allocation solves 474; 1+3 solves 471; and four LPP lanes solve 467. The
common-solve intervals of all mixed allocations include 1.0, while their PAR-1.5
ratios range from 1.048 to 1.486. LPP can reduce runtime for some individual slow
instances, but it sacrifices precisely the tail coverage that the portfolio is meant
to protect.

The previous apparent 2+2 benefit was not a deployable four-lane result: its two
sub-portfolios terminated independently and their random-seed assignment differed
from the all-PPP baseline. A native paired-seed control confirms that neither
repeating the same two seeds under PPP and LPP nor splitting four seeds across the
two representations gives a coverage or PAR improvement. This is a useful negative
result. The final paper must not claim a phase-order portfolio; it should report this
ablation as evidence that structural diversification cannot be assessed by offline
minima or by combining separately terminated solver groups.
