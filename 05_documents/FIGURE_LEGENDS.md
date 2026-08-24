# Figure legends

## Fig. 2 | Recommendation weighting produces a transition in system-level outcomes.

**a–d,** Full-model steady-state agenda divergence (**a**), variance of agenda divergence (**b**), storm time share (**c**) and mean government trust (**d**) across recommendation-weight parameter α. Lines show means across 50 common random seeds and shaded regions show two-sided 95% *t* confidence intervals calculated separately at each α. The gold band denotes the 95% seed-block bootstrap interval for the critical point (0.55–0.60), and the dashed line marks the point estimate (αc=0.60). Each run contains 300 public agents and 300 simulation steps; steady-state metrics use the final 100 steps. Source data: `03_data/figures/source_data/fig2_phase_source_data.csv`.

## Fig. 3 | Seed-block resampling supports the identified critical point.

**a,** Mean full-model agenda divergence (open circles) with two-sided 95% *t* confidence intervals and a centred three-point rolling mean. **b,** Numerical gradient of the smoothed curve; the largest positive internal-grid gradient identifies αc. **c,** Distribution of αc across 5,000 bootstrap draws that resample complete seed-level α curves. The gold region shows the 95% interval and the vertical line shows αc=0.60. Fifty common random seeds were used. Source data: `03_data/figures/source_data/fig3_critical_curve_source_data.csv` and `fig3_critical_bootstrap_source_data.csv`.

## Fig. 4 | Paired ablations identify mechanism-specific contributions across α.

**a–d,** Paired differences between each ablation and the Full model (ablation−Full) for agenda divergence (**a**), divergence variance (**b**), storm time share (**c**) and government trust (**d**). Lines show mean differences across 50 matched random seeds; shaded regions show 95% confidence intervals from 10,000 paired bootstrap resamples. Conditions remove the emotional advantage of off-agenda information, preference drift, the effective heat-suppression component of government response, or trust-to-interaction feedback. In the no-trust condition the trust state is still updated and measured; only `trust_feedback_strength` is set to zero. The horizontal line denotes no difference; the gold region marks the Full-model critical interval. Source data: `03_data/figures/source_data/fig4_ablation_source_data.csv`.

## Fig. 5 | Representative trajectories reveal the temporal form of the transition.

**a–c,** Agenda divergence (**a**), government trust (**b**) and the peak off-agenda topic share (**c**) for α=0.30, 0.55 and 0.70. Thin lines show step-level values and thick lines show centred seven-step rolling means. The grey region is the final 100-step steady-state window; the dashed horizontal line in **c** is the storm threshold (0.30). Seed 73048 was selected before plotting by minimizing the summed squared standardized distance to the Full-model cell means across the three displayed α values and four primary outcomes. This panel is representative rather than inferential. Source data: `03_data/figures/source_data/fig5_trajectory_source_data.csv` and `representative_seed_selection.csv`.

## Fig. 6 | Public datasets provide mechanism-level consistency checks.

**a,** 2022 World Bank GTMI and 2023 OECD national-government trust for 30 matched countries. **b,** Spearman correlations between five GovTech measures from the 2020, 2022 and 2025 releases and the same 2023 trust outcome; intervals are from 5,000 country-level bootstrap resamples, with all 15 raw and Holm-adjusted *P* values supplied in the source table. **c,** Cluster-robust OLS estimates for headline emotion intensity and negative valence in 256,626 news–platform observations, clustered by 87,492 news identifiers and adjusted for headline length, topic, platform and month. **d,** Mean share of 24-h feedback across 27,244 public-affairs articles; shading shows pointwise 95% intervals across articles. These observational analyses test consistency, not causality or structural calibration. Source data: `03_data/figures/source_data/` and `03_data/external/processed/`.

## Extended Data Fig. 1 | Mean trust and between-public dispersion over time.

**a–c,** Mean government trust for α=0.30 (**a**), 0.55 (**b**) and 0.70 (**c**) in representative seed 73048. Shading denotes ±1 population SD across the 300 public agents at each step, not uncertainty across random seeds. Source data: `03_data/figures/source_data/fig5_trajectory_source_data.csv`.

## Extended Data Fig. 2 | Storm characteristics increase across the recommendation-weight scan.

**a–c,** Steady-state storm frequency per 100 steps (**a**), mean storm peak (**b**) and mean storm duration (**c**) in the Full model. Lines show means across 50 common random seeds; shaded regions are two-sided 95% *t* confidence intervals calculated separately at each α. The gold band marks the Full-model critical interval. Source data: `03_data/figures/source_data/figs_storm_source_data.csv`.

## Supplementary Fig. S1 | Public-affairs feedback has an initial burst and a heavier late tail than the geometric comparator.

**a,** Mean fraction of each article’s 24-h feedback occurring in successive 20-min bins, shown on a logarithmic axis; shading is the pointwise 95% normal-approximation interval across 27,244 Facebook Obama and Palestine articles. The dashed curve is a deterministic λ=0.95 geometric sequence normalized across the same 72-bin window; it is illustrative and does not equate one simulation step with 20 min. **b,** Cumulative empirical and comparator shares. Empirical markers at 6 h and 12 h show two-sided 95% *t* intervals across articles. Source data: `03_data/external/source_data/FigS1_attention_decay_source_data.csv` and `FigS1_attention_decay_landmarks.csv`.

## Supplementary Fig. S2 | Formal sensitivity tests separate critical-point stability from outcome depth.

**a,** Detected critical α for 14 one-parameter perturbations. **b,** Detected critical α for the default model, two alternative response strategies, the no-effective-response ablation and three execution-order variants. Points are estimates from the mean agenda-divergence curve; horizontal intervals are 95% seed-block bootstrap intervals from 5,000 resamples of complete α curves. The dashed line and grey band denote the default estimate and interval. **c,** Mean agenda-divergence curves for the three built-in response strategies and the no-effective-response reference; shading shows two-sided 95% *t* intervals across 50 common random seeds at each of 21 α values. Each run contains 300 public agents and 300 steps. Source data: `03_data/sensitivity/source_data/`.
