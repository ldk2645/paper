# Synthetic pilot report

Exploratory simulation only. No real-world or phase-transition claims.

Completed world runs: 40; elapsed seconds: 2.45.

Negative paired differences mean less inference error than the platform estimator.

| alpha | contrast | pairs | mean difference | pointwise 95% interval |
|---|---|---|---|---|
| 0.0 | survey-platform | 8 | -0.0022 | [-0.0356, 0.0293] |
| 0.0 | fused-platform | 8 | -0.0249 | [-0.0430, -0.0064] |
| 0.0 | oracle-platform | 8 | -0.0826 | [-0.1084, -0.0585] |
| 0.25 | survey-platform | 8 | -0.0246 | [-0.0627, 0.0121] |
| 0.25 | fused-platform | 8 | -0.0395 | [-0.0588, -0.0188] |
| 0.25 | oracle-platform | 8 | -0.1050 | [-0.1344, -0.0780] |
| 0.5 | survey-platform | 8 | -0.1644 | [-0.2223, -0.1050] |
| 0.5 | fused-platform | 8 | -0.1149 | [-0.1410, -0.0893] |
| 0.5 | oracle-platform | 8 | -0.2448 | [-0.2958, -0.1965] |
| 0.75 | survey-platform | 8 | -0.2239 | [-0.2715, -0.1816] |
| 0.75 | fused-platform | 8 | -0.1487 | [-0.1715, -0.1257] |
| 0.75 | oracle-platform | 8 | -0.3043 | [-0.3527, -0.2631] |
| 1.0 | survey-platform | 8 | -0.2523 | [-0.3101, -0.2056] |
| 1.0 | fused-platform | 8 | -0.1627 | [-0.1910, -0.1411] |
| 1.0 | oracle-platform | 8 | -0.3327 | [-0.3873, -0.2901] |

Oracle zero error follows from its definition; it is not a substantive finding.
A final observation window is not evidence of convergence. See late_window_shift in runs.csv.
No-feedback estimates share the same world; feedback comparisons use separate active-arm worlds.
A full-population platform signal and a smaller survey are not a matched-sample comparison.
