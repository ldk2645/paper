# Synthetic pilot report

Exploratory simulation only. No real-world or phase-transition claims.

Completed world runs: 40; elapsed seconds: 2.13.

Negative paired differences mean less inference error than the platform estimator.

| alpha | contrast | pairs | mean difference | pointwise 95% interval |
|---|---|---|---|---|
| 0.0 | survey-platform | 8 | -0.0022 | [-0.0356, 0.0293] |
| 0.0 | fused-platform | 8 | -0.0249 | [-0.0430, -0.0064] |
| 0.0 | oracle-platform | 8 | -0.0826 | [-0.1084, -0.0585] |
| 0.25 | survey-platform | 8 | -0.0269 | [-0.0676, 0.0129] |
| 0.25 | fused-platform | 8 | -0.0403 | [-0.0611, -0.0183] |
| 0.25 | oracle-platform | 8 | -0.1074 | [-0.1409, -0.0774] |
| 0.5 | survey-platform | 8 | -0.1703 | [-0.2048, -0.1348] |
| 0.5 | fused-platform | 8 | -0.1227 | [-0.1434, -0.1037] |
| 0.5 | oracle-platform | 8 | -0.2507 | [-0.2847, -0.2182] |
| 0.75 | survey-platform | 8 | -0.2495 | [-0.2964, -0.1999] |
| 0.75 | fused-platform | 8 | -0.1639 | [-0.1876, -0.1415] |
| 0.75 | oracle-platform | 8 | -0.3300 | [-0.3728, -0.2880] |
| 1.0 | survey-platform | 8 | -0.2689 | [-0.3150, -0.2209] |
| 1.0 | fused-platform | 8 | -0.1714 | [-0.1954, -0.1470] |
| 1.0 | oracle-platform | 8 | -0.3494 | [-0.3950, -0.3030] |

Oracle zero error follows from its definition; it is not a substantive finding.
A final observation window is not evidence of convergence. See late_window_shift in runs.csv.
No-feedback estimates share the same world; feedback comparisons use separate active-arm worlds.
A full-population platform signal and a smaller survey are not a matched-sample comparison.
