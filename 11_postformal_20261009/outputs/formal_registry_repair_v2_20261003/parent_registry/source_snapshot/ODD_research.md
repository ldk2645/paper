# Research engine ODD: 0.5.1-dev

This document describes the implemented identification engine, rather than the legacy 0.4.0 model described in `ODD.md`. It is an implementation specification, not a formal experimental freeze. The S1 design is registered separately in `s1_execution_protocol_20260929.md`; exact numerical settings are stored with every run. All S1 artifacts retain `formal_ready=false`.

## 1 Purpose and patterns

The model examines how algorithmic attention and restricted public information interact with governmental inference, delayed topic responses, changing public preferences and trust. Its primary outcomes are the public signal's distance from current preferences, governmental perception error, and the topic mismatch of executed responses evaluated against trigger-time preferences. Exposure, waiting, execution incidence, completion, recovery and trust are separate diagnostics.

The implementation is not calibrated to reproduce a legacy threshold. Development acceptance concerns timing, permissions, accounting and reproducibility. It does not require intervention benefits, a phase transition or recovery.

## 2 Entities, state variables and scales

There are N citizens, a finite content pool, a public signal publisher and a government. Topics form a common K-category taxonomy. A tick is a simulation period with no established conversion to real days. Each citizen has a simplex preference vector, a private interaction propensity, baseline/current trust, and preference-drift counters. Citizens have stable integer IDs.

Each content item has a stable ID, topic, emotional intensity, nonnegative heat, birth tick and source (ordinary, routine official, response official). Government state includes its inferred preference vector, evidence references, pending topic plans and threshold streaks. The publisher maintains a fixed citizen panel, per-tick public counts, history windows and pending delivery packets. Survey and ranking-rule disclosures have separate availability clocks.

The simulation/evaluator holds latent preferences and current exposure. These are excluded from the government's permitted input. Snapshots contain all citizen/content arrays, publisher and estimator state, queues, undelivered information, catalogues, truth history, log prefixes and addressed randomness metadata at `boundary_before_delivery`.

## 3 Process overview and scheduling

At tick t:

1. Record the population mean preference before consumption or drift.
2. Deliver previously generated public packets, surveys and disclosures that are available by t. A missing new public signal does not erase the last valid packet.
3. Update government inference only at its configured frequency and when the substantive evidence signature changes. Store the exact legal input and actual evidence used.
4. On a monitoring tick, schedule eligible topics not already pending, limited by new-plan capacity. Execute every due plan afterward. Delay zero therefore schedules and executes in the same tick; a topic due later in this tick was still pending when scheduling occurred.
5. Apply enabled response heat changes to ordinary content of the target topic, publish enabled replies, publish routine official content according to its interval, and add ordinary arrivals.
6. Rank, consume and interact; record exposure and publish public interaction counts. New packets are available no earlier than t+1+observation_delay. Surveys measure pre-consumption preferences and become available no earlier than t+1+survey_delay.
7. Record evaluator metrics and update trust from this tick's experience.
8. Update preferences, decay heat, remove content according to the registered lifetime rule, and enter the next boundary.

`ResearchWorld.step` implements this common order for all administrative delays. Its scheduling/publication/queue-restoration hooks have default adaptive behavior and an explicitly separate controlled-replay implementation.

## 4 Design concepts

**Emergence and feedback.** Attention concentration, public signal composition, governmental targeting and persistence emerge from individual consumption and interaction, heat reinforcement, drift, responses and trust. They are not imposed as target outcomes.

**Adaptation and objectives.** Citizens' preferences follow the retained drift rule after repeated exposure. The government estimates preferences and applies a fixed threshold/priority policy; it does not optimize a welfare function or learn a control policy. Government agenda share is a separate auxiliary objective, not public welfare.

**Sensing.** The permitted government input is an immutable `GovernmentInformation`: historical public packet, matching public catalogue, and authorized finite survey/ranking disclosure. The government cannot receive the world object, latent citizen vectors, current full exposure, evaluator truth or future observations.

**Interaction and collectives.** Citizens interact through the common content pool and the recommendation mechanism. The finite observation panel is sampled once and preserved across paired branches. There are no additional adaptive organizations or new citizen types.

**Stochasticity.** Initialization, trust, panel membership, content sources, surveys, signal noise, ranking, interaction and response tie-breaking use stable named random addresses. The protocol is `sha256-seedsequence-pcg64-splitmix64-v1`. Seed, stream mapping and NumPy version are archived. Ordinary content draws use stable tick/source/object addresses; optional responses do not consume ordinary-supply draws. Only objects shared across branches have corresponding potential draws.

**Observation.** Raw public counts, source signals, delivered packets, government input/estimates/actions, evaluator trajectories/events and final snapshots are stored separately. A world or parent-seed block is the replication unit; ticks, citizens, inherited prefixes and replay suffixes are not independent repetitions.

## 5 Initialization and input data

Population topic weights and concentration parameters determine independent Dirichlet citizen preferences. Interaction propensities and baseline trust are sampled from bounded distributions using their own streams. Initial content, drift counters, uniform government prior and the empty response queue are initialized explicitly. Physical-array initial hashes are stored independently of the information treatment.

S1 uses synthetic data only. Its alternative initial conditions change registered population topic weights, not hidden post hoc edits. Size checks register whether ordinary supply and scheduling capacity scale with N; rounded realizations are retained. Empirical proxies are not substituted for the model's latent preferences or recommendation exposure.

## 6 Submodels

### Recommendation, interaction and heat

For citizen i and item j, similarity is the citizen's preference for the item's topic divided by the citizen preference vector's Euclidean norm. Heat enters as normalized `log(1+heat)`. The score is α·normalized_heat+(1−α)·similarity. Top-K uses stable random tie keys; the softmax alternative uses Gumbel perturbations and the registered temperature, sampling without duplicate items within a citizen's attention budget.

Interaction probability is clipped to [0,1] and combines citizen interaction propensity, item emotion and a trust factor. The factor is `1+f(2 trust−1)` for official items and `1−f(2 trust−1)` for ordinary items. Interactions increase heat when enabled. Heat decays after consumption; the ordinary rule also removes content below the heat floor after the cold-start period, subject to maximum age.

Complete heat-off suppresses accumulation, heat ranking, heat-based survival, decay and response heat modification. Registered maximum age supplies the replacement lifetime rule. Ordinary interactions remain and still generate the public signal. Heat-mediated response gain in trust is then zero. This differs from α=0, which leaves other heat pathways active, and from merely setting response heat retention to one.

### Public signals and inference

P is the person-weighted mean latent preference; E is the exposure-count composition; source S is the interaction-count composition from the fixed panel. No panel, missing publication or zero raw activity yields no signal. Valid positive raw activity may receive configured count noise and nonnegative truncation; an all-zero result is still missing. A W-tick packet pools valid counts, preserving denominators, weights, missing ticks, coverage, warm-up and delivery times. Source S from the present tick is never available for that tick's decision.

All information cells use a common simplex candidate grid and independent synthetic reference population. A forward model predicts public interaction composition from candidate preferences and public content. Opaque conditions average over registered rule priors; transparent conditions use a disclosed applicable rule while preserving the numerical candidate/call budget. Authorized surveys contribute a common weighted loss. Regularization is toward the uniform prior; tied minima are averaged and optionally smoothed with the prior estimate. Report IDs or repeated delivery times alone do not justify re-smoothing unchanged evidence.

Finite grids, synthetic behavioral priors and a window-end catalogue approximation limit identification. The same public composition may admit multiple preferences. Missing catalogues have an explicitly marked fallback and are unsuitable as the formal main-input regime.

### Response and trust

Adaptive response policies are hard threshold, selective agenda threshold or persistent-threshold waiting. Pending topics block additional plans; capacity limits newly scheduled plans per monitoring tick. Each plan freezes target, trigger/due, legal information reference, heat retention and reply flag. Existing plans retain these values across a later policy fork. Replies and heat actions are separate channels; routine publication survives disabled targeted response.

Trust uses the existing exposure-based or alignment-based rule in `governance.trust_update`, with registered baseline, update rate and gains. No new trust equation is introduced. `trust_update_rate=0` freezes the state at its sampled baseline; `trust_feedback_strength=0` removes its effect on interaction but permits state updates. The S1 2×2 varies these independently.

### Outcomes, replay and dynamic experiments

All distribution distances use total variation, one half of the sum of absolute component differences. Primary means use a registered terminal evaluation window; insufficient public-signal coverage is missing. Perception error with legal evidence is separated from prior-only diagnostics. Executed actions are grouped by trigger and execution time before their target composition is compared with the corresponding complete preference vectors. No execution gives missing targeting error, not zero. Fixed-L completion distinguishes timely execution, known noncompletion and right censoring.

Controlled replay freezes a legally reconstructed donor plan. It retains trigger dates, targets and action parameters, changes due dates only, permits overlapping same-topic plans, and does not adapt targets to the receiving world's subsequent observations. Donor references and receiver truth are kept distinct. Replay replies have a stable event identity across delay arms; they use a separate identity namespace from adaptive replies. Replay snapshots require `ControlledReplayWorld` and reject adaptive forking.

Continuation inherits complete boundary states between registered alpha stages. Recovery branches share a mother snapshot, an independently registered candidate reference and a common observation horizon. Exposure-gap rolling windows define recovery, with a pre-intervention time origin, consecutive confirmation and explicit rebound/censoring. Independent N/T/initial-condition runs are labeled separately from continuation. These small experiments neither establish substantive health nor demonstrate phase transitions, hysteresis, irreversibility or a stationary terminal distribution.

## 7 Implementation and reproducibility

Physical dynamics and state: `research_world.py`; configuration/version: `research_config.py`; public observation: `public_signals.py`; restricted inference: `government_sensing.py`; scheduling: `research_governance.py`; randomness: `research_randomness.py`; summaries/support/censoring: `research_outcomes.py`; controlled timing: `research_replay.py`; registered dynamic experiments and stored-data reconstruction: `research_dynamics.py`.

`research_s1_cli.py` creates new immutable output directories, archives source/tests/scripts and records failures. `validate_s1_outputs.py` checks hashes and reconstructs legal sensing, adaptive plans, summaries, replay diagnostics, dynamic diagnostics and paired statistics without running new simulation ticks. A matching archived engine is required for S1 historical validation because replay plans bind the complete source hash. Serial/parallel comparisons normalize only documented execution-envelope identifiers. Checkpoints retain partial coverage and are not relabeled as completed independent worlds.

## Independent precision pilot (completed 2026-10-02)

The engine remained unchanged for the separately registered `precision_pilot_protocol_20260930.md` design: N=100, T=300, alpha=0.25/0.75, final window 200–299, and a common fork boundary at tick 150. Two unconditional waves of 20 new seeds each produced 80 alpha-by-seed blocks and 1,440 complete endpoints, with no failed blocks. The alpha strata share seeds; the independent replication count is 40. The fixed pilot stopped at 40 seeds.

`execute_precision_pilot.py` runs tests, both waves, read-only validation and combined planning. Compressed raw artifacts retain government inputs and evaluator truth separately. Validation reconstructs public signal generation and delivery, legal sensing and queues, lineage, replay diagnostics, summaries and paired values without advancing physical worlds. Both batches passed validation; 212 tests passed. Validation reports bind the manifest and complete artifact inventory, which combined analysis checks against current file contents.

All 102 registered planning items had 40 jointly measurable seed pairs or four-cell sets. With target half-width 0.02, at least 30 valid observations, and a cap of 1,000 total seeds per condition, 99 items were budget-feasible. Only 41 passed the registered 20-versus-40 stability diagnostic; the remaining 61 failed solely because the sample variance changed by more than 25%. The cross-family total requirement was 184 at alpha=0.25 and 1,293 at alpha=0.75; capping the latter at 1,000 does not meet all registered targets. These are planning approximations, not coverage guarantees. At pilot acceptance, formal inference, multiplicity, budget decisions and new seeds were still pending; pilot artifacts retain `formal_ready=false`. This pilot does not plan precision for dynamic transitions, structural robustness or held-out trust prediction. See [validation](precision_pilot_validation_20261002.md) and [planning](outputs/precision_pilot_20261002_planning/report.md).

## Formal E2/E3/E4 registration (2026-10-03)

The [formal execution protocol](formal_execution_protocol_20261003.md) and `configs/formal_design_20261003.json` retain the pilot model, treatments and evaluation windows. The authorized fixed budget is 184 mother worlds per condition at alpha=0.25 and 1,000 at alpha=0.75, shared across families. New seeds 71001–72000 form a nested design: the lower-alpha stratum uses the first 184. This registers 1,000 independent seed units, 1,184 alpha-by-seed groups, 21,312 physical endpoints and 22,496 statistical arm records; repeated baselines do not create independent observations. All three planning shortfalls and 61 variance-instability flags remain reported.

Primary analysis uses within-mother contrasts conditional on joint measurability, pointwise Student t intervals, and one Holm adjustment across all 102 registered comparisons. Insufficient joint support or numerical zero variance yields descriptive results only; unavailable tests retain their place in the multiplicity family. Actual achieved precision is reported after the fixed batch, without additional sampling. Auxiliary quantities retain their own valid denominators. The protocol states the assumptions and limits of these procedures.

`freeze_formal_design.py` runs the full test suite, audits unused seeds and archives the design, inference rules, code, dependency versions, contracts and pilot evidence. Only a validated registry manifest may set `formal_ready=true`, scoped to this E2/E3/E4 design; the editable configuration template and historical batches remain false. `run_formal_study.py` provides guarded plan, run, read-only validation and analysis commands. Validation reconstructs raw records and summaries without advancing ticks; analysis requires a report bound to the current batch inventory. The freeze itself executes no formal worlds. Subsequent live code or contract changes invalidate this registry's execution gate and require a matching archived environment or a new freeze.
