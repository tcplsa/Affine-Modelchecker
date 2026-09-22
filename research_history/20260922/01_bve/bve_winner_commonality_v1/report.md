# BVE winner commonality

This report separates outcome coverage from runtime. Runtime groups use a two-second dead zone. Cross-campaign rIC3 runtime effects remain load-confounded.

## rIC3 product-sum-high vs product-high

| Candidate-only | Reference-only | Speed wins | Speed losses | Close | Both unsolved |
|---:|---:|---:|---:|---:|---:|
| 13 | 1 | 350 | 24 | 975 | 617 |

### Outcome-discordant models

**Candidate only (13)**

- `2015__pdtswvqis10x6p2`: year=2015, family=pdtswvqis, tier=timeout, ANDs=4348, XORs=37
- `2025__yosyshq_appnote_123_cv32e40x-p524`: year=2025, family=yosyshq_appnote_, tier=timeout, ANDs=60709, XORs=1503
- `2024__ILA_Ridecore_SLT_sanity`: year=2024, family=ILA_Ridecore_SLT_sanity, tier=timeout, ANDs=438734, XORs=17112
- `2015__oski15a01b51s`: year=2015, family=oski, tier=timeout, ANDs=306471, XORs=13441
- `2015__pdtvsarmultip29`: year=2015, family=pdtvsarmultip, tier=timeout, ANDs=2743, XORs=168
- `2025__dblclockfft_butterfly_ck3_r0-p100`: year=2025, family=dblclockfft_butterfly_ck, tier=timeout, ANDs=2871, XORs=226
- `2017__6s4`: year=2017, family=6s4, tier=timeout, ANDs=2451, XORs=43
- `2017__oc8051gma4pc`: year=2017, family=oc, tier=timeout, ANDs=10847, XORs=375
- `2020__arbitrated_top_n4_w8_d64_e0`: year=2020, family=arbitrated_top_n, tier=timeout, ANDs=13326, XORs=248
- `2019__arbitrated_top_n2_w128_d64_e0`: year=2019, family=arbitrated_top_n, tier=timeout, ANDs=84637, XORs=260
- `2019__picorv32_mutAY_nomem-p7`: year=2019, family=picorv, tier=timeout, ANDs=48005, XORs=1145
- `2020__picorv32_mutAY_nomem-p6`: year=2020, family=picorv, tier=timeout, ANDs=47918, XORs=1147
- `2017__6s218b2950`: year=2017, family=6s218b2950, tier=timeout, ANDs=461595, XORs=16739

**Reference only (1)**

- `2025__Problem14_label53`: year=2025, family=Problem, tier=timeout, ANDs=193575, XORs=39476


### Static structure

Cliff delta is positive when the feature tends to be larger in the candidate-favoured group. Values below about 0.33 are weak effects.

| Feature | Candidate-favoured median | Reference-favoured median | Cliff delta |
|---|---:|---:|---:|
| file bytes | 177073.000 | 41126.000 | 0.250 |
| AIG ANDs | 33688.000 | 11592.000 | 0.128 |
| recognized XORs | 1535.000 | 288.000 | 0.080 |
| XAG AND reduction | 0.124 | 0.076 | 0.018 |
| next-cone XORs | 900.000 | 288.000 | 0.014 |
| next-cone XOR density | 0.032 | 0.025 | 0.011 |
| bad-cone XORs | 10.000 | 132.000 | -0.121 |
| bad-cone XOR density | 0.008 | 0.037 | -0.089 |
| shared-cone XORs | 0.000 | 2.000 | -0.144 |

### Repeated decisive families

| Family | Candidate/reference favoured |
|---|---:|
| yosyshq_appnote_ | 42/2 |
| oski | 38/0 |
| dspfilters_fastfir_second | 36/0 |
| oc | 18/10 |
| arbitrated_top_n | 27/0 |
| Problem | 18/2 |
| picorv | 18/0 |
| circular_pointer_top_w | 13/0 |
| shift_register_top_w | 12/0 |
| a | 5/4 |
| pc_sfifo_ | 8/0 |
| cal | 7/0 |
| microban_ | 5/0 |
| vgasim_imgfifo | 4/0 |
| intel | 4/0 |
| elevator_spec | 4/0 |
| qspiflash_dualflexpress_divfive | 3/0 |
| power | 3/0 |
| bob | 3/0 |
| xepic_a | 2/0 |

## MC translation=legacy/lift=sum-high vs XAG legacy

| Candidate-only | Reference-only | Speed wins | Speed losses | Close | Both unsolved |
|---:|---:|---:|---:|---:|---:|
| 6 | 1 | 30 | 19 | 0 | 45 |

### Outcome-discordant models

**Candidate only (6)**

- `2015__6s359r`: year=2015, family=6s359r, tier=timeout, ANDs=26537, XORs=953
- `2015__beemprdcell2f1`: year=2015, family=beemprdcell, tier=timeout, ANDs=801, XORs=23
- `2017__6s320rb1`: year=2017, family=6s320rb1, tier=timeout, ANDs=30349, XORs=256
- `2017__beemadd4b1`: year=2017, family=beemadd, tier=timeout, ANDs=872, XORs=116
- `2019__qspiflash_dualflexpress_divfive-p007`: year=2019, family=qspiflash_dualflexpress_divfive, tier=timeout, ANDs=2872, XORs=260
- `2020__zipcpu-zipmmu-p31`: year=2020, family=zipcpu, tier=timeout, ANDs=4622, XORs=429

**Reference only (1)**

- `2020__qspiflash_dualflexpress_divthree-p153`: year=2020, family=qspiflash_dualflexpress_divthree, tier=timeout, ANDs=2896, XORs=259


### Static structure

Cliff delta is positive when the feature tends to be larger in the candidate-favoured group. Values below about 0.33 are weak effects.

| Feature | Candidate-favoured median | Reference-favoured median | Cliff delta |
|---|---:|---:|---:|
| file bytes | 36026.500 | 32817.500 | 0.144 |
| AIG ANDs | 4566.000 | 3378.500 | 0.031 |
| recognized XORs | 245.500 | 207.000 | 0.110 |
| XAG AND reduction | 0.157 | 0.162 | 0.189 |
| next-cone XORs | 197.500 | 184.000 | 0.200 |
| next-cone XOR density | 0.065 | 0.054 | 0.282 |
| bad-cone XORs | 17.500 | 0.500 | 0.206 |
| bad-cone XOR density | 0.010 | 0.004 | 0.092 |
| shared-cone XORs | 0.000 | 0.000 | 0.117 |

### Repeated decisive families

| Family | Candidate/reference favoured |
|---|---:|
| arbitrated_top_n | 7/2 |
| qspiflash_dualflexpress_divthree | 2/3 |
| qspiflash_dualflexpress_divfive | 3/2 |
| cal | 3/0 |
| qspiflash_qflexpress_divfive | 1/1 |
| bob | 2/0 |
| benchmarks_output_btor | 2/0 |

### MC PDR-free preprocessing deltas

Values are median `sum-high / legacy` ratios. A Cliff delta near zero means that the structural change does not distinguish runtime winners.

| Probe delta | Candidate-favoured | Reference-favoured | Cliff delta |
|---|---:|---:|---:|
| eliminated variables | 0.997 | 0.997 | 0.033 |
| resolvents | 0.930 | 0.930 | 0.086 |
| resolvent literals | 0.986 | 0.959 | 0.147 |
| merge checks | 0.937 | 0.914 | 0.131 |
| output clauses | 0.994 | 0.997 | -0.058 |
| output literals | 1.008 | 1.003 | 0.156 |
| binary clauses | 1.057 | 1.023 | 0.036 |
| ternary clauses | 0.984 | 0.982 | 0.006 |
| long clauses | 0.972 | 0.970 | 0.022 |
| maximum clause size | 1.000 | 1.000 | 0.007 |

## Conclusion

No static feature or simple preprocessing delta currently separates winners with a medium or strong effect. The most visible MC signal is next-cone XOR density, but it is still weak. The next experiment should therefore strengthen the causal treatment (width-weighted BVE acceptance) before fitting an instance selector.
