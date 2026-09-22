# Translation/Lift Presentation Campaign

Rows: 7020; duplicates replaced: 0; timeout penalty: 1.50x; small-difference threshold: 2.00s.

## aig_canonical-cnf

Complete model/run cells: 585; retained non-all-timeout: 343.

| Rank | Translation | Lift | Solved | Penalized s | Gap vs best | Wins >2s |
|---:|---|---|---:|---:|---:|---:|
| 1 | numeric | first | 342/343 | 8642.25 | +0.00% | 49 |
| 2 | first | numeric | 340/343 | 9943.32 | +15.05% | 51 |
| 3 | numeric | numeric | 339/343 | 9982.01 | +15.50% | 57 |
| 4 | first | first | 336/343 | 11398.13 | +31.89% | 51 |

### Versus first/first

| Candidate | Retained | Joint | Base/candidate only | Penalized reduction | Joint reduction | Median base/candidate | Wins >2s (base/candidate) |
|---|---:|---:|---:|---:|---:|---:|---:|
| numeric/first | 342 | 336 | 0/6 | +25.17% | +8.12% | 1.010 | 68/74 |
| first/numeric | 340 | 336 | 0/4 | +14.48% | +2.24% | 1.011 | 57/67 |
| numeric/numeric | 339 | 336 | 0/3 | +14.75% | +5.21% | 1.014 | 72/80 |

### Per-run penalized reduction versus first/first

| Run | numeric/first | first/numeric | numeric/numeric |
|---:|---:|---:|---:|
| 4 | +32.15% | +10.57% | +16.83% |
| 5 | +26.05% | +9.11% | +12.56% |
| 6 | +17.35% | +22.59% | +14.88% |

Status counts: {'SAFE': 1131, 'UNSAFE': 226, 'TIMEOUT': 983}

## xag_canonical-cnf

Complete model/run cells: 1170; retained non-all-timeout: 686.

| Rank | Translation | Lift | Solved | Penalized s | Gap vs best | Wins >2s |
|---:|---|---|---:|---:|---:|---:|
| 1 | numeric | first | 678/686 | 20430.29 | +0.00% | 80 |
| 2 | first | first | 674/686 | 21021.12 | +2.89% | 105 |
| 3 | first | numeric | 675/686 | 21280.53 | +4.16% | 110 |
| 4 | numeric | numeric | 674/686 | 21589.29 | +5.67% | 113 |

### Versus first/first

| Candidate | Retained | Joint | Base/candidate only | Penalized reduction | Joint reduction | Median base/candidate | Wins >2s (base/candidate) |
|---|---:|---:|---:|---:|---:|---:|---:|
| numeric/first | 682 | 670 | 4/8 | +3.07% | -2.70% | 0.981 | 155/119 |
| first/numeric | 679 | 670 | 4/5 | -1.45% | -0.03% | 1.014 | 104/117 |
| numeric/numeric | 680 | 668 | 6/6 | -3.10% | +1.08% | 1.006 | 146/139 |

### Per-run penalized reduction versus first/first

| Run | numeric/first | first/numeric | numeric/numeric |
|---:|---:|---:|---:|
| 1 | +14.68% | +10.43% | +7.38% |
| 2 | -13.86% | -16.93% | -14.88% |
| 3 | -20.01% | -16.02% | -25.46% |
| 4 | -10.76% | -9.04% | +5.81% |
| 5 | +22.79% | +16.57% | +2.93% |
| 6 | +12.66% | +0.32% | +1.48% |

Status counts: {'SAFE': 2233, 'UNSAFE': 468, 'TIMEOUT': 1979}

