# MC XAG product-sum-high concurrent confirmation

Observations: 1668; models: 556; seed blocks: 3; outcome conflicts: 0.

MC calls the candidate `sum-high`; it orders BVE pivots by `(positive*negative, positive+negative, -variable_id)`, the same fill-aware product-sum-high principle transferred to rIC3. Both configurations use four forward-XAG lanes with matched explicit seeds and are launched concurrently within each model.

## Aggregate

| Group | Observations | Solved sum-high/legacy | Only/lost | Common | Geo (cluster 95% CI) | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 1668 | 1439/1445 | 3/9 | 1436 | 0.958 [0.940, 0.977] | 0.947 | 206/137 | 1.266 |

## By seed block

| Group | Observations | Solved sum-high/legacy | Only/lost | Common | Geo (cluster 95% CI) | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1260001 | 556 | 480/481 | 2/3 | 478 | 0.948 [0.923, 0.975] | 0.943 | 75/41 | 1.180 |
| 1270001 | 556 | 478/482 | 0/4 | 478 | 0.957 [0.929, 0.982] | 0.946 | 66/43 | 1.695 |
| 1280001 | 556 | 481/482 | 1/2 | 480 | 0.969 [0.941, 1.000] | 0.954 | 65/53 | 1.045 |

## By year

| Group | Observations | Solved sum-high/legacy | Only/lost | Common | Geo (cluster 95% CI) | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 300 | 255/255 | 0/0 | 255 | 0.936 [0.899, 0.976] | 0.943 | 44/20 | 0.990 |
| 2017 | 264 | 223/223 | 1/1 | 222 | 0.956 [0.914, 0.991] | 0.938 | 22/16 | 1.124 |
| 2019 | 279 | 247/247 | 1/1 | 246 | 0.984 [0.929, 1.054] | 0.949 | 42/25 | 0.892 |
| 2020 | 273 | 235/238 | 0/3 | 235 | 0.954 [0.922, 0.988] | 0.939 | 37/20 | 1.515 |
| 2024 | 252 | 216/216 | 0/0 | 216 | 0.938 [0.888, 0.987] | 0.951 | 23/20 | 0.885 |
| 2025 | 300 | 263/266 | 1/4 | 262 | 0.978 [0.924, 1.057] | 0.960 | 38/36 | 1.937 |

## By historical tier

| Group | Observations | Solved sum-high/legacy | Only/lost | Common | Geo (cluster 95% CI) | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| trivial | 297 | 297/297 | 0/0 | 297 | 0.962 [0.930, 0.994] | 0.959 | 0/0 | 0.962 |
| fast | 360 | 360/360 | 0/0 | 360 | 0.949 [0.920, 0.976] | 0.947 | 0/0 | 0.938 |
| medium | 360 | 360/360 | 0/0 | 360 | 0.957 [0.929, 0.985] | 0.939 | 25/22 | 0.915 |
| slow | 291 | 291/291 | 0/0 | 291 | 0.935 [0.882, 1.002] | 0.924 | 121/59 | 1.359 |
| timeout | 360 | 131/137 | 3/9 | 128 | 1.035 [0.928, 1.169] | 0.987 | 60/56 | 1.266 |

## By outcome

| Group | Observations | Solved sum-high/legacy | Only/lost | Common | Geo (cluster 95% CI) | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SAFE | 1199 | 1190/1196 | 3/9 | 1187 | 0.951 [0.934, 0.966] | 0.947 | 147/95 | 1.236 |
| UNSAFE | 249 | 249/249 | 0/0 | 249 | 0.993 [0.922, 1.084] | 0.947 | 59/42 | 1.371 |

## Outcome-stratified PDR observables

### SAFE raw counters (1187 common solves)

Ratios use observations solved by both configurations. The geometric ratio uses pairs in which both counters are positive; the summed ratio retains zero counts and is tail-sensitive.

| Observable | Positive pairs | Geo ratio (95% family-cluster CI) | Median | Summed-count ratio |
|---|---:|---:|---:|---:|
| SAT queries | 1187 | 0.975 [0.947, 0.996] | 1.000 | 0.883 |
| CTIs | 1010 | 0.988 [0.962, 1.012] | 1.000 | 0.972 |
| MIC calls | 1010 | 0.983 [0.958, 1.005] | 1.000 | 0.953 |
| Push calls | 1010 | 0.972 [0.938, 1.004] | 1.000 | 0.842 |
| PDR depth | 1187 | 0.986 [0.969, 1.003] | 1.000 | 0.937 |

### SAFE normalized counters

| Normalized observable | Positive pairs | Geo ratio (95% family-cluster CI) | Median |
|---|---:|---:|---:|
| CTIs / query | 1010 | 1.019 [1.000, 1.043] | 1.000 |
| MIC calls / query | 1010 | 1.014 [1.000, 1.033] | 1.000 |
| Generalize calls / query | 1010 | 1.017 [1.001, 1.039] | 1.000 |
| Push calls / query | 1010 | 1.002 [0.984, 1.024] | 1.000 |
| Queries / PDR depth | 1187 | 0.989 [0.967, 1.006] | 1.000 |
| Push calls / PDR depth | 1010 | 0.989 [0.964, 1.014] | 1.000 |

### UNSAFE raw counters (249 common solves)

Ratios use observations solved by both configurations. The geometric ratio uses pairs in which both counters are positive; the summed ratio retains zero counts and is tail-sensitive.

| Observable | Positive pairs | Geo ratio (95% family-cluster CI) | Median | Summed-count ratio |
|---|---:|---:|---:|---:|
| SAT queries | 249 | 1.018 [0.925, 1.119] | 1.000 | 0.958 |
| CTIs | 234 | 1.012 [0.942, 1.085] | 1.000 | 0.993 |
| MIC calls | 222 | 1.002 [0.922, 1.082] | 1.000 | 0.980 |
| Push calls | 222 | 0.989 [0.901, 1.075] | 0.997 | 0.872 |
| PDR depth | 234 | 1.020 [0.997, 1.047] | 1.000 | 0.996 |

### UNSAFE normalized counters

| Normalized observable | Positive pairs | Geo ratio (95% family-cluster CI) | Median |
|---|---:|---:|---:|
| CTIs / query | 234 | 0.993 [0.943, 1.038] | 1.000 |
| MIC calls / query | 222 | 1.006 [0.985, 1.031] | 0.996 |
| Generalize calls / query | 222 | 1.012 [0.983, 1.047] | 0.999 |
| Push calls / query | 222 | 0.992 [0.968, 1.018] | 0.995 |
| Queries / PDR depth | 234 | 0.999 [0.906, 1.100] | 1.000 |
| Push calls / PDR depth | 222 | 0.968 [0.894, 1.042] | 0.986 |

## Coverage differences

| Model | Seed | Tier | Outcome | Sum-high | Legacy |
|---|---:|---|---|---:|---:|
| 2017__cmudme2 | 1260001 | timeout | SAFE | 1303.249s | TIMEOUT |
| 2019__synapse.7.prop1-func-interl | 1260001 | timeout | SAFE | 1663.516s | TIMEOUT |
| 2020__rushhour.4.prop1-func-interl | 1260001 | timeout | SAFE | TIMEOUT | 1529.512s |
| 2025__benchmarks_output_btor2_example_494_miter_miter | 1260001 | timeout | SAFE | TIMEOUT | 210.493s |
| 2025__sqrt1-ll_valuebound100 | 1260001 | timeout | SAFE | TIMEOUT | 771.847s |
| 2017__cmudme2 | 1270001 | timeout | SAFE | TIMEOUT | 412.358s |
| 2019__synapse.7.prop1-func-interl | 1270001 | timeout | SAFE | TIMEOUT | 1422.703s |
| 2020__rushhour.4.prop1-func-interl | 1270001 | timeout | SAFE | TIMEOUT | 592.071s |
| 2025__benchmarks_output_btor2_example_494_miter_miter | 1270001 | timeout | SAFE | TIMEOUT | 82.611s |
| 2020__rushhour.4.prop1-func-interl | 1280001 | timeout | SAFE | TIMEOUT | 1797.671s |
| 2025__benchmarks_output_btor2_example_494_miter_miter | 1280001 | timeout | SAFE | TIMEOUT | 219.359s |
| 2025__rocket_1937 | 1280001 | timeout | SAFE | 359.351s | TIMEOUT |
