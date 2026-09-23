# Synthetic pilot report

Exploratory simulation only. No real-world or phase-transition claims.

Completed world runs: 40; elapsed seconds: 2.30.

Negative paired differences mean less inference error than the platform estimator.

| alpha | contrast | pairs | mean difference | pointwise 95% interval |
|---|---|---|---|---|
| 0.0 | survey-platform | 8 | -0.1276 | [-0.2231, -0.0406] |
| 0.0 | fused-platform | 8 | -0.0933 | [-0.1415, -0.0465] |
| 0.0 | oracle-platform | 8 | -0.2081 | [-0.2994, -0.1249] |
| 0.25 | survey-platform | 8 | -0.1163 | [-0.1982, -0.0443] |
| 0.25 | fused-platform | 8 | -0.0906 | [-0.1300, -0.0565] |
| 0.25 | oracle-platform | 8 | -0.1967 | [-0.2727, -0.1306] |
| 0.5 | survey-platform | 8 | -0.1673 | [-0.2483, -0.0894] |
| 0.5 | fused-platform | 8 | -0.1155 | [-0.1563, -0.0811] |
| 0.5 | oracle-platform | 8 | -0.2477 | [-0.3254, -0.1819] |
| 0.75 | survey-platform | 8 | -0.2229 | [-0.2710, -0.1804] |
| 0.75 | fused-platform | 8 | -0.1481 | [-0.1709, -0.1253] |
| 0.75 | oracle-platform | 8 | -0.3033 | [-0.3519, -0.2620] |
| 1.0 | survey-platform | 8 | -0.2523 | [-0.3100, -0.2057] |
| 1.0 | fused-platform | 8 | -0.1627 | [-0.1912, -0.1411] |
| 1.0 | oracle-platform | 8 | -0.3328 | [-0.3875, -0.2901] |

Oracle zero error follows from its definition; it is not a substantive finding.
A final observation window is not evidence of convergence. See late_window_shift in runs.csv.
No-feedback estimates share the same world; feedback comparisons use separate active-arm worlds.
A full-population platform signal and a smaller survey are not a matched-sample comparison.
