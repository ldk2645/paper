# Model, experimental design and analysis

Working manuscript text — 4 October 2026. This draft describes the frozen E2–E4 design. Full-batch recovery, read-only semantic validation and the fixed analysis have now passed; findings are reported in the [Results draft](results_en.md), with computational evidence in the [acceptance record](../formal_execution_acceptance_20261004.md). The design was frozen within the project, and is not described as an externally preregistered study. Recovery did not change the design, seed roster or inference policy.

## Model purpose and scope

We developed an explanatory agent-based model of government responsiveness in an algorithmically mediated information environment. The model represents citizens, a finite pool of content, a public signal publisher and a government. Its purpose is to examine how restricted information, administrative timing and the location of intervention within an attention system affect observable mismatches. It is not calibrated to a particular jurisdiction, a social-welfare optimum or a previously reported parameter threshold. A simulation tick has no established conversion to a real-world day.

The model distinguishes the population's mean latent topic preferences, \(P_t\); the topic composition of consumed exposure, \(E_t\); the composition of publicly reported interactions, \(S_t\); the government's preference estimate, \(\widehat P_t\); and discrete response events with separate trigger and execution times. All use a common four-topic classification, but their denominators differ. Preferences are averaged across citizens, exposure is counted across consumed items, and the public signal is weighted by interactions. None of these quantities is assumed to measure public welfare. The government's agenda is also recorded separately from citizens' preferences.

The formal design in this paper covers information conditions (E2), adaptive and controlled-replay timing experiments (E3), and interventions from a common system state (E4). Phase transitions, hysteresis, irreversibility, structural robustness and the predictive value of trust require additional designs. Their investigation is not implied by the two ranking-weight strata or by the finite observation period used here.

## Agents, feedback and the order of events

Each citizen has a topic-preference vector on the probability simplex, an interaction propensity, baseline and current trust, and exposure-history counters. Content items have stable identities, topics, emotional intensity, nonnegative heat, creation times and a source: ordinary content, routine official publication or a targeted official response. Initial citizen preferences follow the registered Dirichlet specification. Interaction propensities, trust and content characteristics use separately addressed random draws.

For citizen \(i\) and item \(j\), the recommendation score combines normalized log heat and preference similarity:

\[
q_{ij,t}=\alpha\,\widetilde h_{j,t}
 +(1-\alpha)\frac{p_{i,k(j),t}}{\lVert p_{i,t}\rVert_2}.
\]

Here, \(k(j)\) is the item's topic. Log heat is normalized by its maximum across the current pool when positive. The formal model selects the highest-scoring items within each citizen's attention budget, using addressed random priorities for ties. Interactions depend on the citizen's interaction propensity, the item's emotion and a trust-dependent source factor, with probabilities bounded to \([0,1]\). Interactions accumulate heat. Repeated exposure can update preferences under the registered drift rule; trust follows the existing exposure-based update rule. These are behavioral assumptions rather than empirically identified causal coefficients. Full equations and implementation details are provided in the accompanying ODD description and archived code.

Within each tick, the evaluator first records preferences before consumption and drift. Previously generated information is then delivered when its availability time has been reached. Government inference is updated when permitted by its update schedule and evidence signature. The government next schedules responses, after which all due plans execute, including newly scheduled zero-delay plans. Official publications and ordinary arrivals enter recommendation and consumption. The publisher generates the current public signal after consumption; trust, preferences and content states are then updated before the next boundary.

Current public interactions therefore cannot inform a decision earlier in the same tick. Administrative delay zero permits execution in the decision tick using legally available historical information; it does not eliminate observation delay. A topic already pending at scheduling remains ineligible for a duplicate plan even if its existing plan will execute later in that tick.

## Government information and inference

The government receives immutable, restricted information records. These contain a delivered historical public packet, its associated public content catalogue, and any authorized survey report or ranking-rule disclosure. Latent citizen preferences, complete current exposure, future observations and evaluator diagnostics are excluded. The public catalogue contains observable item attributes rather than individual citizen states. Access and actual evidence use are recorded separately from evaluator truth.

The formal baseline publishes aggregate interaction counts covering all citizens, with zero publication noise. Historical packets pool valid counts over five ticks and preserve their denominators, source times, coverage and delivery times. A zero-activity source signal is missing, rather than a uniform preference observation. The last valid delivered packet may remain available when subsequent signals are absent, with its age retained. A lawful survey can provide preference information even when no public packet is available. In the absence of any lawful preference observation, the government's prior is recorded but does not trigger data-driven responses.

All E2 information conditions use the same restricted inverse procedure. It evaluates candidate population preferences on a fixed simplex grid using an independent synthetic reference population and public content attributes. Predictions of public interaction composition are compared with the observed signal. In opaque conditions, predictions are averaged over the registered alpha prior values 0, 0.5 and 1. Applicable rule disclosure replaces that mechanism uncertainty within the same candidate and numerical-call budget. Authorized finite survey information enters the common loss with weight one; regularization toward the uniform prior has weight 0.01. Tie handling and smoothing are shared across conditions. Overlapping historical packets are not multiplied as independent observations.

Inference updates every five ticks when the substantive evidence signature changes. Renaming or redelivering an unchanged packet does not create new evidence. The formal smoothing coefficient is one. The candidate-grid resolution is four, with four synthetic reference individuals and fixed reference seed 1729. The reference population is not drawn from the world's citizens and does not count as an independent simulation replication.

This procedure is a limited numerical inverse. It uses a window-end public catalogue as an approximation to the evolving source window, a finite candidate grid and fixed assumptions about unobserved behavioral heterogeneity. A public composition may be compatible with multiple latent preferences. Consequently, disclosure is not defined to produce perfect inference or an improvement. In feedback experiments, conditions share signal-construction rules and resources, while realized public histories may diverge because government actions change subsequent states.

## Experimental design

Each world contains 100 citizens and four topics and runs for 300 ticks. The primary evaluation window is ticks 200–299. Citizens can consume up to five items per tick, and four ordinary items arrive each tick. The two registered ranking-weight strata are \(\alpha=0.25\) and \(0.75\). The baseline government monitors every tick, uses a hard response threshold of 0.15, permits at most one new plan per monitoring call and executes plans after three ticks. A response retains 0.7 of the target topic's ordinary-content heat and publishes a reply; routine official publication continues every ten ticks. Capacity denotes scheduling capacity, not a separate execution budget. The finite survey samples 12 citizens every five ticks. Public packets and surveys become available no earlier than the tick after their source measurement.

E2 crosses independent preference information with ranking-rule information. In condition IDs I00, I10, I01 and I11, the first bit indicates a finite survey and the second an authorized rule disclosure. A survey does not directly reveal the population preference vector, and rule disclosure does not provide authority to change ranking. The four cells retain the same decision policy and physical response tools.

E3 distinguishes adaptive closed-loop interventions from controlled replay. Closed-loop conditions individually change the administrative delay, scheduling capacity or additional public-signal delivery delay relative to I00. Replay instead retains the trigger dates, topics and action parameters of the same legally reconstructed I00 donor plan, changing only its due dates. It does not retarget actions using the recipient world's subsequent observations. Replay permits overlapping plans for the same topic; the receiving world's physical states continue to evolve. Thus, replay is a controlled timing diagnostic conditional on a donor plan, whereas the adaptive experiment estimates a closed-loop dynamic contrast. Subtracting the two does not identify a generic direct–indirect effect decomposition.

E4 saves the full I00 state at the boundary before information delivery at tick 150 and creates five branches. B0 continues the existing policy. B1 activates the finite survey. B2 reduces the administrative delay of new plans to one tick. B3 permits two new plans per monitoring call. B4 changes ranking's heat weight to zero. Plans already pending retain their targets, due dates and action parameters. The opaque government in B4 does not automatically learn the new ranking rule. B4 retains the other heat pathways and is therefore not a full heat-off intervention.

| Family | Registered contrasts | Count per stratum and outcome |
|---|---|---:|
| E2 | I10−I00; I11−I01; I01−I00; I11−I10; I11−I10−I01+I00 | 5 |
| E3 closed loop | delay0, delay1, delay10, capacity2 and observation2, each minus baseline delay3 | 5 |
| E3 replay | delay1−delay0; delay3−delay0; delay10−delay0 | 3 |
| E4 | B1−B0; B2−B0; B3−B0; B4−B0 | 4 |

These 17 contrasts, two strata and three primary outcomes produce 102 registered analyses. No additional cross-stratum difference test is registered. E4 compares terminal-window outcomes after intervention; it does not establish recovery against a separately justified healthy reference.

## Outcomes

For distributions on the common topic support, total variation is

\[
\operatorname{TV}(x,y)=\tfrac12\sum_{k=1}^{4}|x_k-y_k|.
\]

The first primary outcome, **public representation gap**, is \(\operatorname{TV}(P_t,S_t)\), using consumption-preceding preferences and the source signal generated after consumption in the same tick. This evaluator comparison does not expose the source signal to the government's same-tick decision. A world's value is the equal-tick mean over valid signals in the terminal window. At least 80 of its 100 ticks must have valid source signals; otherwise, the world-level outcome is missing.

The second outcome, **government perception error**, is \(\operatorname{TV}(P_t,\widehat P_t)\), averaged over terminal-window ticks with a data-based government estimate (`has_data=True`). Delivery alone does not satisfy this criterion: the estimator must have updated using lawful evidence. Prior-only ticks are excluded and reported separately. Held data-based estimates remain government states between updates, so the metric includes information ageing as well as limitations of inference. Its valid coverage is retained.

The third outcome, **trigger-time response targeting mismatch**, groups executed actions sharing trigger tick \(\tau\) and execution tick \(u\). Topic action counts in each cohort form a distribution \(r_{\tau,u}\), compared with \(P_\tau\). A world-level value is the equally weighted mean of \(\operatorname{TV}(r_{\tau,u},P_\tau)\) across cohorts executed in ticks 200–299. Their trigger dates may precede that window. No execution yields a missing targeting outcome, accompanied by zero executed actions rather than a claim of perfect alignment.

A single action targeting topic \(k\) has mismatch \(1-P_{\tau,k}\). Action composition is not service provision or a resource allocation. The three distances are not an additive decomposition of policy loss. Actual exposure mismatch, \(\operatorname{TV}(P_t,E_t)\), is retained as an auxiliary mechanism measure rather than substituted for the public representation gap.

Auxiliary summaries include response incidence, executed and newly scheduled counts, execution-tick coverage, pending plans, waiting time, execution-time targeting mismatch, exposure mismatch, preference change, trust and information coverage. Each is summarized within a world before equal-weight aggregation across worlds, with its own valid denominator. Fixed-horizon completion includes plans triggered in ticks 150–279 and asks whether execution occurs within 20 ticks, through a latest deadline of 299. Empty cohorts are undefined; incompletely observed pending plans are censored. Model response completion does not establish that real public needs have been met.

## Replication and sample-size planning

The independent replication unit is the mother-world seed. The formal list contains seeds 71001–72000. All 1,000 are used at \(\alpha=0.75\); the first 184 are used at \(\alpha=0.25\). The resulting 1,184 alpha-by-seed blocks represent 1,000 independent seed units. Shared baselines, citizens, time steps, events and inherited prefixes are not additional replications.

Each block has 18 physical endpoints: four E2 cells, five E4 branches, five additional closed-loop E3 conditions and four replay conditions. The closed-loop baseline reuses E2 I00, producing 19 statistical arm records per block. The complete registered design therefore contains 21,312 physical endpoints and 22,496 arm records. B0 continuation is checked against uninterrupted I00. Stable random addresses couple ordinary supply and shared objects across treatment worlds without requiring endogenous content or realized interactions to be identical.

An independent precision pilot used 40 seeds shared across both alpha strata, in two fixed waves of 20. Planning used the sample variation of within-seed contrasts, a Wilson lower bound for joint measurability and a normal-approximation target pointwise half-width of 0.02. A minimum of 30 jointly measurable units and a maximum of 1,000 mother worlds per condition were retained. The formal counts use the largest cross-family requirement within each stratum, subject to this cap.

Three uncapped requirements exceeded the high-alpha budget: 1,293 for closed-loop delay0−delay3 on public representation gap; 1,071 for the same contrast on trigger-time targeting mismatch; and 1,002 for replay delay3−delay0 on public representation gap. In addition, 61 of 102 pilot planning items failed the registered 20-to-40 variance-stability criterion. All flags are retained. Neither the cap nor the pilot calculation guarantees achieved precision. Formal seeds are not supplemented on the basis of effects, significance, missingness, interval widths or insufficient valid observations, and pilot worlds are not pooled with formal worlds.

## Estimands and statistical inference

World-level outcomes are contrasted within seed using registered coefficients. For outcome \(Y_{ia}\) of seed \(i\) and arm \(a\), define

\[
d_i=\sum_a c_aY_{ia},\qquad
J_i=\mathbf1\{Y_{ia}\text{ is defined for all arms with }c_a\ne0\}.
\]

The estimand is \(E(d_i\mid J_i=1)\). Four-cell interactions require all four outcomes for the same seed; separate cell means with different support sets are not combined. Signal coverage and response occurrence can depend on treatment. The conditional contrast therefore cannot automatically be generalized to an average effect for all registered mother worlds. Total, jointly measurable, partially measurable and entirely unmeasurable counts, detailed support patterns and per-seed differences are retained.

When inference is available, the pointwise 95% interval is

\[
\bar d\ \pm\ t_{0.975,n-1}s_d/\sqrt n,
\]

where \(n\) is the jointly measurable count and \(s_d\) uses denominator \(n-1\). Tests are two-sided against a zero conditional mean. The distribution of model differences is not guaranteed to be normal; these are approximate intervals and marginal tests. The threshold of 30 valid units is a reporting rule, not a guarantee of normality or coverage.

One Holm adjustment covers all 102 primary analyses at familywise level 0.05. Raw and adjusted p-values are retained. Pointwise intervals are not simultaneous intervals, and multiplicity adjustment does not remove approximation error in marginal tests. When joint support is below 30 or the sample standard deviation is at most \(10^{-12}\), available descriptive statistics remain, but intervals and raw p-values are withheld. Such tests retain their family positions using an internal p-value of one for adjustment. Numerical underflow of positive p-values is explicitly flagged. Intervals are not clipped to theoretical outcome bounds. Achieved half-width relative to 0.02 is reported without further sampling.

## Verification and provenance

The frozen design binds configurations, seed lists, resolved jobs, inference rules, source code, dependency versions, test evidence and pilot planning. The physical engine is version 0.5.1-dev. Its full package hash and the registry chain are preserved in the replication manifest. Ordinary raw records, legal government information, evaluator truth, snapshots, validation evidence and analysis artifacts have distinct roles and references.

A reproduced export failure involved a derived TV value of 1.0000000000000002, one floating-point unit above the mathematical upper bound. The registered repair preserves the physical model and original records. Only a derived view may clamp a verified scalar distance to 0 or 1 when the boundary discrepancy is within absolute tolerance \(10^{-12}\), with zero relative tolerance, after checking the supporting distributions and independently reconstructed value. Probability vectors are not renormalized; raw values remain unchanged. Each correction is logged. Invalid vectors, nonfinite values, larger discrepancies or inconsistent records remain errors. This export tolerance does not clip inferential intervals or redefine measurable support.

Recovery retains complete successful groups as byte-identical compressed raw artifacts and reconstructs their metadata and derived summaries without advancing physical worlds. The failed group is rerun in full with its original configuration and seed. Original failed and interrupted outputs are retained, and recovery introduces no additional independent sample. Formal inference is withheld until the complete registered batch passes read-only semantic validation and its analysis is bound to the current manifests and file inventory. This computational verification does not by itself establish empirical validity.

## Working-source record

This English draft is based on the existing [Chinese methods draft](../manuscript_methods_formal_20261004.md), [formal execution protocol](../formal_execution_protocol_20261003.md), [research ODD](../ODD_research.md), [signal contract](../signal_and_outcome_contract.md), [numeric repair policy](../formal_numeric_repair_protocol_20261003.md) and [recovery policy](../formal_numeric_repair_resume_protocol_20261003.md). These project links support review and will be replaced by the appropriate article and supplement references during final manuscript assembly. The draft adds no experiments or unvalidated results.
