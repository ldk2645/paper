# Synthetic pilot report

Exploratory simulation only. No real-world or phase-transition claims.

Completed world runs: 36; elapsed seconds: 0.89.

Negative paired differences mean less inference error than the platform estimator.

| alpha | contrast | pairs | mean difference | pointwise 95% interval |
|---|---|---|---|---|
| 0.0 | survey-platform | 3 | -0.0247 | [-0.0502, 0.0250] |
| 0.0 | fused-platform | 3 | -0.0691 | [-0.0882, -0.0330] |
| 0.0 | oracle-platform | 3 | -0.1691 | [-0.1877, -0.1342] |
| 0.5 | survey-platform | 3 | 0.0333 | [-0.0567, 0.1231] |
| 0.5 | fused-platform | 3 | 0.0006 | [-0.0339, 0.0312] |
| 0.5 | oracle-platform | 3 | -0.0743 | [-0.0951, -0.0453] |
| 1.0 | survey-platform | 3 | -0.2499 | [-0.2882, -0.1771] |
| 1.0 | fused-platform | 3 | -0.1337 | [-0.1504, -0.1060] |
| 1.0 | oracle-platform | 3 | -0.2687 | [-0.3007, -0.2067] |

Oracle zero error follows from its definition; it is not a substantive finding.
A final observation window is not evidence of convergence. See late_window_shift in runs.csv.
No-feedback estimates share the same world; feedback comparisons use separate active-arm worlds.
A full-population platform signal and a smaller survey are not a matched-sample comparison.
