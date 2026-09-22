# CNF Random Replay Calibration

Rows: 29282; status counts: {'OK': 29282}.

## Recorded fidelity

| Role | Traces | Conflicts exact | Decisions exact | Propagations exact | Restarts exact | Observation mismatches |
|---|---:|---:|---:|---:|---:|---:|
| frame | 2580 | 2580/2580 | 2580/2580 | 2580/2580 | 2580/2580 | 0 |
| lift | 82 | 82/82 | 82/82 | 82/82 | 82/82 | 0 |

## Deterministic mapping versus random noise floor

Positive reductions mean the deterministic candidate is cheaper than the recorded mapping.
The random percentile is the fraction of fixed random mappings whose aggregate conflict count is worse than the candidate.

| Representation | Origin | Role | Candidate | Traces | Conflict reduction | Time reduction | Random conflict range | Candidate random percentile |
|---|---|---|---|---:|---:|---:|---:|---:|
| aig | first/first | frame | numeric | 501 | +0.85% | +2.45% | 1,216,899..1,249,994 | 0.0% |
| aig | first/first | lift | numeric | 13 | -0.00% | +6.55% | 107,219..107,247 | 0.0% |
| aig | numeric/numeric | frame | first | 442 | +3.78% | -2.01% | 1,258,879..1,283,211 | 37.5% |
| aig | numeric/numeric | lift | first | 13 | -0.02% | -5.03% | 77,147..77,162 | 0.0% |
| xag | first/first | frame | numeric | 849 | +3.36% | +4.33% | 1,961,657..2,185,015 | 100.0% |
| xag | first/first | lift | numeric | 28 | -0.00% | -0.62% | 158,875..158,907 | 12.5% |
| xag | numeric/numeric | frame | first | 788 | +6.17% | -1.54% | 1,506,376..2,010,505 | 50.0% |
| xag | numeric/numeric | lift | first | 28 | +0.03% | +3.71% | 126,092..126,167 | 62.5% |

## Model-paired robustness

Frame files are summed within each model/run before computing paired log reductions. Random ranges contain the eight fixed random seeds.

| Representation | Origin | Role | Candidate | Model/runs | Geometric reduction | Median reduction | Wins/losses/equal | Random geometric range | Random median range | Beats random median/all |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| aig | first/first | frame | numeric | 15 | +0.75% | +0.30% | 8/4/3 | -44.36%..+2.58% | +0.85%..+2.59% | 5/0 |
| aig | first/first | lift | numeric | 13 | -0.00% | +0.00% | 0/1/12 | -0.00%..+0.01% | +0.00%..+0.00% | 0/0 |
| aig | numeric/numeric | frame | first | 15 | +7.75% | +2.46% | 11/2/2 | -54.00%..+9.38% | +1.94%..+3.72% | 7/1 |
| aig | numeric/numeric | lift | first | 13 | -0.01% | +0.00% | 0/2/11 | -0.01%..+0.00% | +0.00%..+0.00% | 0/0 |
| xag | first/first | frame | numeric | 30 | +9.90% | +2.89% | 23/6/1 | -6.95%..+15.07% | +1.89%..+3.75% | 16/7 |
| xag | first/first | lift | numeric | 28 | -0.00% | +0.00% | 1/2/25 | -0.01%..+0.01% | +0.00%..+0.00% | 2/0 |
| xag | numeric/numeric | frame | first | 30 | +9.27% | +2.33% | 23/7/0 | +8.13%..+25.46% | +3.08%..+4.39% | 12/2 |
| xag | numeric/numeric | lift | first | 28 | +0.02% | +0.00% | 1/1/26 | -0.01%..+0.03% | +0.00%..+0.00% | 2/0 |

## Cross-origin 2x2 conflict decomposition

A=first mapping/first-origin workload, B=numeric mapping/first-origin workload,
C=first mapping/numeric-origin workload, D=numeric mapping/numeric-origin workload.
All values aggregate the traced workload prefixes; censored traces remain censored.

| Representation | Role | Pairs | A | B | C | D | Internal (B-A)/A | Flow (C-A)/A | Interaction/A | Total (D-A)/A |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| aig | frame | 15 | 1,266,209 | 1,255,476 | 1,280,295 | 1,330,533 | -0.85% | +1.11% | +4.82% | +5.08% |
| aig | lift | 13 | 107,245 | 107,248 | 77,162 | 77,150 | +0.00% | -28.05% | -0.01% | -28.06% |
| xag | frame | 30 | 1,996,296 | 1,929,267 | 1,618,638 | 1,725,097 | -3.36% | -18.92% | +8.69% | -13.59% |
| xag | lift | 28 | 158,890 | 158,892 | 126,117 | 126,151 | +0.00% | -20.63% | +0.02% | -20.60% |
