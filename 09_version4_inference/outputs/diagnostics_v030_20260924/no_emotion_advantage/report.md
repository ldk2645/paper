# Synthetic pilot report

Exploratory simulation only. No real-world or phase-transition claims.

Completed world runs: 40; elapsed seconds: 2.17.

Negative paired differences mean less inference error than the platform estimator.

| alpha | contrast | pairs | mean difference | pointwise 95% interval |
|---|---|---|---|---|
| 0.0 | survey-platform | 8 | -0.0022 | [-0.0356, 0.0293] |
| 0.0 | fused-platform | 8 | -0.0249 | [-0.0430, -0.0064] |
| 0.0 | oracle-platform | 8 | -0.0826 | [-0.1084, -0.0585] |
| 0.25 | survey-platform | 8 | -0.0261 | [-0.0638, 0.0109] |
| 0.25 | fused-platform | 8 | -0.0394 | [-0.0589, -0.0191] |
| 0.25 | oracle-platform | 8 | -0.1065 | [-0.1374, -0.0796] |
| 0.5 | survey-platform | 8 | -0.1150 | [-0.1578, -0.0758] |
| 0.5 | fused-platform | 8 | -0.0943 | [-0.1149, -0.0768] |
| 0.5 | oracle-platform | 8 | -0.1954 | [-0.2336, -0.1635] |
| 0.75 | survey-platform | 8 | -0.2050 | [-0.2418, -0.1650] |
| 0.75 | fused-platform | 8 | -0.1405 | [-0.1636, -0.1156] |
| 0.75 | oracle-platform | 8 | -0.2854 | [-0.3201, -0.2465] |
| 1.0 | survey-platform | 8 | -0.2231 | [-0.2583, -0.1900] |
| 1.0 | fused-platform | 8 | -0.1504 | [-0.1695, -0.1342] |
| 1.0 | oracle-platform | 8 | -0.3035 | [-0.3358, -0.2747] |

Oracle zero error follows from its definition; it is not a substantive finding.
A final observation window is not evidence of convergence. See late_window_shift in runs.csv.
No-feedback estimates share the same world; feedback comparisons use separate active-arm worlds.
A full-population platform signal and a smaller survey are not a matched-sample comparison.
