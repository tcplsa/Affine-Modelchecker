# 120-second Single-Lane XOR-Backend Screen

Each model used the same MC-XAG PDR policy and seed. Only the SAT backend/Gaussian setting varied. This is a screening experiment, not an 1,800-second coverage claim.

## Aggregate coverage

| Backend | SAFE | TIMEOUT |
| --- | ---: | ---: |
| CaDiCaL | 18 | 0 |
| CMSat, no Gaussian | 14 | 4 |
| CMSat, Gaussian | 8 | 10 |

## Per-family coverage

| Family | Models | CaDiCaL | CMSat no-Gauss | CMSat Gaussian |
| --- | ---: | ---: | ---: | ---: |
| `crc_frame_residue` | 18 | 18 | 14 | 8 |

## Attribution candidates

- **Gaussian-specific candidates:** 0
- **CMSat-backend candidates (independent of Gaussian):** 0
- **All-backend timeouts:** 0

## Interpretation

No Gaussian-specific candidate was found in this screen. Any CMSat wins should be treated as native-XOR/SAT-backend effects until a Gaussian-only transition appears.
