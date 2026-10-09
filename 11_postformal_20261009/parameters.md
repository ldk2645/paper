# 参数与假设登记（0.4.0）

所有数值均为尚未经验校准的开发假设。默认 Config 保留无反馈测量模型；恢复主模型须使用 configs/restored_core.json。实际运行以各批次 resolved_design.json 为准。

试跑使用α=0、0.25、0.5、0.75、1，以及种子301—308。表中α默认值仅在没有批次覆盖时生效。末时窗不是已验证的稳态。

| 参数 | 代码默认值 | 恢复主模型试跑值 |
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
| population_weights | `()` | `[1, 1, 1, 1]` |
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
| cold_start_rounds | `1` | `2` |
| ranking | `topk` | `topk` |
| temperature | `0.15` | `0.15` |
| drift_rate | `0.0` | `0.03` |
| drift_threshold | `4` | `4` |
| observation_window | `20` | `1` |
| observation_interval | `10` | `1` |
| observation_delay | `0` | `0` |
| signal | `exposure` | `exposure` |
| survey_size | `30` | `12` |
| survey_noise_sd | `0.0` | `0.0` |
| survey_selection_bias | `0.0` | `0.0` |
| platform_panel_size | `0` | `0` |
| fusion_weight | `0.5` | `0.5` |
| government_policy | `none` | `respond` |
| government_interval | `10` | `1` |
| government_delay | `3` | `3` |
| active_arm | `platform` | `platform` |
| agenda_topics | `(0, 1, 2)` | `(0, 1, 2)` |
| agenda_target_share | `0.7` | `0.7` |
| routine_publication_interval | `10` | `10` |
| official_emotion_mean | `None` | `0.15` |
| response_enabled | `True` | `True` |
| response_publish | `True` | `True` |
| response_threshold | `0.3` | `0.15` |
| response_heat_retention | `0.7` | `0.7` |
| response_strategy | `hard` | `hard` |
| response_wait_observations | `3` | `3` |
| response_capacity | `1` | `1` |
| storm_threshold | `0.3` | `0.3` |
| initial_trust_mean | `0.69` | `0.69` |
| initial_trust_sd | `0.12` | `0.12` |
| trust_update_rate | `0.0` | `0.06` |
| trust_feedback_strength | `0.0` | `0.25` |
| trust_rule | `exposure` | `exposure` |
| trust_official_gain | `0.45` | `0.45` |
| trust_offagenda_penalty | `0.6` | `0.6` |
| trust_response_gain | `0.0` | `0.0` |
| trust_alignment_gain | `1.0` | `1.0` |

## 解释与假设性质

- population_weights为空时随机生成总体目标；恢复主模型采用对称目标[1,1,1,1]，每个种子的实际公众偏好仍以个体均值计算。政府agenda_topics及其目标份额独立指定，不代表公共福利。
- supply_weights为空表示均匀话题供给；platform_panel_size=0表示全体观测。曝光等同消费、同一内容可重复被推荐、无网络结构均是结构假设。
- 情绪优势与官方内容情绪均值是不同假设。no_emotion同时清除二者差异；no_topic_emotion只清除话题差异。漂移是可关闭的行为假设。
- heat_retention控制全体热度衰减；response_heat_retention只在回应执行时调节目标话题普通内容的热度。α=0仍可能通过heat_floor产生热度影响内容存活的通道。
- response_capacity限制每次监测新排期数量，同一话题在待执行期间不重复排期。government_delay增大同时影响排队占用，不能直接解释为纯延迟效应。
- trust_update_rate控制状态变化，trust_feedback_strength控制信任对互动的作用；关闭后者不等于冻结信任。两种trust_rule均未校准。核心配置trust_response_gain=0，不给热度调节动作自动增加信任。
- official_emotion_mean是Beta分布均值，不是原V1固定情绪强度。新版信任方程没有直接使用历史截面回归系数。
- observation_delay>0时，首条观测送达前估计保持均匀先验；低阈值可能使其触发回应。当前核心试跑延迟为0；后续信息延迟实验须区分先验与已观测信号。
- 阈值、初值、时序、寿命、内容供给、信任系数和策略强度均须作敏感性或替代结构检验。未发现或校准现实临界值。

生成：python scripts/document_parameters.py。情景覆盖：scripts/run_core_suite.py。
