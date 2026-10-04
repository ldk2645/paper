# ODD: The Reverse Black Box and Government Responsiveness

Implementation version 0.4.0, 26 September 2026. The original governance question is restored: algorithm-mediated signals, delayed responses, amplification and trust feedback. This is a revised implementation, not a numerical replication of the earlier manuscript. Functions refer to `abm_jasss/model.py` and `governance.py`. Full numerical values are in `parameters.md` and each experiment's `resolved_design.json`. `configs/restored_core.json` enables the core; the older no-feedback configuration is a nested diagnostic baseline.

## 1. Purpose and patterns

The purpose is explanatory exploration of the reverse black box: when does algorithm-mediated attention constrain a government's ability to identify concerns and respond, and how do signal error, response delay, finite capacity and an unchanged ranking architecture contribute? Nonlinear transitions and persistent misalignment remain research questions. No empirical patterns have been fitted. Development runs assess implementation and structural dependence, not real populations. Preference measurement is a diagnostic intervention. The instantaneous preference oracle does not reveal ranking rules and is not an algorithm-transparency treatment. A separate two-factor transparency experiment has not yet been implemented.

## 2. Entities, state variables and scales

There are N individuals, one platform, and one governmental actor. Individuals have a K-dimensional preference vector p_i summing to one, fixed interaction propensity q_i, baseline and current trust, and a dominant-exposure topic/streak. No social network or spatial structure is included. Items have a topic, emotionality e_j, heat h_j, birth step and source code (ordinary=0, routine/communication=1, targeted reply=2). Topics have no substantive real-world labels. The fixed government agenda is a separately specified subset with a target attention share. It is not a definition of public preference or welfare.

The platform maintains the active item pool. The observer maintains a rolling activity window, held estimates, delayed observation deliveries and delayed official posts. Discrete steps are abstract recommendation rounds, with no empirical mapping to days. Items can be recommended to the same individual repeatedly. Population membership is fixed.

## 3. Process overview and scheduling

`simulate` executes steps t = 0,...,T−1:

1. In the restored `respond` policy, publish a routine agenda item at its interval and execute due topic responses: multiply ordinary-content heat on the target topic by response_heat_retention and optionally publish a reply. In `communicate`, publish previously scheduled posts. Add ordinary arrivals.
2. Compute population truth P(t) from preferences before this round's drift. Rank available items, allocate up to B distinct items per individual, count exposures and draw interactions. Add interactions to item heat.
3. Add the selected platform panel's activity counts to the rolling window. At observation steps, form platform, survey and fused estimates; queue delivery at t + observation_delay.
4. Deliver observations and hold them until replaced. Update the instantaneous oracle to P(t). Under `communicate`, queue a post sampled from the active estimate. Under enabled `respond`, monitor its topic values against a threshold and queue up to response_capacity eligible topics for t + government_delay. Delay is at least one step.
5. Update trust using this round's exposures and the pre-drift preferences, then record truth, estimates, agenda measures, trust, exposures and action diagnostics. Trust affects interactions only from the next round.
6. Update individual preferences if drift is enabled. Decay heat and remove expired or insufficiently active items.

Observations and government decisions occur at step zero and every respective interval. With zero observation delay, the current observation is available for the current decision. With positive observation delay, uniform initial estimates can trigger responses before the first observation arrives; oracle information is immediate. Timing experiments must distinguish these initial-prior actions. The core pilot uses zero observation delay. The initial item pool is created before step zero's ordinary arrivals. Last-step drift affects no recorded state because the horizon has ended.

## 4. Design concepts

**Basic principles.** Recommendation combines popularity and individual relevance. Topic emotionality can affect interaction independently of preferences and content source. Exposure and aggregate latent preference are distinct distributions.

**Emergence.** Attention concentration, sustained agenda shortfalls and inference error may emerge from positive feedback competing with delayed topic responses. Their occurrence, necessity of emotion, and whether trust shifts a transition must be tested. **Adaptation.** Preference and trust changes are stipulated mechanisms, not estimated learning. Government has no fitted adaptive calibration in this version. **Objectives and sensing.** Exposure is assumed to be consumption. Government monitors only the active information stream, except the oracle benchmark. Its routine communication seeks a separately specified agenda. Response heat modulation represents a constrained assumed intervention, not an empirically measured response effect.

**Interaction and collectives.** Individuals interact indirectly through shared heat. Trust changes source-specific interaction propensities. **Stochasticity.** NumPy SeedSequence spawns nine streams in fixed order: initialization, content, ranking, interaction, survey, panel, government, trust, response_decisions. The first seven retain the earlier stream identities. Measurement changes cannot affect no-feedback worlds. Feedback worlds share seed identifiers but divergent item pools prevent perfectly synchronized common-random-number trajectories.

**Observation.** Governance diagnostics distinguish agenda attention/gap, attention–preference mismatch, inference error, preference drift, trust mean/spread, response publication/exposure and episodes above a specified off-agenda attention threshold. Formal primary outcomes remain to be frozen. A final window is not assumed to be a steady state. Episodes still active at the horizon are right-censored, not evidence of irreversible lock-in.

## 5. Initialization

If population_weights are supplied, normalize them to w; otherwise draw w ~ Dirichlet(c_pop,...,c_pop). Draw p_i ~ Dirichlet(K c_pref w). Population truth is the realized mean of individual p_i, not the generating w. Draw q_i by clipping Normal(interaction_mean, interaction_sd) to [0,1]. These draws use the initialization stream.

Draw a fixed platform panel uniformly without replacement, or use all individuals if platform_panel_size = 0. All held estimates start uniform. Streaks are zero, previous dominant topics are −1. Content supply defaults to uniform topics; supplied weights are normalized. Create initial_items at birth time zero with zero heat. Source is nonofficial. No burn-in or empirical calibration is applied.

Draw baseline trust independently as a clipped Normal(initial_trust_mean, initial_trust_sd), then copy it to current trust. Response pending queues and threshold streaks start empty/zero. The restored core uses a symmetric population target for continuity with the original scenario, while asymmetric targets remain configurable and necessary structural checks.

## 6. Input data

No empirical data enter the model. Configuration values are transparent modeling assumptions, not measured parameters. JSON configurations, seeds, environment metadata and source snapshots define each experiment. Earlier manuscript outputs are not input data or calibration targets.

## 7. Submodels

### Content and recommendation

Choose ordinary topics from supply weights. Communication topics follow a queued estimate; routine topics cycle through agenda_topics; response topics equal their queued target. Let μ_k = emotion_mean + emotion_advantage × 1[k = advantaged_topic]. Draw e_j ~ Beta(μ_k c_emotion, (1−μ_k)c_emotion). For official items, non-null official_emotion_mean overrides μ_k. This is a mean of a Beta distribution, not a fixed item intensity as in the legacy model. Full emotion equalization sets emotion_advantage=0 and official_emotion_mean=null; removing only topic advantage retains the source difference.

Transform pre-round heat as H_j = log(1+h_j)/max_l log(1+h_l), using all zeros when the maximum is zero. Relevance is cosine similarity to the topic's one-hot vector: R_ij = p_ik/||p_i||_2. Score S_ij = α H_j + (1−α) R_ij.

Top-K selects the highest scores with independent uniform random priorities for exact ties, without perturbing unequal scores. Softmax uses Gumbel top-K on S_ij/temperature, sampling distinct items without replacement; it does not make B independent draws with replacement. All selected items count equally as consumed exposures.

Interactions are Bernoulli(clip(q_i e_j φ_ij,0,1)), with φ_ij = 1 + s(2 trust_i−1) for official sources and 1 − s(2 trust_i−1) for ordinary sources; s=trust_feedback_strength. Setting s=0 removes this feedback without freezing trust. Add interactions to heat. At round end multiply heat by heat_retention. Keep an item exactly when `(heat >= heat_floor OR age_rounds < cold_start_rounds) AND age_rounds < max_item_age`, age_rounds=t−birth+1. Protection guarantees eligibility, not actual exposure; max age is a hard cap. Restored core uses two protection rounds; the numerical difference from the earlier one-round pilot is explicit. Setting α=0 removes heat from ranking but retains this heat-dependent survival channel; a full removal of heat-mediated selection also requires age-only retention, such as heat_floor=0.

### Information and estimates

Truth is P(t) = N^−1 Σ_i p_i(t). The platform estimate is normalized exposure or interaction counts summed over the last observation_window rounds for the fixed panel. Early windows contain only available rounds; zero counts map to uniform. Survey and platform observation share update intervals and delivery delay, but the platform averages historical activity while the survey measures preferences at the observation step.

At each observation, sample survey_size individuals without replacement. With zero selection bias sampling is uniform; otherwise selection weights are proportional to exp(survey_selection_bias × p_i,advantaged_topic). These are sequential weighted sampling weights, not marginal inclusion probabilities. Reports equal current preferences in the idealized baseline. With noise, add independent Normal(0, survey_noise_sd), clip negative components and renormalize each report; an all-zero report becomes uniform. Average reports. Samples are redrawn each observation, whereas the platform panel is fixed.

The fused estimate is (1−fusion_weight) × platform + fusion_weight × survey. No weight is optimized on the reported seeds. Delivered estimates are held until replaced. The oracle uses instantaneous P(t), without observation delay; it is not a timing-matched empirical estimator. A uniform prior is recorded as an additional naive benchmark.

### Preference drift and government feedback

`update_preferences` finds each individual's unique modal exposure topic. A tie or no exposure resets the streak; a repeated unique topic increments it. When streak >= drift_threshold, p_i becomes (1−drift_rate)p_i + drift_rate × onehot(topic). The update occurs every qualifying round, not only at threshold crossing. Zero drift leaves all preferences unchanged.

Under government_policy = none, all estimators evaluate one shared world. Under communicate, create a separate world for each active estimator. Every government_interval rounds, queue one future official item with topic probabilities equal to the active estimate at decision time. Draw its topic/emotion upon publication. This communication action has no direct heat suppression or welfare allocation. Trust can be enabled independently. Other estimators within a feedback world are diagnostic; cross-policy summaries use only each world's active estimator.

Under `respond`, routine posts appear every routine_publication_interval. Eligible response signals strictly exceed response_threshold. `hard` admits all topics, `selective` only agenda topics, and `wait` requires response_wait_observations consecutive monitoring calls above threshold. Up to response_capacity new topics are selected by descending signal with random exact ties. Pending topics cannot be scheduled twice, but may be scheduled again upon delivery. At execution, only ordinary items on that topic receive the heat multiplier. Reply publication is optional and does not guarantee exposure. Monitor capacity is a scheduling constraint, not a welfare budget; long delay also holds topics in the pending queue, so timing comparisons include this throughput consequence.

`response_enabled=false` removes targeted scheduling but preserves routine publication. `response_heat_retention=1` retains scheduling and replies but no forced heat change. `response_publish=false` isolates heat modulation without replies. Events preserve signal, trigger/due/execution times, current target preference, and immediate before/after heat. These immediate changes are imposed by the rule; their existence does not prove an effective real-world policy.

### Trust feedback

`governance.trust_update` anchors targets to b_i=logit(initial trust_i), clipping baseline probabilities to [10^−12,1−10^−12] for computation. Under the exposure rule, target latent value is b_i + g_official(O_i−0.25) − g_offagenda X_i + g_response R, where O_i is official exposure, X_i is off-agenda exposure and R is the imposed aggregate heat reduction fraction among executed targets (zero if no positive heat). Under the alternative alignment rule it is b_i + g_alignment(L_i−0.5) + g_response R, where L_i=1−TV(individual exposure distribution,p_i before drift). Apply a logistic function and relax trust toward the target at trust_update_rate. Bounds are enforced numerically.

The exposure penalty encodes the legacy directional assumption; a decline under that rule alone is not independent evidence for trust erosion. The core sets g_response=0, avoiding an automatic direct trust reward for a heat action. Coefficients are uncalibrated; this is not transplantation of cross-sectional standardized regressions or of the old learning-cost equation. Compare rules and feedback-off controls before assigning trust a mechanism role. Its value as an early-warning signal remains untested.

### Measures and inference

E(t) = 0.5 Σ_k |estimate_k(t)−P_k(t)|. Initial-reference error instead uses P(0). Attention error uses current exposure shares against P(t). Uniform-prior error compares 1/K with P(t). Top-topic accuracy is the fraction of estimated maximizers that are also true maximizers, corresponding to uniform tie-breaking. Numerical ties use absolute tolerance 10^−12. Preference change is TV(P(t),P(0)). Late-window shift compares last and first halves of the final window; it is only a diagnostic.

`cli.aggregate` treats seeds as independent replicates within a condition, never time steps or agents. It uses 2,000 percentile bootstrap resamples of run means, analysis seed 90210, and reports pointwise intervals and Monte Carlo standard errors. Estimator contrasts resample within-seed differences. Results across α and scenarios reuse seeds and are correlated; no simultaneous coverage or multiplicity adjustment is claimed. Eight-seed development intervals are preliminary. Feedback runs require separate worlds for each policy.

Agenda gap = agenda_target_share − observed agenda attention; agenda_shortfall=max(0,1−agenda_attention/agenda_target_share). Neither measures public welfare. Agenda-share variance is recorded by that name, not called stability. A storm is a maximal consecutive interval with maximum off-agenda topic attention > storm_threshold; threshold and label are descriptive assumptions. `governance_metrics.csv` uses seed bootstrap seed90211; `run_core_suite.py` uses paired scenario differences, seed90212. Quantities from different feedback worlds have endogenous population preferences and must not be read as equal-target causal accuracy comparisons without additional design.

### Response-target diagnostics added for the paper outline

`response_diagnostics.response_target_diagnostics` reads saved trajectories and events without changing the simulated process. Executed actions with the same trigger time τ and due/execution time u form a cohort. Normalize their topic counts to r and record TV(r,P_τ), TV(r,P_u), their signed difference, and TV(P_τ,P_u). With one action on topic k, target mismatch is 1−P_k. This describes topical focus, not resources, welfare, heat reduction, or a causal effect of delay. No-action worlds have missing conditional mismatch, never zero; pending cohorts remain censored and separate.

`scripts/analyze_response_targets.py` averages cohorts executed within the final window per world, then aggregates independent seed-level summaries with pointwise bootstrap intervals (2,000 resamples; analysis seed 90301). It reports the number of measured worlds, action counts, execution-step coverage and terminal pending actions. Attention and sensing errors use every step in the final window, so they have different conditioning from the response measure. In the current full-population, one-step, zero-delay platform baseline, the estimate equals current attention; the first two errors are identical by construction. The three distances are not an additive causal decomposition. Source files and analysis scripts are hashed in the separate analysis manifest.

## References and remaining validation

ODD structure follows [Grimm et al. (2020)](https://www.jasss.org/23/2/7.html); explanatory purpose follows [Edmonds et al. (2019)](https://www.jasss.org/22/3/6.html). These are methodological references, not a claim that all journal submission requirements have been fulfilled.

Implemented tests cover hand-calculable updates, distribution invariants, seed reproducibility, sampling isolation, tie handling, delayed publication, census measurement, serial/parallel equivalence and failure preservation. Empirical validation, independent reimplementation, label-permutation statistical checks, calibrated competing estimators, population/supply scaling and formal convergence analysis remain unfinished.

The revised suite also covers response timing/capacity, topic eligibility, separate reply/heat controls, trust-rule alternatives and terminal censoring. Algorithm-knowledge interventions, same-state upstream/downstream intervention experiments, continuation scans and phase-transition claims remain pending. The original core questions are preserved, while old numerical thresholds and mechanism-role conclusions are not hard-coded.
