# Affine selector threshold sensitivity and blind holdout

Corpus: 387 models; train 256, holdout 131.
The split was frozen from family/structure names before these backend results were run.
Policy selection maximizes train solved count, then minimizes train PAR-2.

## All 27 policies

| Support | Coverage | Controls | Train solved | Train PAR-2 | Holdout solved | Holdout PAR-2 | Holdout gmean / CaDiCaL |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 16 | 0.50 | 1 | 154/256 | 25445.6 | 73/131 | 14424.0 | 1.049 |
| 16 | 0.50 | 2 | 225/256 | 8318.9 | 115/131 | 4301.2 | 0.840 |
| 16 | 0.50 | 3 | 225/256 | 8361.1 | 115/131 | 4310.4 | 0.935 |
| 16 | 0.75 | 1 | 154/256 | 25442.7 | 83/131 | 11986.8 | 0.954 |
| 16 | 0.75 | 2 | 222/256 | 9033.8 | 122/131 | 2445.2 | 0.677 |
| 16 | 0.75 | 3 | 222/256 | 9076.1 | 122/131 | 2454.8 | 0.746 |
| 16 | 1.00 | 1 | 154/256 | 25442.7 | 83/131 | 11986.3 | 0.926 |
| 16 | 1.00 | 2 | 207/256 | 12625.6 | 107/131 | 6264.6 | 0.858 |
| 16 | 1.00 | 3 | 207/256 | 12663.5 | 107/131 | 6270.2 | 0.891 |
| 32 | 0.50 | 1 | 151/256 | 26192.0 | 73/131 | 14424.5 | 1.050 |
| 32 | 0.50 | 2 | 222/256 | 9065.2 | 115/131 | 4301.7 | 0.841 |
| 32 | 0.50 | 3 | 222/256 | 9107.5 | 115/131 | 4310.9 | 0.936 |
| 32 | 0.75 | 1 | 151/256 | 26189.0 | 83/131 | 11987.3 | 0.954 |
| 32 | 0.75 | 2 | 219/256 | 9780.1 | 122/131 | 2445.7 | 0.677 |
| 32 | 0.75 | 3 | 219/256 | 9822.4 | 122/131 | 2455.3 | 0.746 |
| 32 | 1.00 | 1 | 151/256 | 26189.0 | 83/131 | 11986.8 | 0.927 |
| 32 | 1.00 | 2 | 204/256 | 13371.9 | 107/131 | 6265.2 | 0.859 |
| 32 | 1.00 | 3 | 204/256 | 13409.9 | 107/131 | 6270.7 | 0.892 |
| 64 | 0.50 | 1 | 151/256 | 26251.5 | 73/131 | 14426.0 | 1.065 |
| 64 | 0.50 | 2 | 222/256 | 9124.7 | 115/131 | 4303.2 | 0.852 |
| 64 | 0.50 | 3 | 222/256 | 9166.9 | 115/131 | 4312.4 | 0.949 |
| 64 | 0.75 | 1 | 151/256 | 26248.5 | 83/131 | 11988.8 | 0.966 |
| 64 | 0.75 | 2 | 219/256 | 9839.6 | 122/131 | 2447.2 | 0.686 |
| 64 | 0.75 | 3 | 219/256 | 9881.9 | 122/131 | 2456.8 | 0.756 |
| 64 | 1.00 | 1 | 151/256 | 26248.5 | 83/131 | 11988.3 | 0.938 |
| 64 | 1.00 | 2 | 204/256 | 13431.4 | 107/131 | 6266.7 | 0.869 |
| 64 | 1.00 | 3 | 204/256 | 13469.4 | 107/131 | 6272.3 | 0.903 |

## Frozen-policy evaluation

| Policy | Split | Solved | PAR-2 | Gmean / CaDiCaL [95% bootstrap CI] | Mis-selected | Missed Gaussian | Non-plain path |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| train-selected `16/0.50/2` | train | 225/256 | 8318.9 | 0.535 [0.412, 0.680] | 11 | 9 | 222 |
| train-selected `16/0.50/2` | holdout | 115/131 | 4301.2 | 0.840 [0.558, 1.246] | 20 | 10 | 114 |
| paper-default `32/0.75/2` | train | 219/256 | 9780.1 | 0.600 [0.475, 0.739] | 8 | 28 | 212 |
| paper-default `32/0.75/2` | holdout | 122/131 | 2445.7 | 0.677 [0.497, 0.888] | 8 | 11 | 97 |

## Blind-validation verdict

| Policy | Split | CaDiCaL | Selector | New solves | Lost solves | Net |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| train-selected `16/0.50/2` | train | 116 | 225 | 110 | 1 | +109 |
| train-selected `16/0.50/2` | holdout | 74 | 115 | 48 | 7 | +41 |
| paper-default `32/0.75/2` | train | 116 | 219 | 104 | 1 | +103 |
| paper-default `32/0.75/2` | holdout | 74 | 122 | 48 | 0 | +48 |

- At fixed coverage/control `0.75/2`, support `16/32/64` solves `122/122/122` holdout models: support is not coverage-sensitive in this range.
- Control caps 2 and 3 both solve 122 holdout models, but cap 2 has lower PAR-2 (2445.7 versus 2455.3).
- At fixed support/control `32/2`, coverage `0.50/0.75/1.00` solves `115/122/107`: the 0.75 guard is a substantive domain boundary, not an arbitrary neutral constant.
- The train-optimal 0.50 coverage rule does not transfer: it admits deep residue models
  whose Gaussian maintenance cost dominates. The pre-existing 0.75 rule is therefore
  retained; the holdout result is not used to retune it.

## Holdout by family

| Family | Models | CaDiCaL | Train-selected | Paper-default | Default delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| adder_equiv | 6 | 6 | 6 | 6 | +0 |
| aes_linear_equiv | 6 | 6 | 6 | 6 | +0 |
| affine_phase_sync | 9 | 0 | 2 | 2 | +2 |
| arx_equiv | 6 | 6 | 6 | 6 | +0 |
| crc_equiv | 6 | 6 | 6 | 6 | +0 |
| crc_frame_align | 26 | 2 | 26 | 26 | +24 |
| crc_frame_lock | 19 | 4 | 19 | 19 | +15 |
| crc_frame_residue | 12 | 12 | 5 | 12 | +0 |
| keccak_linear_equiv | 6 | 5 | 6 | 6 | +1 |
| lfsr_jump_equiv | 4 | 4 | 4 | 4 | +0 |
| mac_equiv | 5 | 3 | 3 | 3 | +0 |
| opentitan_prim_lfsr | 6 | 6 | 6 | 6 | +0 |
| scrambler_equiv | 3 | 0 | 3 | 3 | +3 |
| scrambler_recovery | 8 | 8 | 8 | 8 | +0 |
| syndrome_equiv | 3 | 0 | 3 | 3 | +3 |
| verilog_lfsr_style_equivalence | 6 | 6 | 6 | 6 | +0 |

## External public-RTL holdout

All 12 public RTL models are solved by both CaDiCaL and the default selector.
The selector/CaDiCaL geometric wall-time ratio is 0.685; the median ratio is 1.000. The gap means that the
aggregate speedup is driven by a few heavier CRC instances rather than uniform small-model acceleration.

## Online-selector equivalence check

Offline replay and the real online selector agree on 387/387 path choices
and 382/387 final statuses. This check uses the same binary, seed,
timeout, and manifest as the oracle-path experiment.
Holdout status agreement is 131/131.
The status differences are repeat-run boundary effects rather than selector-choice errors:
split counts `{'train': 5}` and directions `{'TIMEOUT->SAFE': 5}`.

## Interpretation rule

A threshold is considered stable only if a neighborhood of policies preserves holdout
coverage and PAR-2; a single isolated winner is not evidence of a robust selector.
`Mis-selected` counts a selected path that loses a CaDiCaL solve or is more than 20%
slower on a common solve. `Missed Gaussian` uses the symmetric 20%/coverage rule.
