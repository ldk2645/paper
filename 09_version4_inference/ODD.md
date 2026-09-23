# ODD: Inferring Public Priorities under Algorithmic Recommendation

Implementation version 0.3.0, 24 September 2026. This describes the implemented synthetic model, not a replication of the earlier manuscript. Functions refer to `abm_jasss/model.py`. Full numerical values are in `parameters.md` and each experiment's `resolved_design.json`.

## 1. Purpose and patterns

The purpose is explanatory exploration: when does algorithm-mediated activity misrepresent a population's topic preferences, and when can finite preference surveys improve inference? No empirical target patterns have been fitted. Development runs assess implementation and structural dependence; they do not validate real populations. The instantaneous oracle is a definitional benchmark, not a substantive discovery.

## 2. Entities, state variables and scales

There are N individuals, one platform, and one governmental observer. Individuals have a K-dimensional preference vector p_i summing to one, a fixed interaction propensity q_i, and a dominant-exposure topic/streak. No social network or spatial structure is included. Content items have a topic, emotionality e_j, heat h_j, birth step and official/nonofficial source flag. Topics have no substantive real-world labels.

The platform maintains the active item pool. The observer maintains a rolling activity window, held estimates, delayed observation deliveries and delayed official posts. Discrete steps are abstract recommendation rounds, with no empirical mapping to days. Items can be recommended to the same individual repeatedly. Population membership is fixed.

## 3. Process overview and scheduling

`simulate` executes steps t = 0,...,T−1:

1. Publish previously scheduled official items due at t; add ordinary arrivals.
2. Compute population truth P(t) from preferences before this round's drift. Rank available items, allocate up to B distinct items per individual, count exposures and draw interactions. Add interactions to item heat.
3. Add the selected platform panel's activity counts to the rolling window. At observation steps, form platform, survey and fused estimates; queue delivery at t + observation_delay.
4. Deliver due observations and hold them until replaced. Update the instantaneous oracle to P(t). At government decision steps, schedule a post for t + government_delay using the active estimator's distribution. Delay is at least one step.
5. Record truth, estimates, errors, exposures, interactions and pool diagnostics.
6. Update individual preferences if drift is enabled. Decay heat and remove expired or insufficiently active items.

Observations and government decisions occur at step zero and every respective interval. With zero observation delay, the current observation is available for the current decision. The initial item pool is created before step zero's ordinary arrivals. Last-step drift affects no recorded state because the horizon has ended.

## 4. Design concepts

**Basic principles.** Recommendation combines popularity and individual relevance. Topic emotionality can affect interaction independently of preferences and content source. Exposure and aggregate latent preference are distinct distributions.

**Emergence.** Concentrated attention and inference error may emerge from ranking, finite attention, content turnover and interaction. They are not guaranteed by the experiment design. **Adaptation.** Optional exposure-driven preference change is a stipulated rule, not estimated learning. The observer has no fitted adaptive calibration in this version. **Objectives and sensing.** Individuals receive ranked content; no utility maximization or explicit choice to consume is modeled. Exposure is assumed to be consumption. Government sees only its specified information stream, except the oracle benchmark.

**Interaction and collectives.** Individuals interact indirectly through shared content heat; there are no interpersonal edges or collective actors. **Stochasticity.** NumPy SeedSequence spawns seven streams in fixed order: initialization, content, ranking, interaction, survey, panel, government. Measurement changes cannot affect the world in no-feedback runs. Feedback worlds share seed identifiers, but divergent content pools mean they are not perfectly synchronized common-random-number trajectories.

**Observation.** Primary run outcome is mean total-variation inference error over a specified final window. Additional outputs include full-horizon error, error against initial truth, topic identification accuracy, attention error, preference change, uniform-prior error and late-window shift. A final window is not assumed to be a steady state.

## 5. Initialization

If population_weights are supplied, normalize them to w; otherwise draw w ~ Dirichlet(c_pop,...,c_pop). Draw p_i ~ Dirichlet(K c_pref w). Population truth is the realized mean of individual p_i, not the generating w. Draw q_i by clipping Normal(interaction_mean, interaction_sd) to [0,1]. These draws use the initialization stream.

Draw a fixed platform panel uniformly without replacement, or use all individuals if platform_panel_size = 0. All held estimates start uniform. Streaks are zero, previous dominant topics are −1. Content supply defaults to uniform topics; supplied weights are normalized. Create initial_items at birth time zero with zero heat. Source is nonofficial. No burn-in or empirical calibration is applied.

## 6. Input data

No empirical data enter the model. Configuration values are transparent modeling assumptions, not measured parameters. JSON configurations, seeds, environment metadata and source snapshots define each experiment. Earlier manuscript outputs are not input data or calibration targets.

## 7. Submodels

### Content and recommendation

For each new item choose topic k according to ordinary supply weights, or the scheduled governmental estimate for an official item. Let μ_k = emotion_mean + emotion_advantage × 1[k = advantaged_topic]. Draw e_j ~ Beta(μ_k c_emotion, (1−μ_k)c_emotion). The same rule applies to both sources. Advantage can be positive, zero or negative.

Transform pre-round heat as H_j = log(1+h_j)/max_l log(1+h_l), using all zeros when the maximum is zero. Relevance is cosine similarity to the topic's one-hot vector: R_ij = p_ik/||p_i||_2. Score S_ij = α H_j + (1−α) R_ij.

Top-K selects the highest scores with independent uniform random priorities for exact ties, without perturbing unequal scores. Softmax uses Gumbel top-K on S_ij/temperature, sampling distinct items without replacement; it does not make B independent draws with replacement. All selected items count equally as consumed exposures.

Each selected item receives one Bernoulli(q_i e_j) interaction opportunity from that individual. Add all successful interactions to its heat. At round end multiply heat by heat_retention. Keep an item exactly when `(heat >= heat_floor OR age_rounds < cold_start_rounds) AND age_rounds < max_item_age`, with age_rounds = t−birth+1. A protection round guarantees eligibility, not actual exposure. Max age is an independent hard cap.

### Information and estimates

Truth is P(t) = N^−1 Σ_i p_i(t). The platform estimate is normalized exposure or interaction counts summed over the last observation_window rounds for the fixed panel. Early windows contain only available rounds; zero counts map to uniform. Survey and platform observation share update intervals and delivery delay, but the platform averages historical activity while the survey measures preferences at the observation step.

At each observation, sample survey_size individuals without replacement. With zero selection bias sampling is uniform; otherwise selection weights are proportional to exp(survey_selection_bias × p_i,advantaged_topic). These are sequential weighted sampling weights, not marginal inclusion probabilities. Reports equal current preferences in the idealized baseline. With noise, add independent Normal(0, survey_noise_sd), clip negative components and renormalize each report; an all-zero report becomes uniform. Average reports. Samples are redrawn each observation, whereas the platform panel is fixed.

The fused estimate is (1−fusion_weight) × platform + fusion_weight × survey. No weight is optimized on the reported seeds. Delivered estimates are held until replaced. The oracle uses instantaneous P(t), without observation delay; it is not a timing-matched empirical estimator. A uniform prior is recorded as an additional naive benchmark.

### Preference drift and government feedback

`update_preferences` finds each individual's unique modal exposure topic. A tie or no exposure resets the streak; a repeated unique topic increments it. When streak >= drift_threshold, p_i becomes (1−drift_rate)p_i + drift_rate × onehot(topic). The update occurs every qualifying round, not only at threshold crossing. Zero drift leaves all preferences unchanged.

Under government_policy = none, all estimators evaluate one shared world. Under communicate, create a separate world for each active estimator. Every government_interval rounds, queue one future official item with topic probabilities equal to the active estimate at decision time. Draw its topic/emotion upon publication. There is no direct heat suppression, welfare allocation, trust update, or special official ranking advantage. Other estimators within a feedback world are diagnostic; cross-policy summaries use only each world's active estimator.

### Measures and inference

E(t) = 0.5 Σ_k |estimate_k(t)−P_k(t)|. Initial-reference error instead uses P(0). Attention error uses current exposure shares against P(t). Uniform-prior error compares 1/K with P(t). Top-topic accuracy is the fraction of estimated maximizers that are also true maximizers, corresponding to uniform tie-breaking. Numerical ties use absolute tolerance 10^−12. Preference change is TV(P(t),P(0)). Late-window shift compares last and first halves of the final window; it is only a diagnostic.

`cli.aggregate` treats seeds as independent replicates within a condition, never time steps or agents. It uses 2,000 percentile bootstrap resamples of run means, analysis seed 90210, and reports pointwise intervals and Monte Carlo standard errors. Estimator contrasts resample within-seed differences. Results across α and scenarios reuse seeds and are correlated; no simultaneous coverage or multiplicity adjustment is claimed. Eight-seed development intervals are preliminary. Feedback runs require separate worlds for each policy.

## References and remaining validation

ODD structure follows [Grimm et al. (2020)](https://www.jasss.org/23/2/7.html); explanatory purpose follows [Edmonds et al. (2019)](https://www.jasss.org/22/3/6.html). These are methodological references, not a claim that all journal submission requirements have been fulfilled.

Implemented tests cover hand-calculable updates, distribution invariants, seed reproducibility, sampling isolation, tie handling, delayed publication, census measurement, serial/parallel equivalence and failure preservation. Empirical validation, independent reimplementation, label-permutation statistical checks, calibrated competing estimators, population/supply scaling and formal convergence analysis remain unfinished.
