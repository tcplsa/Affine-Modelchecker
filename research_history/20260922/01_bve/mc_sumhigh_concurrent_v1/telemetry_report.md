# Strict-cohort MC BVE telemetry

Telemetry ratios use one structural record per model, including unresolved models. Runtime ratios are geometric means over common-solved seed blocks. Correlations use the common-solved subset and are Pearson correlations between per-model log telemetry and log runtime ratios.

## All strict-cohort models

Models in scope: 556.

| Observable | Pairs | Geo ratio | Median ratio | Correlation with log runtime ratio |
|---|---:|---:|---:|---:|
| Residual clauses | 478 | 0.995 | 0.999 | +0.079 |
| Residual literals | 478 | 1.004 | 0.996 | +0.015 |
| Retained resolvents | 477 | 0.926 | 0.927 | -0.066 |
| Resolvent literals | 477 | 0.980 | 0.964 | -0.036 |
| Maximum resolvent width | 477 | 0.991 | 1.000 | -0.055 |
| Estimated merge checks | 477 | 0.915 | 0.911 | -0.031 |

## Historical-fast tier

Models in scope: 120.

| Observable | Pairs | Geo ratio | Median ratio | Correlation with log runtime ratio |
|---|---:|---:|---:|---:|
| Residual clauses | 120 | 1.002 | 0.999 | -0.018 |
| Residual literals | 120 | 1.008 | 0.991 | -0.033 |
| Retained resolvents | 120 | 0.924 | 0.928 | -0.051 |
| Resolvent literals | 120 | 0.971 | 0.968 | -0.110 |
| Maximum resolvent width | 120 | 1.002 | 1.000 | +0.060 |
| Estimated merge checks | 120 | 0.906 | 0.908 | +0.016 |

## Historical-timeout tier

Models in scope: 120.

| Observable | Pairs | Geo ratio | Median ratio | Correlation with log runtime ratio |
|---|---:|---:|---:|---:|
| Residual clauses | 42 | 1.024 | 1.001 | -0.169 |
| Residual literals | 42 | 1.040 | 1.006 | -0.143 |
| Retained resolvents | 42 | 0.910 | 0.923 | -0.192 |
| Resolvent literals | 42 | 0.992 | 0.985 | +0.042 |
| Maximum resolvent width | 42 | 0.957 | 1.000 | +0.119 |
| Estimated merge checks | 42 | 0.913 | 0.912 | -0.212 |
