# Synthetic pilot report

Exploratory simulation only. No real-world or phase-transition claims.

Completed world runs: 40; elapsed seconds: 3.22.

Negative paired differences mean less inference error than the platform estimator.

| alpha | contrast | pairs | mean difference | pointwise 95% interval |
|---|---|---|---|---|
| 0.0 | survey-platform | 8 | -0.0022 | [-0.0356, 0.0293] |
| 0.0 | fused-platform | 8 | -0.0249 | [-0.0430, -0.0064] |
| 0.0 | oracle-platform | 8 | -0.0826 | [-0.1084, -0.0585] |
| 0.25 | survey-platform | 8 | -0.0253 | [-0.0675, 0.0164] |
| 0.25 | fused-platform | 8 | -0.0390 | [-0.0604, -0.0169] |
| 0.25 | oracle-platform | 8 | -0.1058 | [-0.1396, -0.0759] |
| 0.5 | survey-platform | 8 | -0.1433 | [-0.2034, -0.0840] |
| 0.5 | fused-platform | 8 | -0.1079 | [-0.1350, -0.0818] |
| 0.5 | oracle-platform | 8 | -0.2237 | [-0.2787, -0.1730] |
| 0.75 | survey-platform | 8 | -0.2841 | [-0.3712, -0.2061] |
| 0.75 | fused-platform | 8 | -0.1782 | [-0.2224, -0.1364] |
| 0.75 | oracle-platform | 8 | -0.3646 | [-0.4559, -0.2803] |
| 1.0 | survey-platform | 8 | -0.2519 | [-0.3162, -0.1828] |
| 1.0 | fused-platform | 8 | -0.1583 | [-0.1905, -0.1230] |
| 1.0 | oracle-platform | 8 | -0.3324 | [-0.3952, -0.2661] |

Oracle zero error follows from its definition; it is not a substantive finding.
A final observation window is not evidence of convergence. See late_window_shift in runs.csv.
No-feedback estimates share the same world; feedback comparisons use separate active-arm worlds.
A full-population platform signal and a smaller survey are not a matched-sample comparison.
