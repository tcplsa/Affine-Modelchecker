# 120-second Single-Lane XOR-Backend Screen

Each model used the same MC-XAG PDR policy and seed. Only the SAT backend/Gaussian setting varied. This is a screening experiment, not an 1,800-second coverage claim.

## Aggregate coverage

| Backend | SAFE | TIMEOUT |
| --- | ---: | ---: |
| CaDiCaL | 20 | 4 |
| CMSat, no Gaussian | 22 | 2 |
| CMSat, Gaussian | 24 | 0 |

## Per-family coverage

| Family | Models | CaDiCaL | CMSat no-Gauss | CMSat Gaussian |
| --- | ---: | ---: | ---: | ---: |
| `crc_frame_align` | 8 | 4 | 6 | 8 |
| `scrambler_recovery` | 16 | 16 | 16 | 16 |

## Attribution candidates

- **Gaussian-specific candidates:** 2
- **CMSat-backend candidates (independent of Gaussian):** 2
- **All-backend timeouts:** 0

### Gaussian-specific

| Family | Model | Time (s) |
| --- | --- | ---: |
| `crc_frame_align` | `crc_frame_align_polynomial79764919_seed981352_symbol_bits32_width32` | 0.594 |
| `crc_frame_align` | `crc_frame_align_polynomial79764919_seed981384_symbol_bits64_width32` | 0.593 |

### CMSat backend, not Gaussian

| Family | Model | No-Gauss time (s) | Gaussian time (s) |
| --- | --- | ---: | ---: |
| `crc_frame_align` | `crc_frame_align_polynomial4129_seed981192_symbol_bits32_width16` | 0.105 | 0.604 |
| `crc_frame_align` | `crc_frame_align_polynomial4129_seed981224_symbol_bits64_width16` | 0.591 | 0.599 |

## Interpretation

The application-grounded CRC cohort contains a Gaussian-specific transition: the listed CRC-32 parallel frame-alignment instances time out in both non-Gaussian lanes but complete with Gaussian reasoning. This is distinct from the CRC-16 cases solved by CMSat without Gaussian reasoning. The next experiment must repeat both classes at 1,800 seconds and compare against stock rIC3.
