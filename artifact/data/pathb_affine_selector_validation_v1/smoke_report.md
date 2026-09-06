# Affine selector threshold sensitivity and blind holdout

Corpus: 4 models; train 0, holdout 4.
The split was frozen from family/structure names before these backend results were run.
Policy selection maximizes train solved count, then minimizes train PAR-2.

## All 27 policies

| Support | Coverage | Controls | Train solved | Train PAR-2 | Holdout solved | Holdout PAR-2 | Holdout gmean / CaDiCaL |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 16 | 0.50 | 1 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 16 | 0.50 | 2 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 16 | 0.50 | 3 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 16 | 0.75 | 1 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 16 | 0.75 | 2 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 16 | 0.75 | 3 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 16 | 1.00 | 1 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 16 | 1.00 | 2 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 16 | 1.00 | 3 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 32 | 0.50 | 1 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 32 | 0.50 | 2 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 32 | 0.50 | 3 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 32 | 0.75 | 1 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 32 | 0.75 | 2 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 32 | 0.75 | 3 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 32 | 1.00 | 1 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 32 | 1.00 | 2 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 32 | 1.00 | 3 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 64 | 0.50 | 1 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 64 | 0.50 | 2 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 64 | 0.50 | 3 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 64 | 0.75 | 1 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 64 | 0.75 | 2 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 64 | 0.75 | 3 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 64 | 1.00 | 1 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 64 | 1.00 | 2 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |
| 64 | 1.00 | 3 | 0/0 | 0.0 | 4/4 | 1.7 | 1.000 |

## Frozen-policy evaluation

| Policy | Split | Solved | PAR-2 | Gmean / CaDiCaL [95% bootstrap CI] | Mis-selected | Missed Gaussian | Non-plain path |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| train-selected `16/0.50/1` | train | 0/0 | 0.0 | nan [nan, nan] | 0 | 0 | 0 |
| train-selected `16/0.50/1` | holdout | 4/4 | 1.7 | 1.000 [1.000, 1.000] | 0 | 2 | 0 |
| paper-default `32/0.75/2` | train | 0/0 | 0.0 | nan [nan, nan] | 0 | 0 | 0 |
| paper-default `32/0.75/2` | holdout | 4/4 | 1.7 | 1.000 [1.000, 1.000] | 0 | 2 | 0 |

## Holdout by family

| Family | Models | CaDiCaL | Selected | Delta |
| --- | ---: | ---: | ---: | ---: |
| adder_equiv | 4 | 4 | 4 | +0 |

## Interpretation rule

A threshold is considered stable only if a neighborhood of policies preserves holdout
coverage and PAR-2; a single isolated winner is not evidence of a robust selector.
`Mis-selected` counts a selected path that loses a CaDiCaL solve or is more than 20%
slower on a common solve. `Missed Gaussian` uses the symmetric 20%/coverage rule.
