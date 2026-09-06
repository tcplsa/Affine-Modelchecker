# Frozen-Binary CRC Gaussian Confirmation at 1,800 Seconds

## Protocol

- Models: 15 preselected CRC-16/32/64 frame-alignment SAFE instances.
- Timeout: 1,800 seconds per configuration.
- Independent process seeds: 985011 and 985021.
- Each configuration uses four homogeneous PDR lanes.
- Frozen MC binary SHA256:
  `83d12c19856951adc32a1187f6253f45c2cb8cd44969cad4130d752d669bd7d8`.

## Result

Both launches completed all 15 models. On every model and in both launches:

| Configuration | Solved | Timed out |
| --- | ---: | ---: |
| 4x CaDiCaL | 0/15 | 15/15 |
| 4x CryptoMiniSat native XOR, Gaussian off | 0/15 | 15/15 |
| 4x CryptoMiniSat native XOR, Gaussian on | **15/15 SAFE** | 0/15 |

Gaussian wall time ranges from 0.503 to 1.012 seconds. Thus all 15 points remain
strict Gaussian-only under a frozen executable and two independent launches.

The 15 original AAG models were also validated separately by the independent
XOR-aware 1-induction checker in
`../affine_certificate_validation_v1/core_15/`.

## Integrity

- `seed985011.tsv` SHA256:
  `34f54a504a198f52605e5341de6a02bdd3ea8c330c568bc4782225cf3e3b5339`.
- `seed985021.tsv` SHA256:
  `db7a53dc8332ca1db4a197e12463860077c1902695c59ffe3f1fac20b83de959`.
