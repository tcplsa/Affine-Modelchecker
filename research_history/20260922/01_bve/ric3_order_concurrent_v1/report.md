# Concurrent rIC3 BVE-order validation

Candidate: Native product-sum-high. Reference: Native legacy. Both four replicas and launched concurrently per model.

Models: 556; model-seed rows: 1668; outcome conflicts: 0.
Model-clustered 95% bootstrap interval for the common-solve geometric ratio: [0.950, 0.995].

## Aggregate and seeds

| Cohort | Rows | Solved candidate/reference | Only/lost | Common | Geo (model CI) | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Aggregate | 1668 | 1486/1486 | 4/4 | 1482 | 0.972 [0.950, 0.995] | 0.971 | 93/80 | 0.955 |
| seed1110001 | 556 | 494/494 | 2/2 | 492 | 0.962 [0.924, 1.000] | 0.970 | 29/26 | 0.908 |
| seed1120001 | 556 | 495/496 | 1/2 | 494 | 0.960 [0.927, 0.992] | 0.966 | 36/26 | 1.006 |
| seed1130001 | 556 | 497/496 | 1/0 | 496 | 0.995 [0.966, 1.024] | 0.980 | 28/28 | 0.951 |

## Years

| Cohort | Rows | Solved candidate/reference | Only/lost | Common | Geo (model CI) | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 300 | 267/267 | 0/0 | 267 | 0.922 [0.874, 0.967] | 0.961 | 20/12 | 0.758 |
| 2017 | 264 | 228/228 | 0/0 | 228 | 0.981 [0.937, 1.028] | 0.970 | 14/7 | 1.054 |
| 2019 | 279 | 258/259 | 0/1 | 258 | 0.982 [0.943, 1.026] | 0.973 | 12/11 | 1.169 |
| 2020 | 273 | 247/248 | 1/2 | 246 | 0.966 [0.926, 1.011] | 0.971 | 7/11 | 1.242 |
| 2024 | 252 | 216/217 | 0/1 | 216 | 1.015 [0.927, 1.103] | 0.972 | 17/26 | 1.497 |
| 2025 | 300 | 270/267 | 3/0 | 267 | 0.978 [0.910, 1.042] | 0.973 | 23/13 | 0.244 |

## Historical tiers

| Cohort | Rows | Solved candidate/reference | Only/lost | Common | Geo (model CI) | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| trivial | 297 | 297/297 | 0/0 | 297 | 0.983 [0.943, 1.023] | 0.990 | 0/0 | 0.993 |
| fast | 360 | 360/360 | 0/0 | 360 | 0.953 [0.925, 0.980] | 0.958 | 6/0 | 0.850 |
| medium | 360 | 357/357 | 0/0 | 357 | 0.996 [0.960, 1.034] | 0.971 | 12/20 | 1.038 |
| slow | 291 | 288/288 | 0/0 | 288 | 0.983 [0.931, 1.042] | 0.968 | 22/16 | 1.098 |
| timeout | 360 | 184/184 | 4/4 | 180 | 0.930 [0.816, 1.046] | 0.980 | 53/44 | 0.942 |

## Outcomes

| Cohort | Rows | Solved candidate/reference | Only/lost | Common | Geo (model CI) | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SAFE | 1224 | 1224/1221 | 3/0 | 1221 | 0.968 [0.945, 0.992] | 0.968 | 56/50 | 0.601 |
| UNSAFE | 266 | 262/265 | 1/4 | 261 | 0.990 [0.920, 1.057] | 0.982 | 37/30 | 1.343 |
