# CRC-32 Gaussian Confirmation at 1,800 Seconds

## Protocol

Each model is a SAFE serial-versus-parallel CRC frame-alignment property with arbitrary traffic after the start-of-frame reset. Every MC run uses one XAG PDR lane and the same policy; only the SAT backend changes. Stock rIC3 uses its native four-replica portfolio. The two process launches use independent seeds.

## Confirmed Gaussian-specific results

| Model | CRC data width | MC-XAG CaDiCaL | MC-XAG CMSat no-Gauss | MC-XAG CMSat Gaussian | stock rIC3-4 |
| --- | ---: | --- | --- | --- | --- |
| `crc_frame_align_polynomial79764919_seed981352_symbol_bits32_width32` | 32 | TIMEOUT; TIMEOUT | TIMEOUT; TIMEOUT | SAFE (0.510s); SAFE (0.509s) | TIMEOUT (1800.025s); TIMEOUT (1800.022s) |
| `crc_frame_align_polynomial79764919_seed981384_symbol_bits64_width32` | 32 | TIMEOUT; TIMEOUT | TIMEOUT; TIMEOUT | SAFE (0.503s); SAFE (0.503s) | TIMEOUT (1800.035s); TIMEOUT (1800.036s) |

## Interpretation and boundary

- Confirmed candidates: **2** of 2 common models.
- CMSat without Gaussian also times out, separating this result from a native-XOR backend effect under the tested policy.
- The rIC3 comparison is a real 1,800-second hard-boundary result, not a 1,800-to-3,600-second frontier speedup.
- These are frame-depth-one inductive proofs. They establish a sharp SAT and inductive-query advantage for a realistic CRC state-alignment task, but not yet an advantage on deep PDR obligation management. The separate block-lock recovery cohort addresses that boundary.
