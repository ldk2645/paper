# 参数与假设登记

所有数值均为尚未经验校准的开发假设。默认值来自 Config；实际实验以 resolved_design.json 为准。α由批次网格覆盖。种子属于复现控制，不是经验参数。

| 参数 | 代码默认值 | 基线试跑值 |
|---|---|---|
| n_agents | `300` | `120` |
| n_topics | `4` | `4` |
| steps | `1000` | `240` |
| final_window | `300` | `80` |
| alpha | `0.5` | `0.5` |
| attention_budget | `5` | `5` |
| initial_items | `24` | `24` |
| arrivals_per_step | `4` | `4` |
| preference_concentration | `1.0` | `1.0` |
| population_concentration | `3.0` | `3.0` |
| population_weights | `()` | `()` |
| supply_weights | `()` | `()` |
| emotion_mean | `0.4` | `0.4` |
| emotion_concentration | `5.0` | `5.0` |
| emotion_advantage | `0.25` | `0.25` |
| advantaged_topic | `3` | `3` |
| interaction_mean | `0.3` | `0.3` |
| interaction_sd | `0.1` | `0.1` |
| heat_retention | `0.95` | `0.95` |
| heat_floor | `0.01` | `0.01` |
| max_item_age | `200` | `100` |
| cold_start_rounds | `1` | `1` |
| ranking | `topk` | `topk` |
| temperature | `0.15` | `0.15` |
| drift_rate | `0.0` | `0.0` |
| drift_threshold | `4` | `4` |
| observation_window | `20` | `20` |
| observation_interval | `10` | `10` |
| observation_delay | `0` | `0` |
| signal | `exposure` | `exposure` |
| survey_size | `30` | `12` |
| survey_noise_sd | `0.0` | `0.0` |
| survey_selection_bias | `0.0` | `0.0` |
| platform_panel_size | `0` | `0` |
| fusion_weight | `0.5` | `0.5` |
| government_policy | `none` | `none` |
| government_interval | `10` | `10` |
| government_delay | `3` | `3` |
| active_arm | `platform` | `platform` |

结构情景覆盖值见 scripts/run_pilot_suite.py；反馈配置见 configs/smoke_feedback.json。空 population_weights 表示随机生成总体目标；空 supply_weights 表示均匀供给；platform_panel_size=0 表示全体。

行为假设（情绪互动、漂移、曝光即消费）、制度假设（观测和发布时序）、数值假设（内容寿命和保护期）均需分开做敏感性检验。当前测试不提供现实参数依据。
