# MC hard-breakthrough screen

Candidate models: 331; completed strategies: 6.

| Strategy | Rows | Solved | SAFE | UNSAFE | Candidate-only | Baseline-only |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline` | 331 | 0 | 0 | 0 | 0 | 0 |
| `source-init` | 331 | 1 | 0 | 1 | 1 | 0 |
| `source-zero` | 331 | 0 | 0 | 0 | 0 | 0 |
| `source-random` | 331 | 0 | 0 | 0 | 0 | 0 |
| `first-phase` | 331 | 0 | 0 | 0 | 0 | 0 |
| `heuristic` | 331 | 1 | 1 | 0 | 1 | 0 |

## Candidate-only solves

| Strategy | Model | Family | Result | Seconds | Depth |
| --- | --- | --- | --- | ---: | ---: |
| `heuristic` | `2024__dijkstra-u_valuebound1` | `dijkstra` | SAFE | 176.06 | 5 |
| `source-init` | `2024__a07-p14` | `a` | UNSAFE | 1155.81 | 4 |

## Unsolved progress

- `source-init`: 18 models reached a materially deeper frame than baseline.
- `source-zero`: 13 models reached a materially deeper frame than baseline.
- `source-random`: 17 models reached a materially deeper frame than baseline.
- `first-phase`: 14 models reached a materially deeper frame than baseline.
- `heuristic`: 42 models reached a materially deeper frame than baseline.
- `heuristic`: 28 of the deeper-frame models also improved at least two convergence-normalized counters.
