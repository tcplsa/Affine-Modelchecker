# Blind conditional BVE width validation

Frozen models: 150; model-seed rows: 450.

## Aggregate

| Policy | w2 picks | Solved policy/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global w2 | 450 | 205/215 | 6/16 | 199 | 1.197 | 1.194 | 36/117 | 1.307 |
| Conditional bad-cone >= 30 | 180 | 210/215 | 2/7 | 208 | 1.113 | 1.000 | 13/49 | 1.182 |
| Extremes bad-cone = 0 or >= 100 | 180 | 212/215 | 3/6 | 209 | 1.107 | 1.000 | 10/38 | 1.135 |

## ric3_seed1060001_shard0_of_1

| Policy | w2 picks | Solved policy/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global w2 | 150 | 67/69 | 3/5 | 64 | 1.162 | 1.146 | 12/36 | 1.282 |
| Conditional bad-cone >= 30 | 60 | 68/69 | 1/2 | 67 | 1.061 | 1.000 | 6/14 | 1.148 |
| Extremes bad-cone = 0 or >= 100 | 60 | 67/69 | 0/2 | 67 | 1.067 | 1.000 | 4/11 | 1.243 |

## ric3_seed1070001_shard0_of_1

| Policy | w2 picks | Solved policy/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global w2 | 150 | 68/73 | 1/6 | 67 | 1.133 | 1.194 | 11/41 | 1.334 |
| Conditional bad-cone >= 30 | 60 | 70/73 | 0/3 | 70 | 1.089 | 1.000 | 4/18 | 1.238 |
| Extremes bad-cone = 0 or >= 100 | 60 | 72/73 | 1/2 | 71 | 1.086 | 1.000 | 2/15 | 1.132 |

## ric3_seed1080001_shard0_of_1

| Policy | w2 picks | Solved policy/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global w2 | 150 | 70/73 | 2/5 | 68 | 1.298 | 1.227 | 13/40 | 1.304 |
| Conditional bad-cone >= 30 | 60 | 72/73 | 1/2 | 71 | 1.189 | 1.000 | 3/17 | 1.156 |
| Extremes bad-cone = 0 or >= 100 | 60 | 73/73 | 2/2 | 71 | 1.169 | 1.000 | 4/12 | 1.071 |

## Bucket zero

| Policy | w2 picks | Solved policy/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global w2 | 90 | 32/34 | 2/4 | 30 | 1.128 | 1.061 | 5/13 | 1.246 |
| Conditional bad-cone >= 30 | 0 | 34/34 | 0/0 | 34 | 1.000 | 1.000 | 0/0 | 1.000 |
| Extremes bad-cone = 0 or >= 100 | 90 | 32/34 | 2/4 | 30 | 1.128 | 1.061 | 5/13 | 1.246 |

## Bucket 1-9

| Policy | w2 picks | Solved policy/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global w2 | 90 | 26/28 | 0/2 | 26 | 1.264 | 1.252 | 5/21 | 1.442 |
| Conditional bad-cone >= 30 | 0 | 28/28 | 0/0 | 28 | 1.000 | 1.000 | 0/0 | 1.000 |
| Extremes bad-cone = 0 or >= 100 | 0 | 28/28 | 0/0 | 28 | 1.000 | 1.000 | 0/0 | 1.000 |

## Bucket 10-29

| Policy | w2 picks | Solved policy/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global w2 | 90 | 54/55 | 2/3 | 52 | 1.076 | 1.203 | 13/34 | 1.029 |
| Conditional bad-cone >= 30 | 0 | 55/55 | 0/0 | 55 | 1.000 | 1.000 | 0/0 | 1.000 |
| Extremes bad-cone = 0 or >= 100 | 0 | 55/55 | 0/0 | 55 | 1.000 | 1.000 | 0/0 | 1.000 |

## Bucket 30-99

| Policy | w2 picks | Solved policy/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global w2 | 90 | 49/53 | 1/5 | 48 | 1.099 | 1.168 | 8/24 | 1.424 |
| Conditional bad-cone >= 30 | 90 | 49/53 | 1/5 | 48 | 1.099 | 1.168 | 8/24 | 1.424 |
| Extremes bad-cone = 0 or >= 100 | 0 | 53/53 | 0/0 | 53 | 1.000 | 1.000 | 0/0 | 1.000 |

## Bucket 100+

| Policy | w2 picks | Solved policy/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global w2 | 90 | 44/45 | 1/2 | 43 | 1.509 | 1.341 | 5/25 | 2.145 |
| Conditional bad-cone >= 30 | 90 | 44/45 | 1/2 | 43 | 1.509 | 1.341 | 5/25 | 2.145 |
| Extremes bad-cone = 0 or >= 100 | 90 | 44/45 | 1/2 | 43 | 1.509 | 1.341 | 5/25 | 2.145 |
