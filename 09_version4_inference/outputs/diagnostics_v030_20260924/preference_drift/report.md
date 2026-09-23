# Synthetic pilot report

Exploratory simulation only. No real-world or phase-transition claims.

Completed world runs: 40; elapsed seconds: 2.40.

Negative paired differences mean less inference error than the platform estimator.

| alpha | contrast | pairs | mean difference | pointwise 95% interval |
|---|---|---|---|---|
| 0.0 | survey-platform | 8 | 0.1698 | [0.1524, 0.1860] |
| 0.0 | fused-platform | 8 | 0.0848 | [0.0759, 0.0927] |
| 0.0 | oracle-platform | 8 | -0.0003 | [-0.0003, -0.0002] |
| 0.25 | survey-platform | 8 | 0.1662 | [0.1481, 0.1820] |
| 0.25 | fused-platform | 8 | 0.0801 | [0.0711, 0.0883] |
| 0.25 | oracle-platform | 8 | -0.0073 | [-0.0108, -0.0044] |
| 0.5 | survey-platform | 8 | 0.0704 | [0.0406, 0.0965] |
| 0.5 | fused-platform | 8 | 0.0094 | [-0.0113, 0.0270] |
| 0.5 | oracle-platform | 8 | -0.0790 | [-0.1118, -0.0489] |
| 0.75 | survey-platform | 8 | -0.3926 | [-0.5005, -0.2956] |
| 0.75 | fused-platform | 8 | -0.2002 | [-0.2549, -0.1510] |
| 0.75 | oracle-platform | 8 | -0.4030 | [-0.5174, -0.2989] |
| 1.0 | survey-platform | 8 | -0.4312 | [-0.5710, -0.3186] |
| 1.0 | fused-platform | 8 | -0.2332 | [-0.2903, -0.1832] |
| 1.0 | oracle-platform | 8 | -0.4665 | [-0.5881, -0.3660] |

Oracle zero error follows from its definition; it is not a substantive finding.
A final observation window is not evidence of convergence. See late_window_shift in runs.csv.
No-feedback estimates share the same world; feedback comparisons use separate active-arm worlds.
A full-population platform signal and a smaller survey are not a matched-sample comparison.
