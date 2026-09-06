# Pure Gaussian CRC Boundary

All single-lane rows use the same MC-XAG PDR policy. Only the pure SAT backend differs. Four-lane rows, when present, use four replicas of the same backend rather than a mixed portfolio.

## Single-lane boundary

| CRC | Bits/transition | CaDiCaL | CMSat no-Gauss | CMSat Gaussian |
| --- | ---: | --- | --- | --- |
| CRC-16 | 320 | TIMEOUT | TIMEOUT | SAFE (0.546s) |
| CRC-16 | 384 | TIMEOUT | TIMEOUT | SAFE (0.519s) |
| CRC-16 | 448 | TIMEOUT | TIMEOUT | SAFE (0.544s) |
| CRC-16 | 512 | TIMEOUT | TIMEOUT | SAFE (0.508s) |
| CRC-16 | 640 | TIMEOUT | TIMEOUT | SAFE (0.521s) |
| CRC-16 | 768 | TIMEOUT | TIMEOUT | SAFE (1.006s) |
| CRC-16 | 1024 | TIMEOUT | TIMEOUT | TIMEOUT |
| CRC-32 | 272 | TIMEOUT | TIMEOUT | SAFE (0.513s) |
| CRC-32 | 288 | TIMEOUT | TIMEOUT | SAFE (1.509s) |
| CRC-32 | 304 | TIMEOUT | TIMEOUT | SAFE (1.008s) |
| CRC-32 | 320 | TIMEOUT | TIMEOUT | TIMEOUT |
| CRC-32 | 336 | TIMEOUT | TIMEOUT | TIMEOUT |
| CRC-32 | 352 | TIMEOUT | TIMEOUT | TIMEOUT |
| CRC-32 | 368 | TIMEOUT | TIMEOUT | TIMEOUT |
| CRC-64 | 100 | TIMEOUT | TIMEOUT | SAFE (3.010s) |
| CRC-64 | 104 | TIMEOUT | TIMEOUT | SAFE (5.009s) |
| CRC-64 | 108 | TIMEOUT | TIMEOUT | SAFE (1.507s) |
| CRC-64 | 112 | TIMEOUT | TIMEOUT | SAFE (3.508s) |
| CRC-64 | 116 | TIMEOUT | TIMEOUT | SAFE (2.009s) |
| CRC-64 | 120 | TIMEOUT | TIMEOUT | SAFE (1.009s) |
| CRC-64 | 124 | TIMEOUT | TIMEOUT | TIMEOUT |

At the 180-second screen limit, strict Gaussian-only points: **15**.
