# Version 3 pilot figure contract

Core conclusion: A 30% instantaneous response-cooling rule lowers the 14-day post-response heat burden, but this 10-seed pilot does not establish a stable early-versus-late modification across α; daily government publication also does not guarantee exposure.

Figure archetype: quantitative grid with one primary paired-effect panel and three supporting panels.

Target journal/output: broad Nature-family submission style; editable SVG and PDF plus 600 dpi TIFF and PNG preview.

Backend: Python only.

Final size: 183 mm double-column width, approximately 140 mm height.

Panel map:

- a: raw `log(1 + 14-day petition-heat AUC)` across α for the four delay × multiplier cells.
- b: paired cooling benefit, defined as `logAUC(1.00) - logAUC(0.70)`, by α and delay with seed-level uncertainty.
- c: early-minus-late difference-in-differences by α and equally weighted across α; the zero line answers whether timing modifies cooling.
- d: routine-government reach across α, with the invariant `300/300` publication days stated separately from observed exposure.

Evidence hierarchy:

- hero evidence: panel b, because the 1.00 and 0.70 outcomes are matched by seed.
- validation evidence: panel c, because it is the prespecified timing interaction rather than a selected within-cell comparison.
- controls/robustness: panel a shows the untransformed experimental cells after the declared log transform; panel d audits publication versus exposure.

Statistics needed: 10 common random seeds; arithmetic mean; seed-block bootstrap 95% confidence interval; exact two-sided sign-flip test; Hedges-corrected paired effect size; Holm correction for α-stratified interactions. Intervals describe Monte Carlo seed variation, not population sampling uncertainty.

Source data needed: complete 120-run summary, seed-level paired cooling effects, seed-level timing interactions, and statistics output. No rows may be sampled for plotting convenience.

Image-integrity notes: no raster source images, crops, local contrast changes, pseudo-colour, or stitching. SVG text must remain editable.

Reviewer risk: `response_heat_multiplier=0.70` is an encoded counterfactual mechanism, not an estimated real-world effect; `1.00` still publishes a response; the pilot is underpowered for subtle timing interactions; official information is created with inherited V1/V2 content parameters and may receive little recommendation exposure; no real Weibo–Leader Message Board pair is used in this figure.
