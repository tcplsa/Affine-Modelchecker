# Full affine selector and dynamic Gaussian gate

Two independent fixed seeds; all configurations are single-lane and use
the same per-model timeout. PAR-1 assigns the timeout to every unsolved run.

## seed998101

| Configuration | Solved | PAR-1 (s) | GM ratio vs CaDiCaL (common n) |
| --- | ---: | ---: | ---: |
| `cadical` | 193/375 | 113910.32 | 1.000 (193) |
| `cmsat_no_gauss` | 206/375 | 103562.07 | 0.827 (186) |
| `cmsat_gauss` | 306/375 | 47647.66 | 0.702 (184) |
| `cmsat_dynamic` | 298/375 | 49679.38 | 0.739 (186) |
| `two_stage_static` | 316/375 | 41422.69 | 0.476 (193) |
| `two_stage_auto` | 316/375 | 41381.55 | 0.471 (193) |

## seed998102

| Configuration | Solved | PAR-1 (s) | GM ratio vs CaDiCaL (common n) |
| --- | ---: | ---: | ---: |
| `cadical` | 193/375 | 114013.55 | 1.000 (193) |
| `cmsat_no_gauss` | 209/375 | 102414.88 | 0.963 (189) |
| `cmsat_gauss` | 310/375 | 47811.50 | 0.897 (186) |
| `cmsat_dynamic` | 302/375 | 48170.14 | 0.809 (189) |
| `two_stage_static` | 314/375 | 42634.41 | 0.519 (193) |
| `two_stage_auto` | 314/375 | 42616.46 | 0.509 (193) |

## Both seeds pooled as observations

| Configuration | Solved | PAR-1 (s) | GM ratio vs CaDiCaL (common n) |
| --- | ---: | ---: | ---: |
| `cadical` | 386/750 | 227923.87 | 1.000 (386) |
| `cmsat_no_gauss` | 415/750 | 205976.95 | 0.893 (375) |
| `cmsat_gauss` | 616/750 | 95459.15 | 0.794 (370) |
| `cmsat_dynamic` | 600/750 | 97849.53 | 0.773 (375) |
| `two_stage_static` | 630/750 | 84057.10 | 0.497 (386) |
| `two_stage_auto` | 630/750 | 83998.01 | 0.490 (386) |

## Scope and family coverage

| Scope/family | Observations | CaDiCaL | Gaussian | Dynamic | Static auto | Two-stage auto |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| boundary/adder_equiv | 36 | 36 | 36 | 36 | 36 | 36 |
| boundary/aes_linear_equiv | 24 | 24 | 24 | 24 | 24 | 24 |
| boundary/affine_phase_sync | 96 | 8 | 52 | 31 | 64 | 64 |
| boundary/arx_equiv | 36 | 36 | 36 | 36 | 36 | 36 |
| boundary/crc_equiv | 36 | 36 | 36 | 36 | 36 | 36 |
| boundary/crc_frame_residue | 36 | 36 | 26 | 31 | 36 | 36 |
| boundary/keccak_linear_equiv | 24 | 22 | 24 | 24 | 24 | 24 |
| boundary/mac_equiv | 30 | 24 | 18 | 18 | 24 | 24 |
| target/crc_frame_align | 176 | 22 | 112 | 112 | 108 | 108 |
| target/crc_frame_lock | 82 | 24 | 82 | 82 | 78 | 78 |
| target/lfsr_jump_equiv | 54 | 24 | 54 | 54 | 44 | 44 |
| target/scrambler_equiv | 44 | 28 | 40 | 40 | 44 | 44 |
| target/scrambler_recovery | 32 | 32 | 32 | 32 | 32 | 32 |
| target/syndrome_equiv | 44 | 34 | 44 | 44 | 44 | 44 |

## Incremental coverage and decisions

- `cmsat_dynamic` versus `cmsat_gauss`: +5/-21 solved observations.
- `two_stage_static` versus `cadical`: +244/-0 solved observations.
- `two_stage_auto` versus `cadical`: +244/-0 solved observations.
- `two_stage_auto` versus `two_stage_static`: +0/-0 solved observations.
- Two-stage selector choices: `{'fallback': 146, 'cadical-hints': 164, 'cmsat-gauss-guarded-summary': 302, '': 76, 'cmsat-gauss-summary': 62}`.
- Dynamic Gaussian shutdowns in two-stage auto: 0/750 observations.

## Cross-seed coverage stability

| Configuration | Solved in both seeds | Solved in either seed | Seed disagreement |
| --- | ---: | ---: | ---: |
| `cadical` | 193 | 193 | 0 |
| `cmsat_no_gauss` | 205 | 210 | 5 |
| `cmsat_gauss` | 301 | 315 | 14 |
| `cmsat_dynamic` | 297 | 303 | 6 |
| `two_stage_static` | 312 | 318 | 6 |
| `two_stage_auto` | 312 | 318 | 6 |
