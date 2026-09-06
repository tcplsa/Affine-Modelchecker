# Native-XOR Gaussian Specialist: CRC Safety Summary

## Claim that the current evidence supports

Native XOR constraints plus CryptoMiniSat Gaussian elimination form a strong
**specialist for shallow, affine inductive safety queries**.  This is not a
claim that Gaussian elimination is a general replacement for CaDiCaL in PDR,
nor a mixed-portfolio result.

The demonstrated application class is CRC frame-boundary alignment: after a
start-of-frame reset, a serial CRC state and a matrix/parallel CRC state must
remain equal for arbitrary subsequent input traffic.  The transition relation
is a realistic linear-feedback coding datapath, parameterized by standard
CRC-16/CRC-32/CRC-64 polynomials and by bits processed per clock.

All compared runs use the same MC-XAG PDR policy and generated model.  Only
the pure SAT backend changes:

- `4x CaDiCaL`: all four PDR lanes use CaDiCaL;
- `4x CMSat no-Gauss`: all four lanes preserve native XORs but disable Gaussian
  elimination;
- `4x CMSat Gaussian`: all four lanes preserve native XORs and enable Gaussian
  elimination.

Thus the result is not caused by a mixed portfolio and the no-Gauss control
separates Gaussian reasoning from merely changing SAT backends.

## Main controlled result

At an 180-second single-lane screen, 15 CRC parameter points were strict
Gaussian-only cases: both CaDiCaL and native-XOR CMSat without Gaussian
elimination timed out, while Gaussian CMSat proved SAFE.  The 15 points cover
all three standard CRC widths:

| CRC family | Strict Gaussian-only points in coarse sweep | Observed Gaussian boundary in fine sweep (180 s, single lane) |
| --- | ---: | --- |
| CRC-16-CCITT | 4 | solves through 768 bits/transition; times out at 1024 |
| CRC-32/IEEE | 7 | solves through 304 bits/transition; times out at 320 |
| CRC-64/ECMA-182 | 4 | solves through 120 bits/transition; times out at 124 |

The coarse 15 strict points were then confirmed at the actual hard limit:

- 4x CaDiCaL: `15/15` time out at 1,800 seconds;
- 4x native-XOR CMSat without Gaussian: `15/15` time out at 1,800 seconds;
- 4x native-XOR CMSat with Gaussian: `15/15` prove SAFE;
- every row was repeated with two independent process seeds.

The exact coarse table and confirmations are in
[pure_boundary_report.md](/home/wudl/test_tools/compare/results/pathb_crc_gauss_boundary_v1/pure_boundary_report.md).
The fine boundary table is in
[pure_boundary_report.md](/home/wudl/test_tools/compare/results/pathb_crc_gauss_boundary_fine_v1/pure_boundary_report.md).

## Comparison against stock rIC3

Two CRC-32 points (`32` and `64` bits/transition) received the stricter
cross-tool comparison.  On each point and on two independent launches:

| Method | Outcome at 1,800 s |
| --- | --- |
| MC-XAG, one CaDiCaL lane | TIMEOUT |
| MC-XAG, one native-XOR CMSat lane without Gaussian | TIMEOUT |
| MC-XAG, one native-XOR CMSat Gaussian lane | SAFE in about 0.50 s |
| Stock rIC3, native four-replica portfolio | TIMEOUT |

This is a real 1,800-second boundary crossing, not a 1,800-to-3,600-second
frontier speedup.  The raw confirmation is in
[crc32_gauss_1800_confirmation.md](/home/wudl/test_tools/compare/results/pathb_real_xor_apps_v1/crc32_gauss_1800_confirmation.md).

## Why it works

1. A parallel CRC update is an affine linear map over GF(2): the next state is
   `s' = A*s xor B*x`.
2. The property asks whether two independently encoded implementations of that
   same map can diverge.  Under the induction query, this yields a large,
   highly connected affine system.
3. XAG keeps the equations explicit as native XOR constraints.  Gaussian
   elimination combines the equations globally and derives the contradiction
   directly.
4. A CNF/CDCL path instead sees a large XOR lowering.  It must rediscover the
   linear consequences through Boolean propagation, conflicts, and learning.
   The no-Gauss CMSat timeout shows that retaining XOR syntax alone is not
   sufficient for these points.

The sharp width boundary is expected: above a given parallelism the affine
system is still manageable by elimination; at the next size, even the current
Gaussian implementation and PDR integration exhaust the fixed time budget.
This makes the result more informative than a single hand-picked instance.

## Important limitation: this is not deep-PDR acceleration

The frame-alignment proofs converge at frame depth one.  That is still an
unbounded SAFE proof, but it specifically demonstrates a powerful inductive
SAT-query specialization rather than improved obligation management.

We also built a deeper CRC residue/FCS benchmark.  There, the same property
requires depth 7--20 and thousands of incremental PDR queries.  On a
representative CRC-32 case:

| Backend | Result |
| --- | --- |
| CaDiCaL | SAFE in 0.415 s, depth 11 |
| Native-XOR CMSat, no Gaussian | SAFE in 64.014 s, depth 11 |
| Native-XOR CMSat, Gaussian | SAFE in 68.519 s, depth 11 |

Gaussian elimination does not change that PDR trajectory and adds overhead.
The likely reason is that phase control, assumptions, learned frame clauses,
and repeated incremental queries fragment the global affine closure.  CaDiCaL
also benefits from its effective CNF simplification/BVE and mature incremental
CDCL behavior.  Therefore the honest architecture is a **query/domain-gated
Gaussian specialist**, not a global solver replacement.

## Presentation-ready conclusion

> On parameterized CRC frame-alignment safety problems, native XOR Gaussian
> reasoning creates a large and repeatable capability boundary: 15 instances
> that time out for both pure CaDiCaL and native-XOR CMSat without Gaussian at
> 1,800 seconds are solved by pure Gaussian CMSat in two independent four-lane
> runs.  Two CRC-32 points also time out for stock rIC3-4 but are solved by MC
> with Gaussian reasoning in about 0.5 seconds.  The effect is structurally
> explained by full affine closure, and its deep-PDR limit is explicitly shown
> on CRC residue verification where Gaussian reasoning is slower than CaDiCaL.

## Next implementation direction

Keep a pure Gaussian lane only when static/dynamic features indicate an affine
induction query: high XAG XOR density in the transition and bad cone, a large
shared XOR support between current/next state, and shallow frame progress.
Do not enable it for deep residue, control-heavy, or high-assumption queries.
The next research step is to implement this gate in MC and validate it on
independent CRC/link-coding blocks and then on naturally occurring HWMCC
affine cones.
