# 120-second Single-Lane XOR-Backend Screen

Each model used the same MC-XAG PDR policy and seed. Only the SAT backend/Gaussian setting varied. This is a screening experiment, not an 1,800-second coverage claim.

## Aggregate coverage

| Backend | SAFE | TIMEOUT |
| --- | ---: | ---: |
| CaDiCaL | 0 | 21 |
| CMSat, no Gaussian | 0 | 21 |
| CMSat, Gaussian | 15 | 6 |

## Per-family coverage

| Family | Models | CaDiCaL | CMSat no-Gauss | CMSat Gaussian |
| --- | ---: | ---: | ---: | ---: |
| `crc_frame_align` | 21 | 0 | 0 | 15 |

## Attribution candidates

- **Gaussian-specific candidates:** 15
- **CMSat-backend candidates (independent of Gaussian):** 0
- **All-backend timeouts:** 6

### Gaussian-specific

| Family | Model | Time (s) |
| --- | --- | ---: |
| `crc_frame_align` | `crc_frame_align_polynomial4129_seed1002320_symbol_bits320_width16` | 0.546 |
| `crc_frame_align` | `crc_frame_align_polynomial4129_seed1002640_symbol_bits640_width16` | 0.521 |
| `crc_frame_align` | `crc_frame_align_polynomial4129_seed1002768_symbol_bits768_width16` | 1.006 |
| `crc_frame_align` | `crc_frame_align_polynomial79764919_seed1018272_symbol_bits272_width32` | 0.513 |
| `crc_frame_align` | `crc_frame_align_polynomial4129_seed1002384_symbol_bits384_width16` | 0.519 |
| `crc_frame_align` | `crc_frame_align_polynomial4129_seed1002448_symbol_bits448_width16` | 0.544 |
| `crc_frame_align` | `crc_frame_align_polynomial4129_seed1002512_symbol_bits512_width16` | 0.508 |
| `crc_frame_align` | `crc_frame_align_polynomial79764919_seed1018288_symbol_bits288_width32` | 1.509 |
| `crc_frame_align` | `crc_frame_align_polynomial79764919_seed1018304_symbol_bits304_width32` | 1.008 |
| `crc_frame_align` | `crc_frame_align_polynomial4823603603198064275_seed1050104_symbol_bits104_width64` | 5.009 |
| `crc_frame_align` | `crc_frame_align_polynomial4823603603198064275_seed1050100_symbol_bits100_width64` | 3.010 |
| `crc_frame_align` | `crc_frame_align_polynomial4823603603198064275_seed1050108_symbol_bits108_width64` | 1.507 |
| `crc_frame_align` | `crc_frame_align_polynomial4823603603198064275_seed1050116_symbol_bits116_width64` | 2.009 |
| `crc_frame_align` | `crc_frame_align_polynomial4823603603198064275_seed1050112_symbol_bits112_width64` | 3.508 |
| `crc_frame_align` | `crc_frame_align_polynomial4823603603198064275_seed1050120_symbol_bits120_width64` | 1.009 |

## Interpretation

The application-grounded CRC cohort contains a Gaussian-specific transition: the listed CRC parallel alignment/recovery instances time out in both non-Gaussian lanes but complete with Gaussian reasoning. This is distinct from the CRC-16 cases solved by CMSat without Gaussian reasoning. The next experiment must repeat both classes at 1,800 seconds and compare against stock rIC3. The parameterized block-lock detector must not itself be interpreted as a deep-PDR result unless the observed frame depth also changes.
Gaussian-specific families in this screen: crc_frame_align.
