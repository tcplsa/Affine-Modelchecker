# External Crypto and Arithmetic Circuit Sources

The generated 100-model semantic suite is the controlled primary set. External
circuits should be imported as a separate validation set because most public
collections are combinational blocks or unconstrained RTL, not ready-made
sequential safety properties.

| Source | Relevant material | Format and status | Proposed use |
| --- | --- | --- | --- |
| [EPFL Combinational Benchmark Suite](https://www.epfl.ch/labs/lsi/page-102566-en-html/benchmarks/) / [repository](https://github.com/lsils/benchmarks) | Ten arithmetic benchmarks, including adders, multipliers, divider, square root, and hypotenuse | AIGER, BLIF, Verilog, VHDL; repository is MIT licensed | Wrap two implementations in a sequential miter and test adder/multiplier/divider transfer beyond generated RTL |
| [IWLS 2005 benchmarks](https://iwls.org/iwls2005/benchmarks.html) | 84 RTL designs drawn from processors, communication, encryption, and arithmetic designs | Verilog/OpenAccess archive; provenance and license vary by design | Broad legacy validation after selecting source-recoverable designs and constructing explicit safety properties |
| [NIST Lightweight Cryptography benchmarking](https://csrc.nist.gov/Projects/lightweight-cryptography/performance-benchmarking) | Standardized lightweight-cryptography implementation and benchmarking context | Source links and performance resources, not one uniform model-checking suite | Choose standardized primitives and preserve parameter/provenance metadata |
| [GMU CERG repositories](https://github.com/GMUCERG) | Hardware-API implementations and cores for Ascon and other lightweight ciphers | Primarily VHDL with project-specific repositories | Extract round functions or linear layers, then build sequential implementation-equivalence properties |
| [OpenTitan AES core](https://github.com/lowRISC/opentitan/blob/master/hw/ip/aes/rtl/aes_core.sv) | Production-oriented AES RTL | SystemVerilog in the Apache-2.0 OpenTitan tree | Validate AES round/MixColumns conclusions on a realistic implementation |
| [OpenTitan KMAC](https://opentitan.org/book/hw/ip/kmac/data/kmac.html) | Keccak-based SHA-3/SHAKE/KMAC hardware block | Documented SystemVerilog IP with substantial integration dependencies | Extract the Keccak permutation datapath for a realistic XOR-rich transfer study |

## Import policy

1. Keep generated and external models in separate result tables.
2. Record source URL, revision, license, synthesis script, property wrapper, and
   resulting AIGER hash for every imported model.
3. Do not call a combinational block a hardware-safety benchmark until it has a
   meaningful sequential environment and checked property.
4. Prefer contiguous parameter sweeps and held-out architectures over selecting
   only instances where Gaussian reasoning wins.

The recommended first external tranche is EPFL arithmetic plus one GMU/OpenTitan
crypto core. It gives two very different transfer tests without immediately
incurring the dependency and licensing cleanup of the full IWLS archive.
