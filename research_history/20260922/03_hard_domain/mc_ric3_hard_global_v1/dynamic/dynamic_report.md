# Global dynamic atlas of stock-rIC3-3600 hard models

Completed progress rows: 590/590.
Solved inside the diagnostic budget: 9.

Labels are overlapping failure signatures derived from global quartiles. They are
used to choose experiments, not presented as semantic ground truth.

## Thresholds

- `depth_low`: 2.000
- `depth_high`: 9.000
- `queries_low`: 797.000
- `queries_high`: 78905.000
- `cti_depth_high`: 91.500
- `mic_depth_high`: 332.167
- `push_depth_high`: 703.889
- `conflict_query_high`: 1.577

## Failure signatures

| Signature | Models | Largest contributing families |
| --- | ---: | --- |
| `mixed-middle` | 201 | oski:29, yosyshq_appnote_:28, arbitrated_top_n:25, picorv:21, intel:9, circular_pointer_top_w:8 |
| `high-query-volume` | 146 | vgasim_imgfifo:11, oc:10, zipcpu:7, circular_pointer_top_w:4, rast:4, beemextnc:3 |
| `sat-heavy-query` | 146 | oski:30, Problem:16, cal:12, level_:9, mul:6, pals_lcr:6 |
| `front-end-or-few-query` | 117 | Problem:22, yosyshq_appnote_:21, cal:16, oski:15, mul:7, pals_lcr:7 |
| `push-convergence` | 65 | oc:6, vgasim_imgfifo:6, ponylink:3, zipcpu:3, beemextnc:2, intel:2 |
| `early-obligation-generalization` | 38 | oski:16, cal:4, shift_register_top_w:2, a:2, 6s184:1, 6s13:1 |
| `solved` | 9 | zipcpu:5, beempgsol:1, mul:1, gcd_:1, AllInterval:1 |

## Research routing

| Signature | First controlled intervention |
| --- | --- |
| `front-end-or-few-query` | preprocessing, BMC0/first-pre SAT backend, query presentation |
| `early-obligation-generalization` | obligation order, MIC literal order, CTG selection |
| `sat-heavy-query` | selective native XOR/CMSat, abstraction, phase/model control |
| `push-convergence` | lemma strength/priority, push policy, invariant templates |
| `high-query-volume` | lemma reuse/sharing and duplicate-query suppression |

A candidate is tested first on several families inside one signature and then on
held-out families from that signature. Filename- or family-specific dispatch is not
accepted as the final mechanism.
