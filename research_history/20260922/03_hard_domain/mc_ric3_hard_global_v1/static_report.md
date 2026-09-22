# Global atlas of stock-rIC3-3600 hard models

Models: 590; families: 217.

## Structural coverage

| Structural class | Models |
| --- | ---: |
| `mixed-control-data` | 354 |
| `affine-heavy` | 170 |
| `state-heavy` | 49 |
| `very-large` | 17 |

## Largest families

| Family | N | Structure | Latches | ANDs | Next-XOR density | MC-AIG | XAG-only increment |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| `oski` | 81 | `mixed-control-data` | 16357 | 306471 | 0.044 | 0 | 0 |
| `yosyshq_appnote_` | 50 | `state-heavy` | 189026 | 903673 | 0.023 | 0 | 0 |
| `cal` | 27 | `affine-heavy` | 1009 | 94149 | 0.180 | 0 | 0 |
| `arbitrated_top_n` | 25 | `mixed-control-data` | 16524 | 84636 | 0.004 | 0 | 0 |
| `picorv` | 24 | `mixed-control-data` | 3485 | 54078 | 0.024 | 0 | 0 |
| `Problem` | 23 | `affine-heavy` | 229 | 1126553 | 0.210 | 0 | 1 |
| `oc` | 19 | `mixed-control-data` | 934 | 10788 | 0.024 | 0 | 0 |
| `intel` | 14 | `affine-heavy` | 5474 | 68189 | 0.130 | 2 | 0 |
| `circular_pointer_top_w` | 12 | `mixed-control-data` | 4229 | 30266 | 0.004 | 0 | 0 |
| `mul` | 12 | `affine-heavy` | 279 | 17228 | 0.241 | 1 | 0 |
| `zipcpu` | 12 | `affine-heavy` | 793 | 4622 | 0.094 | 4 | 2 |
| `vgasim_imgfifo` | 11 | `affine-heavy` | 880 | 4529 | 0.131 | 0 | 0 |
| `level_` | 9 | `mixed-control-data` | 227 | 12840 | 0.000 | 0 | 0 |
| `pals_lcr` | 9 | `affine-heavy` | 482 | 1574336 | 0.204 | 0 | 0 |
| `a` | 8 | `mixed-control-data` | 41262 | 266760 | 0.000 | 0 | 0 |
| `VexRiscv` | 7 | `mixed-control-data` | 2397 | 17124 | 0.031 | 0 | 0 |
| `rast` | 7 | `mixed-control-data` | 442 | 4259 | 0.021 | 0 | 0 |
| `pgm_protocol` | 5 | `mixed-control-data` | 1032 | 19565 | 0.039 | 0 | 0 |
| `shift_register_top_w` | 5 | `mixed-control-data` | 8275 | 66711 | 0.001 | 0 | 0 |
| `benchmarks_initial_output_btor` | 4 | `affine-heavy` | 5812 | 69876 | 0.166 | 0 | 0 |
| `rocket_` | 4 | `mixed-control-data` | 74179 | 483726 | 0.005 | 0 | 0 |
| `beemextnc` | 3 | `affine-heavy` | 316 | 5800 | 0.083 | 0 | 0 |
| `beemfwt` | 3 | `mixed-control-data` | 3046 | 104771 | 0.076 | 0 | 0 |
| `benchmarks_output_btor` | 3 | `affine-heavy` | 603 | 6200 | 0.190 | 2 | 0 |
| `bob` | 3 | `mixed-control-data` | 1994 | 27175 | 0.007 | 1 | 0 |
| `lcm` | 3 | `affine-heavy` | 229 | 19024 | 0.246 | 0 | 0 |
| `ponylink` | 3 | `mixed-control-data` | 2868 | 20161 | 0.026 | 0 | 0 |
| `ridecore` | 3 | `mixed-control-data` | 83247 | 545028 | 0.022 | 0 | 0 |
| `zipversa_composecrc_prf` | 3 | `affine-heavy` | 315 | 2763 | 0.175 | 0 | 0 |
| `beemcmbrdg` | 2 | `mixed-control-data` | 306 | 7154 | 0.057 | 0 | 0 |
| `beempgsol` | 2 | `mixed-control-data` | 306 | 7164 | 0.064 | 1 | 0 |
| `bobsm` | 2 | `mixed-control-data` | 1303 | 10345 | 0.013 | 0 | 0 |
| `gcd_` | 2 | `affine-heavy` | 129 | 395813 | 0.160 | 1 | 0 |
| `gcd_bit_width_large` | 2 | `affine-heavy` | 155 | 1804 | 0.106 | 0 | 0 |
| `nusmvdme` | 2 | `mixed-control-data` | 323 | 2071 | 0.028 | 0 | 0 |
| `pals_opt` | 2 | `affine-heavy` | 509 | 10430 | 0.096 | 0 | 0 |
| `prodbin` | 2 | `affine-heavy` | 293 | 32982 | 0.244 | 0 | 0 |
| `shift` | 2 | `affine-heavy` | 27 | 145 | 0.180 | 0 | 0 |
| `vis_arrays_bufferAlloc` | 2 | `mixed-control-data` | 27 | 292 | 0.049 | 0 | 0 |
| `6s10` | 1 | `mixed-control-data` | 598 | 15373 | 0.043 | 0 | 0 |

These classes are descriptive strata, not solver-policy labels. The 120-second
dynamic screen must determine whether structurally different families share the
same PDR failure signature before any heuristic is promoted.
