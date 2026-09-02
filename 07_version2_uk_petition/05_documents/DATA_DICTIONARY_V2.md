# 数据字典：英国议会电子请愿案例约束模型 Version 2

## 1. 使用约定

本字典覆盖V2的输入CSV、配置、逐步指标、事件、风暴和运行摘要。数值缺失在内存DataFrame中通常表示为 `None` 或 `NaN`，写入CSV后可能为空单元格。

V2同时保留现实案例里程碑和合成公众支持字段，二者的单位不同：

- `observed_signature_count`：现实请愿的聚合签名数；
- `cumulative_unique_signers`：已经签署的模拟公众智能体数；
- `synthetic_support_fraction`：模拟唯一签署者占 `population_size` 的比例。

**这三者不换算。** `observed_calendar` 与 `synthetic_unique_support` 是互斥运行模式，不应把它们的支持量连接成同一条序列。

## 2. 证据类别

| 标记 | 含义 | 示例 |
|---|---|---|
| `case_observed` | 700024官方记录可直接支持 | 10,000门槛日、100,000门槛日、关闭、签名快照 |
| `case_observed_rounded` | 单案日历间隔取整数模拟步 | 第14、177、182、237步 |
| `conditional_sample` | 222条已回应且时间戳完整的条件样本 | 11、22、57天时延情景 |
| `uk_institutional_rule` | 英国请愿制度规则 | 10,000回应门槛、100,000辩论考虑门槛 |
| `uk_submission_rule` | 英国请愿提交阶段的5名支持者规则 | 初始化占位；不是700024公开时实测签名数 |
| `inherited_v1` | 从冻结V1继承，未被英国数据重新估计 | 推荐公式、热度衰减、偏好漂移、信任方程 |
| `model_rule` | 为实现制度过程而新增的模型规则 | 一次性排程、待回应队列 |
| `synthetic_counterfactual` | 合成支持模式产生或指定 | 模拟唯一签署者、20%合成门槛 |
| `counterfactual_not_identified_by_case` | 案例不能识别的情景参数 | `alpha`、热度乘数、直接信任信号 |

## 3. 输入数据

### 3.1 `03_data/uk_petition_response_delays_222.csv`

粒度：每行一条已获得政府回应且门槛/回应时间戳完整的请愿。

主键：`petition_id`。

| 字段 | 类型 | 单位 | 定义 | 用途 |
|---|---|---|---|---|
| `petition_id` | 字符串 | 无 | 英国议会请愿编号 | 标识记录；保留前导零的可能性 |
| `response_delay_days` | 浮点数 | 天 | 政府回应时间减达到10,000签名门槛时间，保留小数日 | 计算P5/中位数/P95，或经验重抽样后取整数天 |

文件行数：222条数据行。当前文件SHA-256：

```text
F88BE53E79989B755106C406C5311E41559930AEB58BBFC8A2A56BCB319692BC
```

样本边界：API查询条件为 `state=with_response`，再按固定门槛时间窗和完整时间戳筛选。它不是所有请愿的风险集；不能从这份表计算全部请愿的回应率，也不能假设未回应记录与已回应记录具有同一等待时间分布。

转换规则：

```text
response_delay_days = (government_response_timestamp - threshold_10000_timestamp)
                      / 86400秒
```

固定时延情景将约11.07、21.65和56.52天四舍五入为11、22和57个整数步。经验情景从222个正时延中按种子抽样，再转换为至少1天的整数时延；同一随机种子的21个 `alpha` 共用同一抽样值。

### 3.2 700024案例参数

| 参数 | 值 | 单位 | 来源与说明 |
|---|---:|---|---|
| `petition_id` | 700024 | 编号 | 官方请愿编号 |
| `petition_title` | Ban fossil fuel advertising and sponsorship | 文本 | 官方标题 |
| `petition_open_step` | 0 | 日 | 以正式公开为原点 |
| `observed_initial_signatures` | 5 | 支持者 | 英国提交流程需5名支持者；API未记录700024公开瞬间签名数 |
| `observed_response_threshold_step` | 14 | 日 | 公开后约14.28天越过10,000，取整数步 |
| `observed_debate_threshold_step` | 177 | 日 | 公开后越过100,000的整数步 |
| `petition_close_step` | 182 | 日 | 公开后关闭的整数步 |
| `observed_debate_step` | 237 | 日 | 实际辩论日元数据；不用于触发100,000门槛 |
| `observed_final_signatures` | 110,519 | 签名 | 关闭后官方快照 |
| `response_disposition` | `no_policy_change` | 类别 | 政府回应未采纳主要禁令诉求 |

案例观测只给出离散里程碑，不是完整逐日签名曲线。

### 3.3 溯源与参数辅助文件

| 文件 | 内容 | 使用边界 |
|---|---|---|
| `case_700024_parameters.json` | 单案原始UTC时间、整数日历映射、制度门槛、五种时延条件、默认模型设定和证据边界 | 人类可读/机器可读的参数依据，不是模拟结果 |
| `parameter_crosswalk_v1_v2.csv` | 每个重要参数在V1与V2中的值、变更类型、证据类别和解释 | 用于审计版本差异 |
| `source_metadata.json` | 发布者、API请求、许可、抓取时间、过滤窗口、上游与发布表哈希 | 用于数据溯源；上游原始快照和15列处理表未复制进V2发布目录 |

`source_metadata.json`记录：官方API共取得357条带回应记录；门槛时间窗口为2024-07-01（含）至2026-01-01（不含），要求门槛和回应时间戳完整后保留222条。上游原始快照有15页，SHA-256为 `5ADC7154653C97DF2CD4C69BDCEFFBC5D497314555850B6A76A29F47EBB1A814`；上游15列处理表SHA-256为 `69FB38F6CB2593A6B1AB7602D5D1C68009B08C170C5D59AD21BF908CA724B75B`。二者只作溯源记录，V2实际读取的是两列最小发布表。

## 4. 配置字典

### 4.1 V2专有或重定义字段

| 字段 | 类型 | 默认值 | 有效范围/类别 | 证据属性 | 定义 |
|---|---|---:|---|---|---|
| `model_version` | 字符串 | `2.0.0-uk-petition-case` | 固定 | 模型元数据 | V2语义版本标识 |
| `step_unit` | 字符串 | `day` | 固定 | 模型约定 | 一步按一天解释 |
| `petition_id` | 字符串 | `700024` | 非空 | `case_observed` | 焦点请愿编号 |
| `petition_title` | 字符串 | 英文官方标题 | 非空 | `case_observed` | 焦点请愿标题 |
| `petition_topic_index` | 整数 | 3 | `[0, topic_count)` | 模型映射 | 请愿所属议题索引 |
| `petition_open_step` | 整数 | 0 | `>=0` | `case_observed` | 正式公开的模型步 |
| `petition_close_step` | 整数 | 182 | 大于开放步且小于总步数 | `case_observed_rounded` | 关闭步；从此不再推荐或签署 |
| `petition_initial_heat` | 浮点数 | 1.0 | `>=0` | 反事实 | 请愿对象初始热度 |
| `petition_emotional_intensity` | 浮点数 | 0.65 | 建议 `[0,1]` | 反事实 | 请愿内容情绪强度 |
| `real_response_threshold_signatures` | 整数 | 10,000 | `>0` | `uk_institutional_rule` | 现实政府回应门槛；仅作现实计量 |
| `real_debate_threshold_signatures` | 整数 | 100,000 | 大于回应门槛 | `uk_institutional_rule` | 现实议会辩论考虑门槛 |
| `observed_initial_signatures` | 整数 | 5 | `>=0` | `uk_submission_rule` | 初始化占位；字段名沿用模型接口，不代表单案公开时观测值 |
| `observed_response_threshold_step` | 整数 | 14 | 开放期内 | `case_observed_rounded` | 单案达到10,000的步 |
| `observed_debate_threshold_step` | 整数 | 177 | 回应门槛后、关闭前 | `case_observed_rounded` | 单案达到100,000的步 |
| `observed_debate_step` | 整数 | 237 | 非负 | `case_observed_rounded` | 单案实际辩论日元数据；当前模型不据此触发行动 |
| `observed_final_signatures` | 整数 | 110,519 | 至少100,000 | `case_observed` | 关闭后的官方快照 |
| `trigger_mode` | 字符串 | `observed_calendar` | `observed_calendar` / `synthetic_unique_support` | 研究设计 | 决定回应门槛的数据生成方式 |
| `synthetic_support_threshold_fraction` | 浮点或空 | 0.20 | 合成模式中 `(0,1]` | `synthetic_counterfactual` | 模拟唯一签署者占比门槛；不对应10,000 |
| `signature_probability_on_exposure` | 浮点数 | 0.02 | `[0,1]` | `synthetic_counterfactual` | 开放期被推荐后、尚未签署者在该步签署的概率 |
| `response_delay` | 整数 | 22 | `>=1` | `conditional_sample`或情景 | 触发到回应的整数天数 |
| `response_disposition` | 字符串 | `no_policy_change` | `accepted` / `partially_accepted` / `no_policy_change` | 单案质性编码或情景 | 回应的政策采纳立场 |
| `response_heat_multiplier` | 浮点数 | 1.00 | `>=0` | 反事实 | 回应瞬间焦点请愿热度乘数；1不变、0清零、大于1增热 |
| `direct_response_trust_signal` | 浮点数 | 0.00 | `[-1,1]` | 反事实 | 回应当步传入V1信任更新的直接信号 |
| `response_information_emotional_intensity` | 浮点数 | 0.15 | 建议 `[0,1]` | 反事实 | 新生成政府回应信息的情绪强度 |
| `response_information_initial_heat` | 浮点数 | 0.0 | `>=0` | 反事实 | 新生成政府回应信息的初始热度 |
| `enable_routine_government_publication` | 布尔 | `false` | 布尔 | V2边界 | 是否恢复V1周期性政府发布；默认关闭 |
| `enable_legacy_topic_response` | 布尔 | `false` | 必须为 `false` 才可运行 | V2边界 | V1主题份额回应触发器；V2有意禁用 |

### 4.2 继承V1的主要字段

| 字段 | 类型 | 默认值 | 定义与V2解释 |
|---|---|---:|---|
| `alpha` | 浮点数 | 0.50 | 热度权重；正式扫描0–1，案例不能识别 |
| `steps` | 整数 | 300 | 运行步数；V2解释为天 |
| `population_size` | 整数 | 300 | 模拟公众数；不映射现实签名数 |
| `topic_names` | 字符串元组 | 经济、法治、公共服务、公众发起议题 | 四类议题名 |
| `agenda_topic_indices` | 整数元组 | 0、1、2 | 政府议程内主题；焦点请愿索引3为议程外 |
| `attention_budget` | 整数 | 5 | 每名公众每步消费的信息条数上限 |
| `initial_information` | 整数 | 24 | 初始化普通信息数量 |
| `spontaneous_posts_per_step` | 整数 | 4 | 每步新增普通自发信息数量 |
| `preference_concentration` | 浮点数 | 1.0 | 公众初始偏好Dirichlet集中度 |
| `emotionality_mean` / `emotionality_sd` | 浮点数 | 0.30 / 0.10 | 公众情绪性分布参数 |
| `preference_drift_after` | 整数 | 4 | 同一主导议题连续达到多少步后可漂移 |
| `preference_drift_rate` | 浮点数 | 0.03 | 每步偏好漂移率，未按英国日数据校准 |
| `heat_decay` | 浮点数 | 0.95 | 每步衰减后保留比例，未按英国日数据校准 |
| `minimum_heat` | 浮点数 | 0.01 | 普通信息清理阈值；焦点请愿例外保留 |
| `agenda_target_share` | 浮点数 | 0.70 | 议程份额目标，用于计算议程偏离 |
| `storm_threshold` | 浮点数 | 0.30 | 议程外单主题份额的风暴阈值 |
| `digital_government_level` | 浮点数 | 0.60 | 模型数字政府水平，继承V1 |
| `digital_platform_complexity` | 浮点数 | 0.50 | 平台复杂度，进入学习成本方程 |
| `digital_literacy_mean` / `digital_literacy_sd` | 浮点数 | 0.69 / 0.18 | 公众数字素养初始化参数 |
| `initial_trust_mean` / `initial_trust_sd` | 浮点数 | 0.69 / 0.12 | 政府信任初始化参数 |
| `learning_update_rate` | 浮点数 | 0.08 | 学习成本向目标更新的速率 |
| `trust_update_rate` | 浮点数 | 0.06 | 信任向目标更新的速率 |
| `trust_feedback_strength` | 浮点数 | 0.25 | 信任对互动来源倾向的反馈强度 |
| `seed` | 整数 | 42 | 模拟随机种子 |

`response_strength`、`response_threshold`、`publish_interval`和 `response_strategy`等V1字段仍因继承的配置类而存在，但V2默认分别由显式热度乘数/请愿门槛/发布开关所取代或禁用，不应据其字面解释V2请愿回应。

## 5. 内部状态对象

### 5.1 `PetitionState`

| 字段 | 类型 | 定义 |
|---|---|---|
| `petition_id` | 字符串 | 焦点请愿编号 |
| `petition_item_id` | 整数 | 信息池中焦点请愿对象的内部编号 |
| `opened_step` | 整数 | 开放步 |
| `close_step` | 整数 | 关闭步 |
| `state` | 字符串 | `open`、`response_pending`、`responded`、`debate_eligible`或`closed` |
| `observed_signature_count` | 整数 | 案例日历模式的现实里程碑计数；合成模式不使用它表示合成支持 |
| `response_threshold_step` | 整数或空 | 首次达到回应门槛的步 |
| `debate_threshold_step` | 整数或空 | 达到100,000制度门槛的步；不等于实际辩论日 |
| `response_due_step` | 整数或空 | 回应排定到期步 |
| `response_executed_step` | 整数或空 | 回应发布步 |
| `response_disposition` | 字符串 | 回应政策立场 |

### 5.2 `PendingPetitionResponse`

| 字段 | 类型 | 定义 |
|---|---|---|
| `petition_id` | 字符串 | 待回应请愿编号 |
| `trigger_step` | 整数 | 首次门槛触发步 |
| `due_step` | 整数 | `trigger_step + response_delay` |

同一焦点请愿最多存在一个待回应对象。

## 6. 逐步指标表 `metrics`

粒度：每个模拟步一行。默认完整运行300行。

主键建议：`model_version + petition_id + trigger_mode + alpha + seed + step`。

### 6.1 V1继承字段

| 字段 | 类型 | 定义 |
|---|---|---|
| `step` | 整数 | 从0开始的模拟日 |
| `alpha` | 浮点数 | 本次运行的热度推荐权重 |
| `agenda_share` | 浮点数 | 本步消费中议程内主题占比 |
| `agenda_divergence` | 浮点数 | `clip(1 - agenda_share / agenda_target_share, 0, 1)` |
| `official_attention_share` | 浮点数 | 每名公众推荐列表中政府来源比例的均值 |
| `off_agenda_peak_share` | 浮点数 | 议程外单主题消费份额最大值 |
| `storm` | 0/1 | `off_agenda_peak_share > storm_threshold` |
| `mean_trust` | 浮点数 | 本步公众政府信任均值 |
| `trust_p10` / `trust_p90` | 浮点数 | 本步信任第10/90百分位 |
| `mean_learning_cost` | 浮点数 | 本步学习成本均值 |
| `total_interactions` | 整数 | 本步所有推荐项互动次数 |
| `pool_size` | 整数 | 记录时的信息池对象数 |
| `responses_scheduled` | 整数 | 本步新排程的焦点请愿回应数，V2应为0或1 |
| `responses_executed` | 整数 | 本步发布的焦点请愿回应数，V2应为0或1 |
| `response_effect` | 浮点数 | 传入信任更新的回应信号；V2等于当步 `direct_response_trust_signal` 或0 |
| `topic_share_<索引>_<名称>` | 浮点数 | 各主题占本步总消费的比例 |

### 6.2 V2新增字段

| 字段 | 类型 | 单位/范围 | 定义 |
|---|---|---|---|
| `model_version` | 字符串 | 固定 | V2版本标识 |
| `petition_id` | 字符串 | 无 | 焦点请愿编号 |
| `trigger_mode` | 字符串 | 两类模式 | 本次运行使用的门槛模式 |
| `petition_state` | 字符串 | 状态类别 | 记录时的请愿制度状态 |
| `petition_visible` | 0/1 | 布尔 | 本步焦点请愿是否进入推荐候选 |
| `petition_heat` | 浮点数 | 非负 | 本步记录时、自然衰减前的请愿热度 |
| `petition_exposures` | 整数 | 人 | 本步至少一次被推荐到请愿的模拟公众数 |
| `petition_interactions` | 整数 | 次 | 本步焦点请愿因公众互动增加的热度量 |
| `new_unique_signers` | 整数 | 人 | 合成模式本步首次签署者数；案例日历模式为0 |
| `cumulative_unique_signers` | 整数 | 人 | 已签署的模拟公众数；每人最多一次 |
| `synthetic_support_fraction` | 浮点数 | `[0,1]` | `cumulative_unique_signers / population_size` |
| `observed_signature_count` | 整数 | 现实签名 | 案例日历里程碑值；不可与合成签署者换算 |
| `response_pending` | 0/1 | 布尔 | 是否存在未执行的焦点请愿回应 |
| `response_queue_age_days` | 整数 | 天 | 待办期间当前步减触发步；非待办时为0 |
| `response_due_step` | 整数或空 | 日 | 排定回应步 |
| `petition_response_executed` | 0/1 | 布尔 | 回应是否恰在本步执行 |
| `response_disposition` | 字符串 | 三类 | 回应的政策采纳立场，与是否发布分开 |
| `response_heat_multiplier` | 浮点数 | `>=0` | 回应执行时作用于请愿热度的乘数 |
| `response_heat_delta` | 浮点数 | 热度 | 仅执行当步非零；乘法后的热度减乘法前热度 |
| `direct_response_trust_signal` | 浮点数 | `[-1,1]` | 仅执行当步记录的直接信任信号 |
| `debate_threshold_reached` | 0/1 | 布尔 | 截至本步是否已达到100,000制度门槛 |

注意：`petition_heat`在记录后仍会乘以 `heat_decay`。因此相邻步热度差同时包含互动、可能的回应热度乘数和自然衰减，不能把简单前后差全部归因于政府回应。

## 7. 事件表 `events`

粒度：每行一个离散制度或模型事件。

| 字段 | 类型 | 定义 |
|---|---|---|
| `petition_id` | 字符串 | 焦点请愿编号 |
| `event_type` | 字符串 | 事件类别，见下表 |
| `step` | 整数 | 事件发生步 |
| `value` | 字符串/数值/空 | 事件的计数、到期步或政策立场 |
| `evidence` | 字符串 | `case_observed`、`case_open_time_plus_uk_submission_rule`、`synthetic_counterfactual`、`model_rule`、`case_position_and_model_timing`或 `model_calendar`等 |

事件类别：

| `event_type` | 发生次数 | `value`含义 |
|---|---:|---|
| `petition_opened` | 1 | 初始化的5名提交支持者；开放时间来自单案，人数来自制度规则而非公开时快照 |
| `response_threshold_reached` | 0或1 | 案例模式为现实门槛签名数；合成模式为唯一签署者数 |
| `government_response_scheduled` | 0或1 | 回应到期步 |
| `government_response_published` | 0或1 | `response_disposition` |
| `debate_threshold_reached` | 案例日历模式0或1 | 达到100,000时的现实签名里程碑 |
| `petition_closed` | 1 | 案例模式为最终现实签名快照；合成模式为模型日历关闭值 |

`observed_debate_step=237`目前是配置元数据，不会生成“实际辩论发生”的模型行动事件。`debate_threshold_reached`只表示达到议会辩论考虑门槛，不表示议会必然已辩论。

## 8. 风暴表 `storms`

粒度：每行一个连续风暴区间。

| 字段 | 类型 | 定义 |
|---|---|---|
| `start_step` | 整数 | 风暴开始步 |
| `end_step` | 整数 | 风暴结束步 |
| `duration` | 整数 | 连续风暴步数 |
| `peak_share` | 浮点数 | 区间内最大议程外单主题份额 |

## 9. 运行摘要 `summary`

摘要默认对最后100步计算V1稳态指标，并增加焦点请愿生命周期指标。

### 9.1 V1继承摘要

| 字段 | 定义 |
|---|---|
| `alpha` / `seed` / `steps` / `population_size` | 运行身份和规模 |
| `mean_agenda_divergence` | 末100步议程偏离均值 |
| `system_stability` | 末100步议程偏离的总体方差；越大表示波动越强 |
| `mean_agenda_share` | 末100步议程内消费份额均值 |
| `mean_official_attention_share` | 末100步政府来源曝光均值 |
| `mean_trust` | 末100步模型政府信任均值 |
| `mean_learning_cost` | 末100步学习成本均值 |
| `storm_count` | 与末100步相交的风暴区间数 |
| `storm_frequency_per_100_steps` | 上述区间数按100步标准化 |
| `storm_time_share` | 末100步风暴状态占比 |
| `storm_mean_peak` / `storm_max_peak` | 末窗口相交风暴的平均/最大峰值 |
| `storm_mean_duration` | 末窗口相交风暴的平均持续长度 |
| `full_run_storm_count` | 全运行风暴区间数 |
| `full_run_storm_frequency_per_100_steps` | 全运行风暴频率 |
| `full_run_storm_time_share` | 全运行风暴状态占比 |
| `responses_scheduled` / `responses_executed` | 全运行回应排程/执行总数，V2最多各1 |
| `total_interactions` | 全运行互动总数 |
| `final_pool_size` | 结束时信息池对象数 |

### 9.2 V2新增摘要

| 字段 | 类型 | 定义 |
|---|---|---|
| `model_version` | 字符串 | V2版本 |
| `petition_id` | 字符串 | 焦点请愿编号 |
| `trigger_mode` | 字符串 | 触发模式 |
| `response_delay_days` | 整数 | 配置的回应时延 |
| `response_threshold_step` | 整数或空 | 首次回应门槛步 |
| `response_due_step` | 整数或空 | 排定到期步 |
| `response_executed_step` | 整数或空 | 回应发布步 |
| `realized_response_delay_days` | 整数或空 | 执行步减门槛步，应等于配置时延 |
| `debate_threshold_step` | 整数或空 | 达到100,000门槛步，不是实际辩论日 |
| `petition_close_step` | 整数 | 关闭步 |
| `final_observed_signature_count` | 整数 | 案例里程碑最终计数；合成模式不应用作合成支持 |
| `final_unique_signers` | 整数 | 最终模拟唯一签署者数 |
| `final_synthetic_support_fraction` | 浮点数 | 最终合成支持比例 |
| `response_disposition` | 字符串 | 政策采纳立场 |
| `response_heat_multiplier` | 浮点数 | 回应热度乘数 |
| `direct_response_trust_signal` | 浮点数 | 回应直接信任信号 |
| `petition_heat_auc_pre_7_days` | 浮点或空 | 回应前7个记录步的请愿热度和 |
| `petition_heat_auc_post_7_days` | 浮点或空 | 从回应当步开始7个记录步的请愿热度和 |

回应前后AUC是模型内描述性指标，不能单独解释为回应的因果效应。

## 10. 运行器输出

### 10.1 `v2_run_summaries.csv`

粒度：每个 `condition_id + alpha + seed` 一行。前置字段为：

| 字段 | 定义 |
|---|---|
| `run_id` | `<condition_id>__a<alpha两位小数>__s<seed>` |
| `scope` | `smoke`或`formal`；两类输出不能混为同一证据集 |
| `condition_id` | 五种时延条件之一 |

其余字段来自本字典第9节的 `summary`。条件编号固定为：

- `v1_reference_3`：3天；
- `conditional_p05_11`：11天；
- `case_typical_22`：22天；
- `conditional_p95_57`：57天；
- `conditional_empirical_resample`：按种子从222条条件时延抽取并取整。

### 10.2 `v2_event_log.csv`

粒度：每次运行中的每个事件一行。运行器在第7节事件字段前增加 `run_id`、`scope`、`condition_id`、`alpha`、`seed` 和 `response_delay_days`，从而可把事件表无歧义地连接到摘要表。

### 10.3 `v2_run_manifest.json`

| 字段 | 定义 |
|---|---|
| `status` | 运行是否完整结束 |
| `scope` | 烟雾或正式范围 |
| `evidence_status` | 烟雾时为 `smoke_only_not_formal_evidence`，正式时为 `formal_design` |
| `created_at_utc` | UTC生成时间 |
| `model_version` | V2模型版本 |
| `v1_parent_sha256` / `v2_model_sha256` | 父模型与V2模型哈希 |
| `runner_sha256` / `delay_data_sha256` | 运行器与222条输入表哈希 |
| `run_signature` | 模型版本、父模型哈希、输入哈希和任务列表的确定性SHA-256 |
| `completed_rows` / `event_rows` | 摘要与事件行数 |
| `condition_ids` / `alpha_values` / `seed_values` | 实际完成的设计水平 |
| `workers` | 并行进程数 |
| `python` / `platform` / `numpy` / `pandas` / `scipy` | 运行环境版本 |

当前烟雾清单记录15行摘要、90行事件，并明确标记为非正式证据。

## 11. 正式运行面板的主键与QA

正式运行摘要CSV的最小主键应为：

```text
(delay_condition, alpha, seed)
```

应满足：

- 5个 `delay_condition`；
- 每个条件21个 `alpha`；
- 每个条件—`alpha`组合50个种子；
- 总行数5,250，主键无重复；
- 固定情景时延只能是3、11、22或57；
- `conditional_empirical_resample`中每个种子跨21个 `alpha` 只有一个时延；
- 抽样时延来自冻结222条输入并为正整数；
- 每行同时记录V2模型哈希、V1父模型哈希、输入CSV哈希、运行器哈希和配置签名；
- 烟雾输出与正式输出必须用独立的范围标记和路径。

截至本字典版本，烟雾面板已经生成15行摘要（5个条件×3个 `alpha`×1个种子）和90行事件；单元测试11/11、独立发布QA 9/9通过。正式5,250行面板尚未生成。

## 12. 结果解释禁区

- `responses_executed=1`只表示模型发布了回应，不表示政策被采纳；
- `response_disposition=no_policy_change`只描述政策立场，不推导热度或信任方向；
- `response_heat_multiplier=1`是中性模型假设，不是“现实回应没有热度影响”的估计；
- `direct_response_trust_signal=0`是中性模型假设，不是“现实回应没有信任影响”的估计；
- `debate_threshold_reached=1`表示具备进入辩论考虑的门槛条件，不表示已经举行辩论；
- `system_stability`是方差，数值越大并不意味着系统越稳定；
- 222条时延不能代表所有请愿的无条件时延；
- `observed_signature_count`与模拟唯一签署者数量不能换算。
