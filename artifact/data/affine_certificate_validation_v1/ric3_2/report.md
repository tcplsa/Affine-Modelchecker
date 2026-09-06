# Independent SAFE Certificate Validation

- Models: 2
- Passed: 2
- Failed: 0
- Obligations: `Init => I` and `I & T => I'`, where `I` contains the safety property.
- XOR trust check: exhaustive four-assignment validation of every recognized local pattern.
- SAT backend: CryptoMiniSat native XOR with Gaussian elimination.

The checker parses the original AAG independently and does not call MC's PDR implementation.
