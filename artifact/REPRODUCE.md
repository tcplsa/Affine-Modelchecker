# Reproducing the affine-induction experiments

The checked-in artifact contains the generated AIGER inputs, raw result tables,
analysis scripts, and independent SAFE checks used by the project report. No
prebuilt solver binary is included; build the current source first.

## Quick integrity check

```bash
cd artifact
sha256sum -c SHA256SUMS
```

## Generate one benchmark

```bash
python3 code/pathb/generate.py single \
  --family crc_frame_align --width 32 --symbol-bits 320 --out /tmp/crc32
```

Run the generated AAG with the two controlled backends:

```bash
MC_PDR_SOLVER=cadical ../modelchecker -xag /tmp/crc32/*.aag

MC_PDR_SOLVER=cmsat \
MC_PDR_CMSAT_GAUSS=1 \
MC_PDR_CMSAT_SIMPLIFY=0 \
MC_PDR_AFFINE_SUMMARY=1 \
../modelchecker -xag /tmp/crc32/*.aag
```

## Recompute reported summaries

```bash
python3 code/summarize_frozen_confirmation.py \
  data/pathb_crc_gauss_boundary_1800_frozen_v1/seed985011.tsv \
  data/pathb_crc_gauss_boundary_1800_frozen_v1/seed985021.tsv

python3 code/pathb/analyze_affine_selector_validation.py \
  --input data/pathb_affine_selector_validation_v1/oracle_120s.tsv \
  --online-input data/pathb_affine_selector_validation_v1/online_default_120s.tsv \
  --report /tmp/selector.md --summary /tmp/selector.json --timeout 120

python3 code/group_bootstrap_selector.py \
  data/pathb_affine_selector_validation_v1/oracle_120s.tsv
```

The long-running campaign protocol and exact result locations are documented in
`README.md`. Paths embedded in old raw manifests are provenance records; use
`data/pathb_affine_selector_validation_v1/manifest.relative.json` for portable
runs.
