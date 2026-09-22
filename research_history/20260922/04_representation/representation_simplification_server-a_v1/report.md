# Representation / Simplification Report

Rows: 1296; solved-outcome conflicts: 0; timeout penalty: 1.50x.

All tables exclude cases where every compared configuration timed out or errored. Meaningful wins additionally require a fastest/slowest gap above 2 seconds.

## Representations under native

Complete pairs: 144; retained cases: 110; best penalized total: aig_native.

| Config | Solved | Penalized seconds | Wins | Wins >2s | Gap vs best |
|---|---:|---:|---:|---:|---:|
| aig_native | 110/144 | 1281.43 | 44 | 19 | best |
| xag_native | 110/144 | 1404.28 | 52 | 22 | 9.6% |
| lowered_native | 108/144 | 2037.10 | 14 | 8 | 59.0% |

## Representations under raw

Complete pairs: 144; retained cases: 110; best penalized total: xag_raw.

| Config | Solved | Penalized seconds | Wins | Wins >2s | Gap vs best |
|---|---:|---:|---:|---:|---:|
| aig_raw | 110/144 | 2084.39 | 33 | 16 | 13.3% |
| xag_raw | 110/144 | 1840.28 | 50 | 29 | best |
| lowered_raw | 108/144 | 2708.21 | 27 | 12 | 47.2% |

## Representations under precanonical

Complete pairs: 144; retained cases: 108; best penalized total: xag_precanonical.

| Config | Solved | Penalized seconds | Wins | Wins >2s | Gap vs best |
|---|---:|---:|---:|---:|---:|
| aig_precanonical | 108/144 | 1041.54 | 36 | 17 | 1.5% |
| xag_precanonical | 108/144 | 1026.59 | 41 | 17 | best |
| lowered_precanonical | 108/144 | 1073.78 | 31 | 12 | 4.6% |

## Preprocessing for aig

Complete pairs: 144; retained cases: 110; best penalized total: aig_native.

| Config | Solved | Penalized seconds | Wins | Wins >2s | Gap vs best |
|---|---:|---:|---:|---:|---:|
| aig_native | 110/144 | 1281.43 | 43 | 27 | best |
| aig_raw | 110/144 | 2084.39 | 16 | 9 | 62.7% |
| aig_precanonical | 108/144 | 1941.54 | 51 | 26 | 51.5% |

## Preprocessing for xag

Complete pairs: 144; retained cases: 110; best penalized total: xag_native.

| Config | Solved | Penalized seconds | Wins | Wins >2s | Gap vs best |
|---|---:|---:|---:|---:|---:|
| xag_native | 110/144 | 1404.28 | 30 | 17 | best |
| xag_raw | 110/144 | 1840.28 | 20 | 8 | 31.0% |
| xag_precanonical | 108/144 | 1926.59 | 60 | 28 | 37.2% |

## Preprocessing for lowered

Complete pairs: 144; retained cases: 108; best penalized total: lowered_precanonical.

| Config | Solved | Penalized seconds | Wins | Wins >2s | Gap vs best |
|---|---:|---:|---:|---:|---:|
| lowered_native | 108/144 | 1137.10 | 35 | 20 | 5.9% |
| lowered_raw | 108/144 | 1808.21 | 15 | 6 | 68.4% |
| lowered_precanonical | 108/144 | 1073.78 | 58 | 32 | best |

## Status Counts

- aig_native: {'SAFE': 78, 'UNSAFE': 32, 'TIMEOUT': 34}
- aig_precanonical: {'SAFE': 78, 'UNSAFE': 30, 'TIMEOUT': 36}
- aig_raw: {'SAFE': 78, 'UNSAFE': 32, 'TIMEOUT': 34}
- lowered_native: {'SAFE': 78, 'UNSAFE': 30, 'TIMEOUT': 36}
- lowered_precanonical: {'SAFE': 78, 'UNSAFE': 30, 'TIMEOUT': 36}
- lowered_raw: {'SAFE': 78, 'UNSAFE': 30, 'TIMEOUT': 36}
- xag_native: {'SAFE': 78, 'UNSAFE': 32, 'TIMEOUT': 34}
- xag_precanonical: {'SAFE': 78, 'UNSAFE': 30, 'TIMEOUT': 36}
- xag_raw: {'SAFE': 78, 'UNSAFE': 32, 'TIMEOUT': 34}
