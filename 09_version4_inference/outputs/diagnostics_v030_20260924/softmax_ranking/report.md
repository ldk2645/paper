# Synthetic pilot report

Exploratory simulation only. No real-world or phase-transition claims.

Completed world runs: 40; elapsed seconds: 2.25.

Negative paired differences mean less inference error than the platform estimator.

| alpha | contrast | pairs | mean difference | pointwise 95% interval |
|---|---|---|---|---|
| 0.0 | survey-platform | 8 | -0.0123 | [-0.0478, 0.0237] |
| 0.0 | fused-platform | 8 | -0.0297 | [-0.0504, -0.0094] |
| 0.0 | oracle-platform | 8 | -0.0927 | [-0.1203, -0.0665] |
| 0.25 | survey-platform | 8 | -0.0351 | [-0.0740, 0.0073] |
| 0.25 | fused-platform | 8 | -0.0430 | [-0.0639, -0.0194] |
| 0.25 | oracle-platform | 8 | -0.1155 | [-0.1470, -0.0827] |
| 0.5 | survey-platform | 8 | -0.0704 | [-0.1038, -0.0342] |
| 0.5 | fused-platform | 8 | -0.0665 | [-0.0822, -0.0494] |
| 0.5 | oracle-platform | 8 | -0.1508 | [-0.1779, -0.1224] |
| 0.75 | survey-platform | 8 | -0.1654 | [-0.2313, -0.1103] |
| 0.75 | fused-platform | 8 | -0.1148 | [-0.1452, -0.0889] |
| 0.75 | oracle-platform | 8 | -0.2459 | [-0.3107, -0.1941] |
| 1.0 | survey-platform | 8 | -0.2928 | [-0.3862, -0.2022] |
| 1.0 | fused-platform | 8 | -0.1803 | [-0.2221, -0.1362] |
| 1.0 | oracle-platform | 8 | -0.3733 | [-0.4681, -0.2866] |

Oracle zero error follows from its definition; it is not a substantive finding.
A final observation window is not evidence of convergence. See late_window_shift in runs.csv.
No-feedback estimates share the same world; feedback comparisons use separate active-arm worlds.
A full-population platform signal and a smaller survey are not a matched-sample comparison.
