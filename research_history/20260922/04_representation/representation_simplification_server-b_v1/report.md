# Representation / Simplification Report

Rows: 1296; solved-outcome conflicts: 0; timeout penalty: 1.50x.

All tables exclude cases where every compared configuration timed out or errored. Meaningful wins additionally require a fastest/slowest gap above 2 seconds.

## Representations under native

Complete pairs: 144; retained cases: 122; best penalized total: xag_native.

| Config | Solved | Penalized seconds | Wins | Wins >2s | Gap vs best |
|---|---:|---:|---:|---:|---:|
| aig_native | 120/144 | 2758.97 | 38 | 18 | 16.6% |
| xag_native | 122/144 | 2367.00 | 49 | 16 | best |
| lowered_native | 120/144 | 3131.34 | 35 | 15 | 32.3% |

## Representations under raw

Complete pairs: 144; retained cases: 123; best penalized total: xag_raw.

| Config | Solved | Penalized seconds | Wins | Wins >2s | Gap vs best |
|---|---:|---:|---:|---:|---:|
| aig_raw | 122/144 | 3047.43 | 40 | 17 | 9.9% |
| xag_raw | 122/144 | 2772.19 | 56 | 26 | best |
| lowered_raw | 122/144 | 3330.02 | 27 | 16 | 20.1% |

## Representations under precanonical

Complete pairs: 144; retained cases: 123; best penalized total: xag_precanonical.

| Config | Solved | Penalized seconds | Wins | Wins >2s | Gap vs best |
|---|---:|---:|---:|---:|---:|
| aig_precanonical | 122/144 | 3111.74 | 40 | 16 | 8.7% |
| xag_precanonical | 122/144 | 2862.29 | 43 | 20 | best |
| lowered_precanonical | 120/144 | 3239.06 | 40 | 20 | 13.2% |

## Preprocessing for aig

Complete pairs: 144; retained cases: 122; best penalized total: aig_raw.

| Config | Solved | Penalized seconds | Wins | Wins >2s | Gap vs best |
|---|---:|---:|---:|---:|---:|
| aig_native | 120/144 | 2758.97 | 40 | 24 | 6.2% |
| aig_raw | 122/144 | 2597.43 | 15 | 10 | best |
| aig_precanonical | 122/144 | 2661.74 | 67 | 31 | 2.5% |

## Preprocessing for xag

Complete pairs: 144; retained cases: 123; best penalized total: xag_raw.

| Config | Solved | Penalized seconds | Wins | Wins >2s | Gap vs best |
|---|---:|---:|---:|---:|---:|
| xag_native | 122/144 | 2817.00 | 34 | 17 | 1.6% |
| xag_raw | 122/144 | 2772.19 | 21 | 13 | best |
| xag_precanonical | 122/144 | 2862.29 | 68 | 38 | 3.3% |

## Preprocessing for lowered

Complete pairs: 144; retained cases: 122; best penalized total: lowered_precanonical.

| Config | Solved | Penalized seconds | Wins | Wins >2s | Gap vs best |
|---|---:|---:|---:|---:|---:|
| lowered_native | 120/144 | 3131.34 | 36 | 19 | 12.3% |
| lowered_raw | 122/144 | 2880.02 | 16 | 8 | 3.3% |
| lowered_precanonical | 120/144 | 2789.06 | 70 | 41 | best |

## Status Counts

- aig_native: {'SAFE': 94, 'UNSAFE': 26, 'TIMEOUT': 24}
- aig_precanonical: {'SAFE': 96, 'UNSAFE': 26, 'TIMEOUT': 22}
- aig_raw: {'SAFE': 96, 'UNSAFE': 26, 'TIMEOUT': 22}
- lowered_native: {'SAFE': 94, 'UNSAFE': 26, 'TIMEOUT': 24}
- lowered_precanonical: {'SAFE': 96, 'UNSAFE': 24, 'TIMEOUT': 24}
- lowered_raw: {'SAFE': 96, 'UNSAFE': 26, 'TIMEOUT': 22}
- xag_native: {'SAFE': 96, 'UNSAFE': 26, 'TIMEOUT': 22}
- xag_precanonical: {'SAFE': 95, 'UNSAFE': 27, 'TIMEOUT': 22}
- xag_raw: {'SAFE': 95, 'UNSAFE': 27, 'TIMEOUT': 22}
