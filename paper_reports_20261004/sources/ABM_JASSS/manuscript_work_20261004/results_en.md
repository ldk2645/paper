# Results

Working manuscript text — 4 October 2026. These results use the completed, accepted E2–E4 batch and its fixed analysis. Acceptance was recorded at 05:52:11 China Standard Time on 4 October 2026. The design was frozen within the project; this wording does not imply external preregistration. Model and outcome definitions are given in [Methods](methods_en.md).

The complete numerical record is the accepted [primary table](../outputs/formal_e2_e4_repaired_v2_20261004_analysis/primary.csv) and [auxiliary table](../outputs/formal_e2_e4_repaired_v2_20261004_analysis/auxiliary.csv), accompanied by the [full report and forest plots](../outputs/formal_e2_e4_repaired_v2_20261004_report/report_zh.md). Editorial references such as **P18** and **A59** identify physical lines in those two CSV files, counting their header as line 1. The evidence index below maps every primary line to its family, stratum, contrast and outcome. These references are working-draft provenance markers, not literature citations.

## 5.1 Completed sample, support and precision

The accepted batch contains 1,184 alpha-by-seed blocks and 21,312 physical endpoint records, using 1,000 independent seeds. The low-alpha stratum uses the first 184 seeds of the 1,000-seed high-alpha set. Recovery reused 1,183 blocks and reran one block at its original seed, without adding independent samples. The original failed batch remains recorded separately. Recovery, full semantic validation, analysis and reporting all passed the [execution acceptance](../outputs/formal_repair_v2_retry_execution_20261004/acceptance.json).

All 102 registered primary analyses were estimable. For every contrast and outcome, joint valid support equalled the registered total: 184 mother worlds at alpha 0.25 and 1,000 at alpha 0.75. The counts of partially valid and entirely invalid contrasts were zero. All 532 auxiliary rows likewise had valid support equal to their total. Thus, outcome missingness did not remove mother worlds from these realized primary comparisons. The registered estimands nevertheless remain paired contrasts on joint measurable support: complete support in this batch does not redefine an outcome or guarantee support in another design. In particular, a defined targeting outcome requires at least one execution and does not imply equal numbers or timing of responses across conditions. [P2–P103; A2–A533]

All observed pointwise 95% confidence-interval half-widths were at or below the target of 0.02 TV units, ranging from 0.0000764 to 0.0199208. The three pilot planning shortfalls and 61 pilot variance-instability flags remain part of the record. The pilot's uncapped requirements were 1,293 for the high-alpha closed-loop delay0 public representation gap, 1,071 for its targeting mismatch, and 1,002 for the high-alpha replay delay3 public representation gap. The fixed cap remained 1,000; these planning risks are not three failures of achieved formal precision. No outcome-dependent sample extension was made. [P47, P49, P64, P74, P90; full report]

Forty-five of the 102 null hypotheses were rejected by the single Holm adjustment over the complete primary family. The table below partitions those decisions for description; the adjustment was not recomputed within its rows. Eight pointwise intervals excluded zero while the corresponding Holm decisions did not reject, illustrating why interval exclusion alone is insufficient for the registered decision rule. Six extreme p-values carry a numerical-floor flag; their stored floor is not an exact tail probability and is never reported as p=0. Complete raw p-values, adjusted p-values and half-widths remain in the primary CSV. [P2–P103]

| Experiment | Alpha 0.25: Holm rejections / registered tests | Alpha 0.75: Holm rejections / registered tests | All tests |
|---|---:|---:|---:|
| E2 information conditions | 6 / 15 | 10 / 15 | 16 / 30 |
| E3 adaptive closed loop | 5 / 15 | 8 / 15 | 13 / 30 |
| E3 donor-plan replay | 0 / 9 | 1 / 9 | 1 / 18 |
| E4 common-state interventions | 7 / 12 | 8 / 12 | 15 / 24 |
| Total | 18 / 51 | 27 / 51 | 45 / 102 |

All effects below are differences in TV distance, not percentage-point changes in accuracy or welfare. Intervals are pointwise 95% t intervals, not simultaneous intervals. A negative treatment-minus-baseline difference indicates a lower distance on that outcome. The E2 interaction instead measures departure from the additive prediction. Non-rejection is not evidence of equivalence or proof of no effect. The two alpha strata describe separate registered settings; no cross-alpha difference test was registered.

## 5.2 Information effects depended on the information already available

At alpha 0.75, adding a finite preference survey lowered both government perception error and trigger-time response targeting mismatch, whether or not the rule was disclosed. Without disclosure, the respective differences were −0.499881 [−0.507042, −0.492720] and −0.495916 [−0.509086, −0.482746]. With disclosure, they were −0.660369 [−0.668475, −0.652263] and −0.637499 [−0.649707, −0.625291]. All four rejected after Holm adjustment; all four also carry the numerical-floor flag. These reductions should not be interpreted as the survey revealing population truth without error. [P18–P19, P21–P22]

Rule disclosure had opposite estimated directions depending on survey access in this stratum. Without a survey, disclosure increased perception error by 0.142137 [0.133537, 0.150737] and targeting mismatch by 0.072245 [0.068964, 0.075525]. With a survey, disclosure lowered them by 0.018351 [0.015486, 0.021217] and 0.069339 [0.059834, 0.078844], respectively; equivalently, the signed contrasts were negative. All four rejected after Holm adjustment. The interactions were −0.160488 [−0.168985, −0.151992] for perception and −0.141583 [−0.151194, −0.131973] for targeting, also rejecting. These interactions place the combined condition below the additive prediction for these distances; they are not direct estimates of I11 minus I00. [P24–P25, P27–P28, P30–P31]

At alpha 0.25, the pattern did not support a uniform benefit from either form of information. Rule disclosure lowered perception error both without a survey (−0.025697 [−0.033285, −0.018108]) and with one (−0.020452 [−0.023310, −0.017595]); both rejected after Holm adjustment. Adding a survey when the rule was already disclosed instead increased perception error by 0.004382 [0.002580, 0.006183], also rejecting. The survey contrast without disclosure did not reject for perception error. Survey access lowered targeting mismatch in both disclosure conditions: −0.001163 [−0.001778, −0.000548], adjusted p=0.01494, and −0.000574 [−0.000837, −0.000311], adjusted p=0.00165. Rule disclosure with a survey increased targeting mismatch by 0.001145 [0.000836, 0.001454], whereas its no-survey targeting contrast did not reject. Neither low-alpha interaction rejected. [P3–P16]

None of the ten E2 public representation-gap contrasts, including both interactions, rejected after Holm adjustment. This outcome concerns the relation between latent preferences and public interactions, not the accuracy of the government's estimate. Its non-rejections alongside changes in the other outcomes support reporting the layers separately, without claiming that public representation was invariant. Moreover, E2 is a closed-loop experiment: government actions can alter later preferences, content and signals. These are dynamic effects of information conditions, not estimator comparisons applied to identical realized inputs. [P2, P5, P8, P11, P14, P17, P20, P23, P26, P29]

Auxiliary descriptions also distinguish response incidence from response density. At alpha 0.75, every E2 mother world had a terminal-window response in every arm. Yet mean execution-tick coverage was 0.74863 in I00, 0.98203 in I01, 0.33508 in I10 and 0.30052 in I11; corresponding mean execution counts were 74.863, 98.203, 33.508 and 30.052. These equal-weight mother-world summaries are descriptive. Lower targeting mismatch therefore should not be read as an equal volume of service delivered more accurately. [A58–A59, A63, A72–A73, A77, A86–A87, A91, A100–A101, A105]

## 5.3 Administrative timing changed several parts of the adaptive system

In the closed-loop experiment, all conditions are compared with the adaptive baseline administrative delay of three ticks. At alpha 0.25, delay0 increased perception error by 0.113545 [0.099707, 0.127384] while lowering targeting mismatch by 0.021380 [0.016190, 0.026570]; both signed contrasts rejected after Holm adjustment. Delay1 showed the same direction pattern: perception error increased by 0.086793 [0.070681, 0.102904] and targeting mismatch fell by 0.005711 [0.003897, 0.007525], again with both rejecting. Neither change rejected for the public representation gap. Faster execution therefore did not lower all three distances in this setting. [P32–P37]

At alpha 0.75, delay0 lowered all three distances: public representation gap by 0.082081 [0.065351, 0.098810], perception error by 0.020560 [0.013251, 0.027869], and targeting mismatch by 0.402709 [0.384704, 0.420714]. All three signed contrasts rejected after Holm adjustment. Delay1 lowered the public representation gap by 0.037737 [0.023188, 0.052287] and targeting mismatch by 0.087775 [0.082261, 0.093289], with both rejecting. Its perception-error contrast was −0.011601 [−0.018866, −0.004336], but did not reject after Holm adjustment (adjusted p=0.10128). [P47–P52]

Extending administrative delay to ten ticks produced no Holm rejection at alpha 0.25. At alpha 0.75 it increased the public representation gap by 0.053272 [0.039562, 0.066981] and targeting mismatch by 0.027044 [0.023527, 0.030560], both rejecting; the perception-error contrast did not reject. Adding two ticks of observation delay produced no Holm rejection for any primary outcome in either stratum. These non-rejections delimit the evidence from this design; they do not establish that observation ageing or the longer delay is inconsequential. [P38–P40, P44–P46, P53–P55, P59–P61]

Increasing scheduling capacity from one to two new plans per monitoring call lowered targeting mismatch at both alpha values: −0.169458 [−0.180920, −0.157997] at 0.25 and −0.009590 [−0.014226, −0.004955] at 0.75, both rejecting. Its other primary contrasts did not reject. This result is sensitive to the meaning of the targeting outcome, which measures topic composition within executed cohorts. At alpha 0.25, baseline and capacity2 mean execution counts were 96.505 and 97.147, while their execution-tick coverage was 0.96505 and 0.59978. At alpha 0.75, counts were 74.863 and 77.375 and coverage was 0.74863 and 0.59291. Thus, capacity changed how actions were distributed across execution ticks as well as their count. The lower cohort-based mismatch does not identify improved efficiency at a fixed response cost. More generally, adaptive timing changes can alter pending-topic eligibility, subsequent plans and system states; they are not pure waiting-time losses. [P41–P43, P56–P58; A114–A115, A128–A129, A198–A199, A212–A213]

## 5.4 Replay provides a distinct donor-plan timing diagnostic

Replay compares delays of one, three and ten ticks with delay0 under a fixed donor action plan. None of its nine low-alpha tests rejected. At alpha 0.75, only the delay3 targeting contrast rejected: −0.009888 [−0.013876, −0.005900], adjusted p=0.00008331. The delay3 public representation-gap contrast was −0.017628 [−0.031834, −0.003423], but did not reject after Holm adjustment (adjusted p=0.81330). All perception-error contrasts and all remaining replay contrasts did not reject. Accordingly, one of the 18 replay tests rejected, rather than replay demonstrating a general absence of timing effects. [P62–P79]

The fixed object is the donor plan's trigger dates, targets and action parameters, not a common sequence of observed information packets. Recipient preferences and physical states continue to evolve; changing due dates can also change the executed cohorts entering the terminal-window outcome. Replay delay0 and closed-loop delay3 are different baselines. Their effects cannot be subtracted to produce a direct–indirect or mediated-effect decomposition, and the difference in rejection counts is not a test that the two experimental effects differ.

## 5.5 Interventions from a common state produced outcome-specific changes

E4 compares four interventions with B0 after branching from the same mother state at tick 150. B1 enables a survey, B2 sets the delay of new plans to one tick, B3 raises new-plan scheduling capacity to two, and B4 sets ranking's heat weight to zero. Plans already pending retain their existing specifications. All comparisons use the terminal window, ticks 200–299.

At alpha 0.25, B1 lowered targeting mismatch by 0.001197 [0.000546, 0.001849] and rejected after Holm adjustment (adjusted p=0.02175), while its representation-gap and perception-error contrasts did not reject. B2 lowered targeting mismatch by 0.005224 [0.003334, 0.007114] but increased perception error by 0.094663 [0.078099, 0.111227]; both rejected, whereas its representation-gap contrast did not. B3 lowered targeting mismatch by 0.058293 [0.049726, 0.066861], with no rejection for either of the other outcomes. [P80–P88]

At alpha 0.75, B1 lowered perception error by 0.499233 [0.492056, 0.506411] and targeting mismatch by 0.497406 [0.484753, 0.510058]. Both rejected and carry the numerical-floor flag; its representation-gap contrast did not reject. B2 lowered the public representation gap by 0.030492 [0.020298, 0.040686] and targeting mismatch by 0.086874 [0.082022, 0.091727], both rejecting. Its perception-error contrast, −0.006321 [−0.011918, −0.000725], did not reject after Holm adjustment (adjusted p=1). B3 lowered targeting mismatch by 0.011332 [0.007591, 0.015074], with no rejection for its other outcomes. [P92–P100]

B4 illustrates why the outcomes cannot be merged into a single claim of improvement. At alpha 0.25, it lowered the public representation gap and targeting mismatch but increased government perception error. At alpha 0.75, it lowered all three distances. Every B4 contrast rejected after the same full-family Holm adjustment, as shown below. The different directions across alpha settings are descriptive; they do not constitute a registered test of effect heterogeneity.

| Initial alpha | Outcome | Signed B4 minus B0 effect [pointwise 95% CI] | Holm-adjusted p | Evidence |
|---|---|---|---:|---|
| 0.25 | Public representation gap | −0.020681 [−0.025636, −0.015725] | 2.503 × 10⁻¹² | P89 |
| 0.25 | Government perception error | +0.203374 [+0.183453, +0.223295] | 2.246 × 10⁻⁴⁶ | P90 |
| 0.25 | Trigger-time response targeting mismatch | −0.007142 [−0.009399, −0.004885] | 2.033 × 10⁻⁷ | P91 |
| 0.75 | Public representation gap | −0.277818 [−0.293174, −0.262462] | 2.892 × 10⁻¹⁷⁷ | P101 |
| 0.75 | Government perception error | −0.064831 [−0.071267, −0.058396] | 1.006 × 10⁻⁷¹ | P102 |
| 0.75 | Trigger-time response targeting mismatch | −0.024413 [−0.028271, −0.020555] | 4.023 × 10⁻³¹ | P103 |

B4 changes ranking only: other heat pathways remain active, and the opaque government does not automatically learn the new rule. Its results therefore do not describe a full heat-off system. The comparisons establish finite-window differences after an intervention, not recovery to a validated healthy state, reversibility or a welfare ranking among policies. Testing those claims, locating a critical alpha, establishing structural robustness, or attributing the results specifically to trust requires separately designed analyses. None is supplied by the present E2–E4 batch.

## Working-draft evidence index

The following is a location index, not an additional statistical analysis. **P** is the physical line number in `primary.csv`; **A** is the physical line number in `auxiliary.csv`. Every primary key is the tuple `(family, alpha, contrast, metric)`. In the table, the outcome columns correspond exactly to `platform_representation_gap`, `perception_error` and `targeting_error_trigger`, respectively. The prose calls the first outcome the public representation gap to distinguish public interactions from consumed exposure.

| Family | Alpha | Exact CSV contrast ID | Public representation gap | Perception error | Trigger-time targeting mismatch |
|---|---:|---|---:|---:|---:|
| E2 | 0.25 | `pref_given_rule0` | P2 | P3 | P4 |
| E2 | 0.25 | `pref_given_rule1` | P5 | P6 | P7 |
| E2 | 0.25 | `rule_given_pref0` | P8 | P9 | P10 |
| E2 | 0.25 | `rule_given_pref1` | P11 | P12 | P13 |
| E2 | 0.25 | `interaction` | P14 | P15 | P16 |
| E2 | 0.75 | `pref_given_rule0` | P17 | P18 | P19 |
| E2 | 0.75 | `pref_given_rule1` | P20 | P21 | P22 |
| E2 | 0.75 | `rule_given_pref0` | P23 | P24 | P25 |
| E2 | 0.75 | `rule_given_pref1` | P26 | P27 | P28 |
| E2 | 0.75 | `interaction` | P29 | P30 | P31 |
| E3_closed | 0.25 | `delay0` | P32 | P33 | P34 |
| E3_closed | 0.25 | `delay1` | P35 | P36 | P37 |
| E3_closed | 0.25 | `delay10` | P38 | P39 | P40 |
| E3_closed | 0.25 | `capacity2` | P41 | P42 | P43 |
| E3_closed | 0.25 | `observation2` | P44 | P45 | P46 |
| E3_closed | 0.75 | `delay0` | P47 | P48 | P49 |
| E3_closed | 0.75 | `delay1` | P50 | P51 | P52 |
| E3_closed | 0.75 | `delay10` | P53 | P54 | P55 |
| E3_closed | 0.75 | `capacity2` | P56 | P57 | P58 |
| E3_closed | 0.75 | `observation2` | P59 | P60 | P61 |
| E3_replay | 0.25 | `delay1` | P62 | P63 | P64 |
| E3_replay | 0.25 | `delay3` | P65 | P66 | P67 |
| E3_replay | 0.25 | `delay10` | P68 | P69 | P70 |
| E3_replay | 0.75 | `delay1` | P71 | P72 | P73 |
| E3_replay | 0.75 | `delay3` | P74 | P75 | P76 |
| E3_replay | 0.75 | `delay10` | P77 | P78 | P79 |
| E4 | 0.25 | `B1` | P80 | P81 | P82 |
| E4 | 0.25 | `B2` | P83 | P84 | P85 |
| E4 | 0.25 | `B3` | P86 | P87 | P88 |
| E4 | 0.25 | `B4` | P89 | P90 | P91 |
| E4 | 0.75 | `B1` | P92 | P93 | P94 |
| E4 | 0.75 | `B2` | P95 | P96 | P97 |
| E4 | 0.75 | `B3` | P98 | P99 | P100 |
| E4 | 0.75 | `B4` | P101 | P102 | P103 |

The E2 IDs denote I10−I00, I11−I01, I01−I00, I11−I10 and I11−I10−I01+I00 in the order listed within each stratum. Every E3_closed ID is its named condition minus baseline delay3; every E3_replay ID is its named delay minus replay delay0; every E4 ID is its branch minus B0.

| Family | Alpha | Exact auxiliary arm ID | `execution_count` | `execution_coverage` | `has_response` |
|---|---:|---|---:|---:|---:|
| E2 | 0.75 | `I00` | A58 | A59 | A63 |
| E2 | 0.75 | `I01` | A72 | A73 | A77 |
| E2 | 0.75 | `I10` | A86 | A87 | A91 |
| E2 | 0.75 | `I11` | A100 | A101 | A105 |
| E3_closed | 0.25 | `baseline` | A114 | A115 | — |
| E3_closed | 0.25 | `capacity2` | A128 | A129 | — |
| E3_closed | 0.75 | `baseline` | A198 | A199 | — |
| E3_closed | 0.75 | `capacity2` | A212 | A213 | — |

The remaining auxiliary rows are retained in the complete table, including signal and perception coverage, exposure mismatch, execution-time targeting mismatch, waiting time, scheduled and pending plans, fixed-horizon completion, preference change and trust. They are descriptive summaries with their own outcome definitions and valid denominators; no additional hypothesis tests are introduced here.
