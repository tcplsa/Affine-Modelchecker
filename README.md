# XAG-Modelchecker

## Structure-Guided Gaussian Reasoning for Affine Induction

XAG-Modelchecker is an IC3/PDR hardware model checker that recovers XOR
structure from AIGER and selectively exposes affine transition relations to
CryptoMiniSat's native XOR and Gaussian reasoning. The central idea is not to
replace CDCL globally. It is to recognize **shallow affine induction** queries,
where parity reasoning is the right representation, and retain CaDiCaL for the
rest of the design space.

The repository contains the implementation, controlled AIGER benchmarks, raw
experimental tables, generators, analysis scripts, negative controls, and
independent SAFE checks.

## Main result

The validated specialist domain consists of CRC/LFSR/scrambler/syndrome-style
state machines whose property-relevant next-state relation has high affine
coverage, substantial cross-latch support, and a shallow inductive proof.

| Experiment | CaDiCaL / control | Structure-guided Gaussian |
| --- | ---: | ---: |
| Frozen CRC-16/32/64 hard set, 1,800 s, launch 1 | 0/15 | **15/15 SAFE** |
| Frozen CRC-16/32/64 hard set, 1,800 s, launch 2 | 0/15 | **15/15 SAFE** |
| Blind selector holdout, 131 models | 74/131 | **122/131** |
| Stock rIC3-4 hard CRC-32 cases | 0/2 | **2/2, about 0.5 s** |

For the frozen 15-model experiment, four CaDiCaL lanes and four native-XOR
CryptoMiniSat lanes with Gaussian disabled all time out. Four Gaussian lanes
solve every model in 0.503--1.012 seconds in two independent launches. The
original AAGs were also checked by an independent XOR-aware one-induction
checker. See [artifact/README.md](artifact/README.md) for exact files and
integrity hashes.

The selector result is a coverage result, not a claim of universal speedup.
The family-group bootstrap interval for common-solve runtime crosses 1. Deep
CRC residue, nonlinear control, and carry-dominated arithmetic are included as
explicit failure-domain evidence.

## Method

1. **Recover structure.** Recognize XOR subgraphs in an ordinary AIG and retain
   them as XAG equations instead of treating every XOR as an unrelated AND
   network.
2. **Analyze the transition relation.** Express each latch next-state function,
   when possible, as a GF(2) affine equation and measure coverage, rank, and
   support width.
3. **Select the reasoning path.** Use Gaussian reasoning only when the observed
   structure matches the affine-induction domain. The evaluated default uses a
   support threshold of 32, affine coverage of 0.75, and at most two control
   latches for guarded affine modes.
4. **Preserve incremental PDR.** Frame, predecessor, lifting, and push queries
   remain ordinary incremental PDR queries. Only their transition encoding and
   SAT backend change.
5. **Control Gaussian cost.** Optional runtime telemetry can disable Gaussian
   matrices when deeper queries spend substantial elimination work without
   useful propagation or conflict.
6. **Compress private XOR islands.** Private XOR trees or DAGs can be replaced
   by one boundary parity equation, reducing matrix variables while preserving
   externally visible semantics. Replacement can be SAT-validated at startup.

The approach is sound because every recovered or summarized parity relation is
logically equivalent to the original gate cone. Selection affects performance,
not the verification result.

## Applicability

Good targets:

- CRC frame alignment and block-lock datapaths;
- LFSR and scrambler equivalence or recovery properties;
- syndrome and other linear-code datapaths;
- SAFE properties that close in a small number of PDR frames;
- affine next-state cones with broad latch coupling.

Expected fallback targets:

- adders, multipliers, MACs, and ARX circuits dominated by carry/AND logic;
- deep protocol properties that require many incremental frames;
- large mux-controlled designs with more than a small number of state guards;
- arbitrary HWMCC models without a property-relevant affine core.

This boundary is a feature of the method: it prevents expensive Gaussian
maintenance from being imposed on unsuitable PDR workloads.

## Build

The base solver uses the bundled CaDiCaL and MiniSat sources. The affine lane
uses CryptoMiniSat 5.14.5 plus a small API patch for runtime Gaussian control
and telemetry.

```bash
git clone https://github.com/tcplsa/XAG-Modelchecker.git
cd XAG-Modelchecker
./scripts/bootstrap_cmsat.sh
```

The bootstrap script clones `tcplsa/PIC3withXors` beside this repository,
checks out the recorded dependency commit, applies
`third_party/cryptominisat-5.14.5-affine-pdr.patch`, builds CryptoMiniSat, and
then builds Modelchecker. To use an existing dependency tree:

```bash
./scripts/bootstrap_cmsat.sh /path/to/PIC3withXors
```

For a manual build, pass `CMSAT_ROOT=/path/to/PIC3withXors` to `make`.

## Run

CaDiCaL baseline:

```bash
./modelchecker -aig design.aag
```

Explicit structure-guided Gaussian lane:

```bash
MC_PDR_SOLVER=cmsat \
MC_PDR_CMSAT_GAUSS=1 \
MC_PDR_CMSAT_SIMPLIFY=0 \
MC_PDR_AFFINE_SUMMARY=1 \
MC_PDR_STATS=1 \
./modelchecker -xag design.aag
```

Automatic affine backend selection:

```bash
MC_PDR_AFFINE_AUTO=1 \
MC_PDR_GUARDED_AFFINE_AUTO=1 \
MC_PDR_GUARDED_AFFINE_VALIDATE=1 \
MC_PDR_STATS=1 \
./modelchecker -xag design.aag
```

Four homogeneous Gaussian lanes:

```bash
MC_PDR_SOLVER_LANES=cmsat,cmsat,cmsat,cmsat \
MC_PDR_CMSAT_GAUSS=1 \
MC_PDR_AFFINE_SUMMARY=1 \
./modelchecker --forward-xag 4 design.aag
```

Use `-witness` for UNSAFE traces and `-certificate` for the standard PDR SAFE
certificate path. Run `./modelchecker -h` for the complete command-line list.

## Artifact layout

- `artifact/data/`: raw TSV/JSON/log data and all redistributed AIGER inputs;
- `artifact/code/pathb/`: deterministic benchmark generators and experiment
  runners;
- `artifact/reports/`: detailed Chinese technical and experimental reports;
- `artifact/environment/`: machine, version, timing, and certificate records;
- `artifact/REPRODUCE.md`: short integrity and analysis commands;
- `docs/TECHNICAL_ROUTE_ZH.md`: detailed Chinese explanation of the method;
- `third_party/`: CryptoMiniSat wrapper and the small dependency patch.

The 387-model selector corpus includes 16 structural families and a frozen
256/131 train/holdout split. Generated cases are grouped by construction to
avoid presenting correlated parameter variants as independent evidence.

## Secondary functionality

The codebase also retains AIG/XAG ablations, BMC, directional PDR, multiple
four-lane portfolios, CNF preprocessing telemetry, witnesses, and certificates.
These facilities support controlled comparisons; they are not the primary
claim of this release.

## License

The Modelchecker code is distributed under the repository's existing
[LICENSE](LICENSE). Third-party benchmark provenance and solver licenses remain
with their respective upstream projects; see the manifests under
`artifact/data/pathb_public_affine_rtl_v1/`.
