# Public affine-induction benchmarks

This directory contains seven whole-design, single-property AIGER benchmarks
derived from two public RTL projects.  They exercise the affine-induction and
guarded-affine-summary paths without using modular decomposition, assume-guarantee
contracts, or per-block proof reuse.

## HAVEN/OpenCores Ethernet CRC

`haven/rtl/eth_crc.v` is the unmodified Ethernet CRC implementation distributed
by HAVEN at commit `b2beffbdeb940cbc84637f3425eee4b0e2fbe142`.  The local formal
wrapper compares that implementation, and repeated applications of its 4-bit
update, with an independently written bit-serial CRC-32/IEEE recurrence.

| AIGER input | Property |
| --- | --- |
| `eth_crc_original_vs_standard4.aag` | Original 4-bit update equals the standard recurrence |
| `eth_crc_explicit_vs_standard_s32.aag` | 32-bit/cycle parallel update equivalence |
| `eth_crc_explicit_vs_standard_s64.aag` | 64-bit/cycle parallel update equivalence |
| `eth_crc_explicit_vs_standard_s128.aag` | 128-bit/cycle parallel update equivalence |
| `eth_crc_explicit_vs_standard_s256.aag` | 256-bit/cycle parallel update equivalence |

The state machines receive arbitrary data, enable, and initialize sequences.
Each AIG contains one SAFE temporal property over the complete wrapper; the
wide models are not proved by splitting them into smaller CRC blocks.

## OpenTitan SECDED

The encoder and decoder come from OpenTitan commit
`01a04ddc0759d0ce5425e5ee5dc2ddf804b23060`.  The wrapper instantiates 8 or 32
independent 72/64 Hamming SECDED banks, stores arbitrary data, injects one
arbitrarily selected codeword-bit error, and checks that decoding recovers the
original data on the following cycle.

| AIGER input | Property |
| --- | --- |
| `opentitan_secded_512.aag` | Eight SECDED banks protect a 512-bit line |
| `opentitan_secded_2048.aag` | Thirty-two banks protect a 2048-bit row |

These are also whole-wrapper, single-property SAFE models.  The replicated
banks increase the width of one transition system; no bank-level proof is
reused to establish the final result.

## Running a benchmark

From the repository root, after building the model checker and its
CryptoMiniSat wrapper:

```bash
# General CDCL path
MC_PDR_SOLVER=cadical ./modelchecker -xag \
  artifact/data/public_affine_case_studies_v1/opentitan/aiger/opentitan_secded_512.aag

# Structure-guided affine path
MC_PDR_SOLVER=cmsat \
MC_PDR_CMSAT_GAUSS=1 \
MC_PDR_CMSAT_SIMPLIFY=0 \
MC_PDR_AFFINE_AUTO=1 \
MC_PDR_GUARDED_AFFINE_AUTO=1 \
MC_PDR_GUARDED_AFFINE_VALIDATE=1 \
./modelchecker -xag \
  artifact/data/public_affine_case_studies_v1/opentitan/aiger/opentitan_secded_512.aag
```

`PROVENANCE.tsv` records upstream commits and SHA256 hashes for the RTL files.
The OpenTitan files retain their Apache-2.0 license; `eth_crc.v` retains its
upstream LGPL notice.

## Excluded material

This benchmark directory intentionally excludes the exploratory BCH/Reed-Solomon
block decomposition, CAN contract reuse, and other compositional-verification
experiments.  It contains only inputs solved as one transition system.
