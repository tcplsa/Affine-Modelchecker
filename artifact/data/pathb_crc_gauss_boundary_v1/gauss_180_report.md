# 120-second Single-Lane XOR-Backend Screen

Each model used the same MC-XAG PDR policy and seed. Only the SAT backend/Gaussian setting varied. This is a screening experiment, not an 1,800-second coverage claim.

## Aggregate coverage

| Backend | SAFE | TIMEOUT |
| --- | ---: | ---: |
| CaDiCaL | 4 | 19 |
| CMSat, no Gaussian | 5 | 18 |
| CMSat, Gaussian | 20 | 3 |

## Per-family coverage

| Family | Models | CaDiCaL | CMSat no-Gauss | CMSat Gaussian |
| --- | ---: | ---: | ---: | ---: |
| `crc_frame_align` | 23 | 4 | 5 | 20 |

## Attribution candidates

- **Gaussian-specific candidates:** 15
- **CMSat-backend candidates (independent of Gaussian):** 1
- **All-backend timeouts:** 3

### Gaussian-specific

| Family | Model | Time (s) |
| --- | --- | ---: |
| `crc_frame_align` | `crc_frame_align_polynomial4129_seed1001096_symbol_bits96_width16` | 0.518 |
| `crc_frame_align` | `crc_frame_align_polynomial4129_seed1001192_symbol_bits192_width16` | 0.524 |
| `crc_frame_align` | `crc_frame_align_polynomial4129_seed1001256_symbol_bits256_width16` | 0.512 |
| `crc_frame_align` | `crc_frame_align_polynomial4129_seed1001128_symbol_bits128_width16` | 0.509 |
| `crc_frame_align` | `crc_frame_align_polynomial79764919_seed1017032_symbol_bits32_width32` | 0.507 |
| `crc_frame_align` | `crc_frame_align_polynomial79764919_seed1017064_symbol_bits64_width32` | 0.508 |
| `crc_frame_align` | `crc_frame_align_polynomial79764919_seed1017096_symbol_bits96_width32` | 0.506 |
| `crc_frame_align` | `crc_frame_align_polynomial79764919_seed1017128_symbol_bits128_width32` | 0.504 |
| `crc_frame_align` | `crc_frame_align_polynomial79764919_seed1017160_symbol_bits160_width32` | 0.505 |
| `crc_frame_align` | `crc_frame_align_polynomial79764919_seed1017192_symbol_bits192_width32` | 0.506 |
| `crc_frame_align` | `crc_frame_align_polynomial79764919_seed1017256_symbol_bits256_width32` | 0.513 |
| `crc_frame_align` | `crc_frame_align_polynomial4823603603198064275_seed1049016_symbol_bits16_width64` | 0.503 |
| `crc_frame_align` | `crc_frame_align_polynomial4823603603198064275_seed1049032_symbol_bits32_width64` | 1.005 |
| `crc_frame_align` | `crc_frame_align_polynomial4823603603198064275_seed1049064_symbol_bits64_width64` | 0.505 |
| `crc_frame_align` | `crc_frame_align_polynomial4823603603198064275_seed1049096_symbol_bits96_width64` | 1.007 |

### CMSat backend, not Gaussian

| Family | Model | No-Gauss time (s) | Gaussian time (s) |
| --- | --- | ---: | ---: |
| `crc_frame_align` | `crc_frame_align_polynomial4129_seed1001064_symbol_bits64_width16` | 0.522 | 0.521 |

## Interpretation

The application-grounded CRC cohort contains a Gaussian-specific transition: the listed CRC parallel alignment/recovery instances time out in both non-Gaussian lanes but complete with Gaussian reasoning. This is distinct from the CRC-16 cases solved by CMSat without Gaussian reasoning. The next experiment must repeat both classes at 1,800 seconds and compare against stock rIC3. The parameterized block-lock detector must not itself be interpreted as a deep-PDR result unless the observed frame depth also changes.
Gaussian-specific families in this screen: crc_frame_align.
