# Blind conditional BVE width validation

Frozen models: 240; model-seed rows: 720.

## Aggregate

| Policy | w2 picks | Solved policy/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global w2 | 720 | 358/366 | 6/14 | 352 | 1.243 | 1.196 | 67/191 | 1.258 |
| Conditional bad-cone >= 30 | 288 | 363/366 | 1/4 | 362 | 1.057 | 1.000 | 28/62 | 1.102 |
| Extremes bad-cone = 0 or >= 100 | 288 | 370/366 | 4/0 | 366 | 1.059 | 1.000 | 27/59 | 0.944 |

## ric3_seed1030001_shard0_of_1

| Policy | w2 picks | Solved policy/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global w2 | 240 | 120/122 | 3/5 | 117 | 1.241 | 1.187 | 23/63 | 1.169 |
| Conditional bad-cone >= 30 | 96 | 122/122 | 1/1 | 121 | 1.071 | 1.000 | 10/21 | 1.049 |
| Extremes bad-cone = 0 or >= 100 | 96 | 124/122 | 2/0 | 122 | 1.041 | 1.000 | 11/17 | 0.925 |

## ric3_seed1040001_shard0_of_1

| Policy | w2 picks | Solved policy/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global w2 | 240 | 121/121 | 2/2 | 119 | 1.233 | 1.200 | 24/61 | 1.221 |
| Conditional bad-cone >= 30 | 96 | 120/121 | 0/1 | 120 | 1.044 | 1.000 | 10/19 | 1.105 |
| Extremes bad-cone = 0 or >= 100 | 96 | 122/121 | 1/0 | 121 | 1.049 | 1.000 | 10/18 | 0.973 |

## ric3_seed1050001_shard0_of_1

| Policy | w2 picks | Solved policy/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global w2 | 240 | 117/123 | 1/7 | 116 | 1.254 | 1.222 | 20/67 | 1.409 |
| Conditional bad-cone >= 30 | 96 | 121/123 | 0/2 | 121 | 1.057 | 1.000 | 8/22 | 1.163 |
| Extremes bad-cone = 0 or >= 100 | 96 | 124/123 | 1/0 | 123 | 1.085 | 1.000 | 6/24 | 0.938 |

## Bucket zero

| Policy | w2 picks | Solved policy/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global w2 | 144 | 66/63 | 3/0 | 63 | 1.225 | 1.347 | 10/36 | 0.816 |
| Conditional bad-cone >= 30 | 0 | 63/63 | 0/0 | 63 | 1.000 | 1.000 | 0/0 | 1.000 |
| Extremes bad-cone = 0 or >= 100 | 144 | 66/63 | 3/0 | 63 | 1.225 | 1.347 | 10/36 | 0.816 |

## Bucket 1-9

| Policy | w2 picks | Solved policy/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global w2 | 144 | 67/72 | 1/6 | 66 | 1.384 | 1.301 | 8/31 | 1.312 |
| Conditional bad-cone >= 30 | 0 | 72/72 | 0/0 | 72 | 1.000 | 1.000 | 0/0 | 1.000 |
| Extremes bad-cone = 0 or >= 100 | 0 | 72/72 | 0/0 | 72 | 1.000 | 1.000 | 0/0 | 1.000 |

## Bucket 10-29

| Policy | w2 picks | Solved policy/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global w2 | 144 | 105/108 | 1/4 | 104 | 1.236 | 1.188 | 21/62 | 1.324 |
| Conditional bad-cone >= 30 | 0 | 108/108 | 0/0 | 108 | 1.000 | 1.000 | 0/0 | 1.000 |
| Extremes bad-cone = 0 or >= 100 | 0 | 108/108 | 0/0 | 108 | 1.000 | 1.000 | 0/0 | 1.000 |

## Bucket 30-99

| Policy | w2 picks | Solved policy/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global w2 | 144 | 68/72 | 0/4 | 68 | 1.196 | 1.145 | 11/39 | 1.930 |
| Conditional bad-cone >= 30 | 144 | 68/72 | 0/4 | 68 | 1.196 | 1.145 | 11/39 | 1.930 |
| Extremes bad-cone = 0 or >= 100 | 0 | 72/72 | 0/0 | 72 | 1.000 | 1.000 | 0/0 | 1.000 |

## Bucket 100+

| Policy | w2 picks | Solved policy/w0 | Only/lost | Common | Geo | Median | W/L >2s | PAR-1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global w2 | 144 | 52/51 | 1/0 | 51 | 1.171 | 1.187 | 17/23 | 0.773 |
| Conditional bad-cone >= 30 | 144 | 52/51 | 1/0 | 51 | 1.171 | 1.187 | 17/23 | 0.773 |
| Extremes bad-cone = 0 or >= 100 | 144 | 52/51 | 1/0 | 51 | 1.171 | 1.187 | 17/23 | 0.773 |
