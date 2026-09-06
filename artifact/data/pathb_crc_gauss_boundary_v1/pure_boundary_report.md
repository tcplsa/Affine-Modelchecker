# Pure Gaussian CRC Boundary

All single-lane rows use the same MC-XAG PDR policy. Only the pure SAT backend differs. Four-lane rows, when present, use four replicas of the same backend rather than a mixed portfolio.

## Single-lane boundary

| CRC | Bits/transition | CaDiCaL | CMSat no-Gauss | CMSat Gaussian |
| --- | ---: | --- | --- | --- |
| CRC-16 | 32 | SAFE (106.660s) | SAFE (0.541s) | SAFE (0.519s) |
| CRC-16 | 64 | TIMEOUT | SAFE (0.522s) | SAFE (0.521s) |
| CRC-16 | 96 | TIMEOUT | TIMEOUT | SAFE (0.518s) |
| CRC-16 | 128 | TIMEOUT | TIMEOUT | SAFE (0.509s) |
| CRC-16 | 192 | TIMEOUT | TIMEOUT | SAFE (0.524s) |
| CRC-16 | 256 | TIMEOUT | TIMEOUT | SAFE (0.512s) |
| CRC-32 | 8 | SAFE (0.544s) | SAFE (0.508s) | SAFE (0.505s) |
| CRC-32 | 16 | SAFE (36.552s) | SAFE (0.504s) | SAFE (0.510s) |
| CRC-32 | 32 | TIMEOUT | TIMEOUT | SAFE (0.507s) |
| CRC-32 | 64 | TIMEOUT | TIMEOUT | SAFE (0.508s) |
| CRC-32 | 96 | TIMEOUT | TIMEOUT | SAFE (0.506s) |
| CRC-32 | 128 | TIMEOUT | TIMEOUT | SAFE (0.504s) |
| CRC-32 | 160 | TIMEOUT | TIMEOUT | SAFE (0.505s) |
| CRC-32 | 192 | TIMEOUT | TIMEOUT | SAFE (0.506s) |
| CRC-32 | 256 | TIMEOUT | TIMEOUT | SAFE (0.513s) |
| CRC-32 | 384 | TIMEOUT | TIMEOUT | TIMEOUT |
| CRC-64 | 8 | SAFE (7.013s) | SAFE (0.507s) | SAFE (0.506s) |
| CRC-64 | 16 | TIMEOUT | TIMEOUT | SAFE (0.503s) |
| CRC-64 | 32 | TIMEOUT | TIMEOUT | SAFE (1.005s) |
| CRC-64 | 64 | TIMEOUT | TIMEOUT | SAFE (0.505s) |
| CRC-64 | 96 | TIMEOUT | TIMEOUT | SAFE (1.007s) |
| CRC-64 | 128 | TIMEOUT | TIMEOUT | TIMEOUT |
| CRC-64 | 160 | TIMEOUT | TIMEOUT | TIMEOUT |

At the 180-second screen limit, strict Gaussian-only points: **15**.

## Pure four-lane confirmation

| CRC | Bits/transition | 4x CaDiCaL | 4x CMSat no-Gauss | 4x CMSat Gaussian | Repetitions |
| --- | ---: | --- | --- | --- | ---: |
| CRC-16 | 96 | TIMEOUT | TIMEOUT | SAFE | 2 |
| CRC-16 | 128 | TIMEOUT | TIMEOUT | SAFE | 2 |
| CRC-16 | 192 | TIMEOUT | TIMEOUT | SAFE | 2 |
| CRC-16 | 256 | TIMEOUT | TIMEOUT | SAFE | 2 |
| CRC-32 | 32 | TIMEOUT | TIMEOUT | SAFE | 2 |
| CRC-32 | 64 | TIMEOUT | TIMEOUT | SAFE | 2 |
| CRC-32 | 96 | TIMEOUT | TIMEOUT | SAFE | 2 |
| CRC-32 | 128 | TIMEOUT | TIMEOUT | SAFE | 2 |
| CRC-32 | 160 | TIMEOUT | TIMEOUT | SAFE | 2 |
| CRC-32 | 192 | TIMEOUT | TIMEOUT | SAFE | 2 |
| CRC-32 | 256 | TIMEOUT | TIMEOUT | SAFE | 2 |
| CRC-64 | 16 | TIMEOUT | TIMEOUT | SAFE | 2 |
| CRC-64 | 32 | TIMEOUT | TIMEOUT | SAFE | 2 |
| CRC-64 | 64 | TIMEOUT | TIMEOUT | SAFE | 2 |
| CRC-64 | 96 | TIMEOUT | TIMEOUT | SAFE | 2 |
