# Path B controlled-circuit generator

Deterministic, structure-controlled sequential safety benchmarks for the
Path B controlled XOR/arithmetic domain (see `PATH_B_CONTROLLED_DOMAINS_DESIGN.md`).

## Layout

- `netlist.py` — gate-level netlist intermediate representation (single source of truth).
- `aag_writer.py` — AAG (ASCII AIGER) exporter: XOR lowered to 3-AND; latch rows carry an explicit reset literal.
- `blif_writer.py` — BLIF exporter that preserves XOR as `.names 01 1 / 10 1` rows, so `blif_output` recognizes them as native XOR (CryptoMiniSat `add_xor`).
- `families/lfsr.py` — Galois LFSR (SAFE: all-zero unreachable).
- `families/adders.py` — three adder structures (ripple/prefix/carrysave) with two sequential properties:
  - `invariant` (SAFE): two identical accumulators fed the same input must stay equal.
  - `counter` (UNSAFE): free-running `acc' = acc + 1`, bad when `acc == target`.
- `families/affine_equiv.py` — two independent dense affine state transforms
  driven by shared inputs.  The SAFE invariant is bitwise state equality, so
  PDR lemmas remain ordinary clauses while predecessor queries require XOR
  elimination.
- `families/affine_warmup.py` — delayed version of affine equivalence.  The
  state vectors synchronize after the first transition, and a valid chain
  activates equality only after several frames.
- `families/affine_phase_sync.py` — a full-rank affine data path with one-hot
  phase corrections.  Equality becomes active after several frames without
  placing muxes in the XOR data path.
- `families/crc_equiv.py` — serial versus matrix-expanded CRC updates using
  standard CRC-8, CRC-16-CCITT, and CRC-32 polynomials.
- `families/aes_linear_equiv.py` — structurally distinct AES MixColumns paths.
- `families/keccak_linear_equiv.py` — dual Keccak theta-rho-pi linear layers.
- `families/arx_equiv.py` — ChaCha quarter-round and Speck-style ARX equivalence.
- `families/adder_equiv.py` — ripple/prefix/carry-save accumulator equivalence.
- `families/mac_equiv.py` — schoolbook/Wallace-style multiply-accumulate equivalence.
- `families/scrambler_recovery.py` — IEEE 802.3 64b/66b self-synchronizing
  scrambler recovery after arbitrary receiver history loss.
- `families/crc_frame_align.py` — CRC state alignment at an arbitrary
  start-of-frame boundary under arbitrary valid/data traffic.
- `families/crc_frame_lock.py` — receiver block-lock recovery before the CRC
  frame boundary, including lock loss and reacquisition.
- `families/crc_frame_residue.py` — fixed-length payload/FCS protocol with a
  delayed CRC residue check.
- `generate.py` — CLI + manifest (AAG/BLIF sha256, xor density, expected outcome).
- `self_test.py` — end-to-end verdict cross-check against rIC3.
- `build_semantic_suite.py` — frozen specification for 100 categorized
  crypto/arithmetic sequential safety circuits.
- `validate_semantic_suite.py` — deterministic export checks and randomized
  sequential simulation for the 100-circuit suite.
- `summarize_semantic_suite.py` — structural report and one-model-per-family
  solver smoke manifest.
- `build_real_xor_apps.py` — a 24-model protocol-oriented link-coding cohort.
- `build_crc_frame_lock_suite.py` — a 32-model CRC block-lock recovery cohort.
- `build_crc_frame_residue_suite.py` — an 18-model temporal CRC/FCS cohort.
- `build_crc_gauss_boundary_suite.py` — a standard-polynomial, pure-backend
  CRC Gaussian boundary sweep.

## Usage

```bash
# one benchmark
python3 pathb/generate.py single --family lfsr --width 8 --out dir/
python3 pathb/generate.py single --family adder --width 16 --struct prefix \
    --mode invariant --out dir/

# batch from a manifest JSON
python3 pathb/generate.py manifest --manifest specs.json --out dir/

# build, generate, validate, and summarize the 100-model semantic suite
python3 pathb/build_semantic_suite.py \
  --output pathb_semantic_100_specs_v1.json \
  --summary pathb_semantic_100_summary_v1.json
python3 pathb/generate.py manifest \
  --manifest pathb_semantic_100_specs_v1.json \
  --out results/pathb_semantic_100_v1/benchmarks
python3 pathb/validate_semantic_suite.py \
  --specs pathb_semantic_100_specs_v1.json \
  --manifest results/pathb_semantic_100_v1/benchmarks/manifest.json

# construct application-grounded link-coding models (no performance run)
python3 pathb/build_real_xor_apps.py --output pathb_real_xor_apps_v1.json
python3 pathb/generate.py manifest \
  --manifest pathb_real_xor_apps_v1.json \
  --out results/pathb_real_xor_apps_v1/benchmarks

# sanity gate (needs rIC3 binary)
python3 pathb/self_test.py --ric3 /home/wudl/rIC3/target/release/ric3
```

## Expected outcomes

| family | mode | expected |
| --- | --- | --- |
| lfsr | — | SAFE (all-zero unreachable from nonzero init) |
| adder | invariant | SAFE (acc1 == acc2 is an inductive invariant) |
| adder | counter | UNSAFE (witness depth = target) |
| affine_equiv | — | SAFE (left and right states remain equal) |
| affine_warmup | — | SAFE (delayed equality after synchronization) |
| affine_phase_sync | — | SAFE (phase corrections reach equality when done rises) |
| crc_equiv | — | SAFE (serial and matrix-expanded CRC states stay equal) |
| aes_linear_equiv | — | SAFE (AES MixColumns implementations stay equal) |
| keccak_linear_equiv | — | SAFE (Keccak linear-layer implementations stay equal) |
| arx_equiv | — | SAFE (ARX round implementations stay equal) |
| adder_equiv | — | SAFE (different accumulator structures stay equal) |
| mac_equiv | — | SAFE (different MAC structures stay equal) |
| scrambler_recovery | — | SAFE (64b/66b descrambler locks after 58 bits) |
| crc_frame_align | — | SAFE (serial and parallel CRC engines align after SOF) |
| crc_frame_lock | — | SAFE (CRC engines align while receiver block lock is held) |
| crc_frame_residue | — | SAFE (derived FCS produces zero CRC residue at frame end) |

## Known limitation

The `blif/` Python PDR (`PDRblif.py`) aborts on UNSAFE instances inside
`extract_state_from_sat` (`assert res == 0, "不应为SAT"`).  This is a PDR-side
bug, not a generator bug: rIC3 returns the correct verdict on the same AAG.
Use rIC3 / MC for UNSAFE cases until that PDR path is fixed (see repo memory).
