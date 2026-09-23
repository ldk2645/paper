# Synthetic pilot report

Exploratory simulation only. No real-world or phase-transition claims.

Completed world runs: 40; elapsed seconds: 2.38.

Negative paired differences mean less inference error than the platform estimator.

| alpha | contrast | pairs | mean difference | pointwise 95% interval |
|---|---|---|---|---|
| 0.0 | survey-platform | 8 | 0.1101 | [0.0682, 0.1474] |
| 0.0 | fused-platform | 8 | 0.0119 | [-0.0235, 0.0440] |
| 0.0 | oracle-platform | 8 | -0.0826 | [-0.1084, -0.0585] |
| 0.25 | survey-platform | 8 | 0.0877 | [0.0451, 0.1252] |
| 0.25 | fused-platform | 8 | -0.0053 | [-0.0427, 0.0305] |
| 0.25 | oracle-platform | 8 | -0.1050 | [-0.1344, -0.0780] |
| 0.5 | survey-platform | 8 | -0.0521 | [-0.1056, 0.0082] |
| 0.5 | fused-platform | 8 | -0.0787 | [-0.1275, -0.0369] |
| 0.5 | oracle-platform | 8 | -0.2448 | [-0.2958, -0.1965] |
| 0.75 | survey-platform | 8 | -0.1116 | [-0.1599, -0.0641] |
| 0.75 | fused-platform | 8 | -0.0972 | [-0.1242, -0.0673] |
| 0.75 | oracle-platform | 8 | -0.3043 | [-0.3527, -0.2631] |
| 1.0 | survey-platform | 8 | -0.1400 | [-0.1875, -0.0985] |
| 1.0 | fused-platform | 8 | -0.1038 | [-0.1201, -0.0868] |
| 1.0 | oracle-platform | 8 | -0.3327 | [-0.3873, -0.2901] |

Oracle zero error follows from its definition; it is not a substantive finding.
A final observation window is not evidence of convergence. See late_window_shift in runs.csv.
No-feedback estimates share the same world; feedback comparisons use separate active-arm worlds.
A full-population platform signal and a smaller survey are not a matched-sample comparison.
