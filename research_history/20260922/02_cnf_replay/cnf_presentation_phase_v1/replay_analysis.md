# Frozen SAT Query Replay

Rows: 11384; duplicates replaced: 0; non-OK or mismatching rows: 8.

Candidate reductions compare a fresh candidate replay with a fresh replay of the mapping recorded by the originating live PDR run.

| Representation | Origin | Solver role | Candidate mapping | Traces | Complete pairs | Replay-time reduction | Conflict reduction | Decision reduction | Propagation reduction |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| aig | first/first | checker | encounter | 15 | 6 | -7.27% | +0.00% | +0.00% | +0.00% |
| aig | first/first | checker | numeric | 15 | 6 | -13.96% | +0.00% | +0.00% | +0.00% |
| aig | first/first | checker | reverse | 15 | 6 | -21.99% | +0.00% | +0.00% | +0.00% |
| aig | first/first | frame | encounter | 507 | 209 | -0.73% | +0.00% | +0.00% | +0.00% |
| aig | first/first | frame | numeric | 507 | 209 | +1.95% | -0.93% | +0.84% | +0.10% |
| aig | first/first | frame | reverse | 507 | 209 | +0.97% | +2.02% | +1.06% | -0.20% |
| aig | first/first | lift | encounter | 13 | 4 | +0.68% | +0.00% | +0.00% | +0.00% |
| aig | first/first | lift | numeric | 13 | 4 | +1.50% | -0.00% | +0.00% | +0.08% |
| aig | first/first | lift | reverse | 13 | 4 | +1.13% | +0.00% | +0.00% | +0.05% |
| aig | first/first | source | encounter | 13 | 4 | +0.10% | +0.00% | +0.00% | +0.00% |
| aig | first/first | source | numeric | 13 | 4 | +0.20% | +0.00% | +0.00% | +0.00% |
| aig | first/first | source | reverse | 13 | 4 | +0.00% | +0.00% | +0.00% | +0.00% |
| aig | numeric/numeric | checker | encounter | 15 | 7 | -46.88% | +0.00% | +0.00% | +0.00% |
| aig | numeric/numeric | checker | numeric | 15 | 7 | -13.25% | +0.00% | +0.00% | +0.00% |
| aig | numeric/numeric | checker | reverse | 15 | 7 | +14.02% | +0.00% | +0.00% | +0.00% |
| aig | numeric/numeric | frame | encounter | 444 | 264 | +0.08% | +2.16% | +0.61% | +1.27% |
| aig | numeric/numeric | frame | numeric | 444 | 264 | +0.76% | -2.20% | +1.04% | +0.85% |
| aig | numeric/numeric | frame | reverse | 444 | 264 | +2.44% | +3.54% | -0.16% | +1.02% |
| aig | numeric/numeric | lift | encounter | 13 | 5 | -2.43% | -0.02% | +0.00% | -0.22% |
| aig | numeric/numeric | lift | numeric | 13 | 5 | -22.37% | +0.00% | +0.00% | -23.11% |
| aig | numeric/numeric | lift | reverse | 13 | 5 | +2.50% | -0.02% | +0.00% | -0.22% |
| aig | numeric/numeric | source | encounter | 13 | 5 | -0.42% | +0.00% | +0.00% | +0.00% |
| aig | numeric/numeric | source | numeric | 13 | 5 | -0.29% | +0.00% | +0.00% | +0.00% |
| aig | numeric/numeric | source | reverse | 13 | 5 | -0.27% | +0.00% | +0.00% | +0.00% |
| xag | first/first | checker | encounter | 30 | 14 | -11.59% | +0.00% | +0.00% | +0.00% |
| xag | first/first | checker | numeric | 30 | 14 | -3.18% | +0.00% | +0.00% | +0.00% |
| xag | first/first | checker | reverse | 30 | 14 | -12.80% | +0.00% | +0.00% | +0.00% |
| xag | first/first | frame | encounter | 850 | 360 | -0.08% | +0.00% | +0.00% | +0.00% |
| xag | first/first | frame | numeric | 850 | 360 | +4.24% | +2.57% | -1.07% | -0.51% |
| xag | first/first | frame | reverse | 850 | 360 | +3.29% | +2.66% | -0.24% | -0.05% |
| xag | first/first | lift | encounter | 28 | 12 | -2.65% | +0.00% | +0.00% | +0.00% |
| xag | first/first | lift | numeric | 28 | 12 | -1.81% | -0.00% | +0.00% | +0.01% |
| xag | first/first | lift | reverse | 28 | 12 | -3.15% | +0.00% | +0.00% | -0.04% |
| xag | first/first | source | encounter | 28 | 12 | -3.75% | +0.00% | +0.00% | +0.00% |
| xag | first/first | source | numeric | 28 | 12 | -2.94% | +0.00% | +0.00% | +0.00% |
| xag | first/first | source | reverse | 28 | 12 | -5.95% | +0.00% | +0.00% | +0.00% |
| xag | numeric/numeric | checker | encounter | 30 | 13 | +7.86% | +0.00% | +0.00% | +0.00% |
| xag | numeric/numeric | checker | numeric | 30 | 13 | +11.84% | +0.00% | +0.00% | +0.00% |
| xag | numeric/numeric | checker | reverse | 30 | 13 | +15.25% | +0.00% | +0.00% | +0.00% |
| xag | numeric/numeric | frame | encounter | 789 | 285 | -0.62% | +5.40% | -0.77% | +1.04% |
| xag | numeric/numeric | frame | numeric | 789 | 285 | -2.15% | -3.51% | -1.01% | -0.86% |
| xag | numeric/numeric | frame | reverse | 789 | 285 | +4.55% | +5.88% | -0.79% | +1.78% |
| xag | numeric/numeric | lift | encounter | 28 | 11 | -2.32% | +0.03% | +0.00% | -0.01% |
| xag | numeric/numeric | lift | numeric | 28 | 11 | -2.61% | +0.03% | +0.00% | +0.01% |
| xag | numeric/numeric | lift | reverse | 28 | 11 | +0.69% | +0.05% | +0.00% | -0.02% |
| xag | numeric/numeric | source | encounter | 28 | 11 | +0.25% | +0.00% | +0.00% | +0.00% |
| xag | numeric/numeric | source | numeric | 28 | 11 | -0.44% | +0.00% | +0.00% | +0.00% |
| xag | numeric/numeric | source | reverse | 28 | 11 | -0.23% | +0.00% | +0.00% | +0.00% |

Replay status counts: {'OK': 11376, 'ERROR': 8}

