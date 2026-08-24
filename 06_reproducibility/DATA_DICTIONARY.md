# 数据字典

## 1. 约定

- 所有 CSV 首行为字段名，浮点数使用小数点，布尔值保存为 `True`/`False`。
- `seed` 是伪随机种子；共同随机种子配对意味着比较条件必须在相同 `alpha` 和相同 `seed` 上对齐。
- 除明确写为“全程”的字段外，模拟汇总指标来自每次 300 步运行的最后 100 步稳态窗口。
- 置信区间上下界均为双侧 95% 区间；具体区间和检验方法由对应表的字段说明决定。

## 2. 正式消融原始表

文件：`../03_data/formal_ablation/raw/formal_replicates_5conditions.csv`

粒度：一行是一组 `condition_id × alpha × seed` 的独立模型运行。主键为 `(condition_id, alpha, seed)`；`replicate` 与 50 个种子的顺序一一对应，但统计配对应优先使用 `seed`，不要只按行序或 `replicate` 合并。

设计：5 个条件 × 21 个 α × 50 个共同随机种子 = 5,250 行；`alpha` 从 0.00 到 1.00，步长 0.05；种子为 73000—73049；每次 300 步、300 个公众智能体。

### 2.1 标识与设计字段

| 字段 | 类型 | 定义 |
|---|---|---|
| `analysis_status` | string | 运行协议版本标识；正式表中的字面值由冻结运行器写入 |
| `condition_id` | string | 条件代码：`full`、`no_emotion`、`no_drift`、`no_response`、`no_trust` |
| `condition_label` | string | 条件的人类可读标签 |
| `condition_order` | integer | 作表/作图排序，不是效应大小 |
| `removed_mechanism` | string | 被关闭机制的代码；完整模型为 `none` |
| `alpha` | float [0,1] | 推荐得分中热度项的权重；相似度权重为 `1-alpha` |
| `replicate` | integer 0–49 | 条件格内重复编号 |
| `seed` | integer | 随机种子，也是跨条件配对键 |
| `steps` | integer | 本次运行的总时间步数 |
| `population_size` | integer | 公众智能体数 |
| `emotion_advantage_enabled` | boolean | 自发信息的情绪优势开关 |
| `preference_drift_rate` | float | 偏好向互动内容移动的更新率；`0` 表示关闭偏好漂移 |
| `response_strength` | float | 政府回应对相关信息热度的保留系数；`1` 表示不降低热度，较小值表示抑制更强 |
| `trust_feedback_strength` | float | 信任对互动概率反馈的强度；`0` 表示关闭该反馈，但信任状态本身仍可更新 |
| `elapsed_seconds` | float | 该次运行墙钟耗时，仅用于性能审计，不是研究结果 |

### 2.2 核心结果指标

| 字段 | 类型/范围 | 操作定义 |
|---|---|---|
| `mean_agenda_divergence` | float [0,1] | 最后 100 步的议程偏离均值；每步为 `clip(1 - agenda_share / agenda_target_share, 0, 1)`，越高表示公众所见推荐列表与政府目标议程越偏离 |
| `system_stability` | float ≥0 | 最后 100 步 `agenda_divergence` 的总体方差（`ddof=0`）；越低表示时间上的议程偏离更稳定，不等同于价值判断上的“更好” |
| `mean_agenda_share` | float [0,1] | 最后 100 步中，推荐给公众的全部条目里政府议程主题所占份额的均值；这是推荐曝光份额，不是随机互动成功率 |
| `mean_official_attention_share` | float [0,1] | 最后 100 步中，每名公众推荐列表里的官方来源条目占比，再跨公众与时间取均值；这是推荐曝光份额 |
| `mean_trust` | float [0,1] | 最后 100 步的公众平均政府信任均值 |
| `mean_learning_cost` | float [0,1] | 最后 100 步的公众平均学习成本均值 |
| `storm_time_share` | float [0,1] | 最后 100 步中处于舆情风暴状态的时间比例 |

### 2.3 风暴、回应和运行审计字段

| 字段 | 类型 | 操作定义 |
|---|---|---|
| `storm_count` | integer | 与最后 100 步相交的风暴事件数；跨窗口事件也会计入 |
| `storm_frequency_per_100_steps` | float | `storm_count / 稳态窗口步数 × 100` |
| `storm_mean_peak` | float | 与稳态窗口相交的风暴事件之峰值注意份额均值；无事件时为 0 |
| `storm_max_peak` | float | 上述事件中的最大峰值；无事件时为 0 |
| `storm_mean_duration` | float | 上述事件持续时间均值（步）；无事件时为 0 |
| `full_run_storm_count` | integer | 300 步全程的风暴事件数 |
| `full_run_storm_frequency_per_100_steps` | float | 全程事件数除以总步数后换算为每 100 步频率 |
| `full_run_storm_time_share` | float [0,1] | 300 步全程处于风暴状态的时间比例 |
| `responses_scheduled` | integer | 全程被安排的政府回应次数 |
| `responses_executed` | integer | 全程实际到期执行的政府回应次数；末尾尚未到期的安排可能使其小于 scheduled |
| `total_interactions` | integer | 全程所有公众互动次数之和 |
| `final_pool_size` | integer | 运行结束时信息池中的信息对象数量 |

## 3. 正式消融处理表的关键字段

### `condition_summary_5conditions.csv`

主键为 `(condition_id, alpha, metric)`。`n` 是该单元的重复数；`mean`、`sd`、`se` 为跨种子描述统计；`mean_t_ci_low/high` 为均值的 t 区间。

### `paired_effects_5conditions.csv`

主键为 `(condition_id, alpha, metric)`，其中 `condition_id` 是待比较消融条件，基准始终是 `full`。`mean_difference` 等于“消融 − 完整”；`n_pairs` 为按共同种子配对的样本数；`bootstrap_ci_*` 是配对差的种子级 bootstrap 区间；`signflip_p_raw` 是配对符号翻转检验；`holm_*` 是相应检验族的 Holm 校正 p 值；`cohen_dz`、`hedges_gz` 及 `rank_biserial` 为配对效应量。`is_primary_alpha` 标记预先选定的主 α。

### `auc_effects_5conditions.csv`

主键为 `(condition_id, metric)`。先对每个种子的 21 点 α 曲线用梯形法求 0—1 区间曲线下面积，再按共同种子比较“消融 − 完整”。效应和检验字段与配对表同义。

## 4. 敏感性原始表（运行器设计字典）

文件：`../03_data/sensitivity/raw/sensitivity_replicates.csv`；设计清单：`sensitivity_manifest.json`；运行器：`../02_experiment_code/run_formal_sensitivity.py`。

本节只记录运行器预设结构，不据不完整文件报告任何敏感性结果。预设主键为 `(scenario_id, alpha, seed)`；19 个情景 × 21 个 α × 50 个共同随机种子，完整设计应有 19,950 行。解释结果前必须先按 manifest 的 `expected_rows`、主键唯一性和每格 50 次重复进行完整性检查。

| 字段 | 类型 | 定义 |
|---|---|---|
| `analysis_status` | string | 敏感性运行协议版本 |
| `run_signature` | string | 整个敏感性设计对象的 SHA-256；用于防止续跑时混入另一设计 |
| `scenario_id` | string | 情景唯一代码 |
| `scenario_kind` | string | `parameter`、`response_strategy` 或 `execution_order` |
| `parameter` | string | 被变动参数或敏感性维度名称 |
| `value` | string/number | 该情景设置值 |
| `simulation_class` | string | 运行器选择的实现类别标识；默认参数情景为 `default` |
| `replicate` | integer 0–49 | 重复编号 |
| `seed` | integer | 共同随机种子，预设为 73000—73049 |
| `alpha` | float [0,1] | 21 个推荐权重点之一 |
| `configuration_json` | JSON string | 该次运行的完整配置快照 |
| `configuration_sha256` | string | 配置快照的 SHA-256 |
| `steps`、`population_size` | integer | 运行规模 |
| `elapsed_seconds` | float | 运行耗时 |

其余模型输出字段（从 `mean_agenda_divergence` 到 `final_pool_size`）与正式消融原始表的同名字段定义完全相同。

## 5. S1 外部验证表

### 5.1 `external/processed/macro_country_panel.csv`

粒度：一行是一个“国家 × GTMI 版本”；候选键为 `(Code, Year)`。现有表为 30 国 × 3 个版本 = 90 行。

| 字段 | 定义 |
|---|---|
| `Code` | 三位国家代码，跨数据源连接键 |
| `OECD_country` | OECD 国家名称 |
| `trust_year` | 信任观测年份，本分析为 2023 |
| `trust_national_pct` | 对国家政府有高度或中高度信任者百分比 |
| `Year` | GTMI 版本年份：2020、2022 或 2025 |
| `Economy` | GTMI 国家/经济体名称 |
| `GTMI` | GovTech Maturity Index 综合指数 |
| `CGSI` | Core Government Systems Index |
| `PSDI` | Public Service Delivery Index |
| `DCEI` | Digital Citizen Engagement Index |
| `GTEI` | GovTech Enablers Index |
| `internet_pct_year` | 互联网使用率实际取值年份，不晚于 2023 |
| `internet_pct` | 使用互联网的人口百分比 |
| `gdp_ppp_pc_year` | 人均 GDP 实际取值年份，不晚于 2023 |
| `gdp_ppp_pc` | PPP 调整、2017 年不变国际元计的人均 GDP |
| `log_gdp_ppp_pc` | `ln(gdp_ppp_pc)` |

### 5.2 `external/processed/macro_spearman.csv`

主键为 `(gtmi_year, predictor)`，共 3 × 5 = 15 行。

| 字段 | 定义 |
|---|---|
| `gtmi_year` | GTMI 版本年份 |
| `predictor` | `GTMI`、`CGSI`、`PSDI`、`DCEI` 或 `GTEI` |
| `outcome` | 结果变量代码，本分析为 `trust_national_pct_2023` |
| `n` | 完整国家数 |
| `spearman_rho` | Spearman 秩相关系数 |
| `p_value` | 该单项 Spearman 检验的原始双侧 p 值 |
| `ci_low`、`ci_high` | 国家级重抽样 percentile bootstrap 的 95% 区间 |
| `bootstrap_reps` | bootstrap 次数，本分析为 5,000 |
| `ci_method` | 区间方法标签 |
| `p_holm_15` | 对 15 个“版本 × 指标”相关统一做 Holm 校正后的 p 值；不能用原始 p 值替代 |

### 5.3 `external/processed/macro_regression_hc3.csv`

主键为 `(gtmi_year, model_predictor, term)`。每个“版本 × 目标指数”模型包含截距、标准化目标指数、标准化互联网使用率和标准化对数人均 GDP 四个系数。

| 字段 | 定义 |
|---|---|
| `gtmi_year` | GTMI 版本年份 |
| `model_predictor` | 本模型的目标 GovTech 指标 |
| `term` | 系数项名称；`z_` 前缀表示总体标准化 |
| `estimate` | OLS 系数 |
| `std_error` | HC3 异方差稳健标准误 |
| `t` | `estimate / std_error` |
| `df` | 残差自由度 |
| `p_value` | 基于 HC3 标准误的双侧 t 检验原始 p 值 |
| `ci_low`、`ci_high` | HC3 系数的 95% t 区间 |
| `covariance` | 协方差估计标签，本表为 `HC3` |
| `n` | 模型中的完整国家数 |

### 5.4 `external/processed/macro_leave_one_out.csv`

主键为 `(gtmi_year, predictor)`。`loo_rho_min`、`loo_rho_max` 是每次剔除一个国家后重新计算 Spearman ρ 所得范围；它只检查相关系数对单一国家的敏感性，不是逐国剔除回归结果，也不是置信区间。

### 5.5 `external/processed/news_sentiment_regression_cluster.csv`

粒度：一行一个回归系数项；键为 `term`。因变量是 `log1p` 平台反馈。模型含情绪强度、负面标题、标题长度、主题、平台和月份项；标准误按新闻 `IDLink` 聚类。

| 字段 | 定义 |
|---|---|
| `term` | 系数项名称；`z_emotion_intensity` 为绝对标题情感的标准化值，`negative` 为负面标题指示变量，`z_headline_chars_log` 为标准化后的 `log1p` 标题字符数，其余为虚拟变量 |
| `estimate` | 条件 log 尺度 OLS 系数 |
| `std_error` | 新闻级聚类稳健标准误 |
| `t` | 系数 t 统计量 |
| `df` | 聚类推断自由度；87,491 对应 87,492 个新闻聚类减 1 |
| `p_value` | 双侧原始 p 值 |
| `ci_low`、`ci_high` | 聚类稳健 95% t 区间 |
| `covariance` | `cluster(IDLink)` |
| `n` | 有效“新闻 × 平台”观测数，本分析为 256,626 |

### 5.6 `external/processed/facebook_public_affairs_article_decay.csv`

粒度：一行一篇符合条件的文章；候选键为 `(IDLink, topic)`，共 27,244 行。

| 字段 | 定义 |
|---|---|
| `IDLink` | UCI 新闻标识符 |
| `topic` | `obama` 或 `palestine` |
| `valid_bins` | 原时间序列中非负的 20 分钟观测格数量 |
| `total_24h_feedback` | 前 72 格累计序列经一阶差分、负增量截零后的 24 小时新增反馈总量 |
| `share_first_6h` | 前 18 格新增反馈占 24 小时总量的比例 |
| `share_first_12h` | 前 36 格新增反馈占 24 小时总量的比例 |

### 5.7 `external/processed/facebook_public_affairs_decay_curve.csv`

主键为 `bin`，共 72 个 20 分钟格。

| 字段 | 定义 |
|---|---|
| `bin` | 1—72 的时间格序号 |
| `hours_since_first_observed` | `bin / 3`，从首次观测起的小时数 |
| `mean_share_of_24h_feedback` | 各文章在该格的 24 小时反馈份额之均值 |
| `ci_low`、`ci_high` | 跨文章标准误的正态近似 95% 区间；下限截断为 0 |

### 5.8 `external/source_data/FigS1_attention_decay_source_data.csv`

在上一曲线表的五个字段之外，增加：

| 字段 | 定义 |
|---|---|
| `empirical_cumulative_share` | 经验 `mean_share_of_24h_feedback` 从第 1 格起的累积和 |
| `lambda_095_share_normalized_to_24h` | 以每格保留率 0.95 构造、并在同一 72 格窗口内归一化的示意几何曲线 |
| `lambda_095_cumulative_share` | 上述几何曲线累积和 |
| `n_articles` | 经验曲线的文章数，逐行恒为 27,244 |

`FigS1_attention_decay_landmarks.csv` 保存图中文字标注所需的 6 小时和 12 小时累计份额。λ=0.95 曲线是同窗口比较基准，不是由 UCI 数据估计的模型参数。

## 6. 汇总索引表

### `external/dataset_sources.csv`

| 字段 | 定义 |
|---|---|
| `source` | 数据集正式名称 |
| `url` | 官方来源或 DOI |
| `license` | 数据提供方声明的许可/使用条款 |
| `downloaded_file` | 原项目中的下载相对路径 |
| `used_data` | 实际纳入的年份、字段和样本范围 |
| `role` | 在验证中的作用 |

### `external/final_conclusion_data.csv`

| 字段 | 定义 |
|---|---|
| `evidence_family` | 证据族：正式消融主 α、α 曲线面积、外部宏观、外部新闻或外部衰减 |
| `comparison` | 比较对象的可读说明 |
| `metric` | 指标或结果变量 |
| `estimate` | 点估计 |
| `ci_low`、`ci_high` | 95% 区间；方法见 `p_definition` 及来源表 |
| `p_value` | 与该行定义匹配的 p 值；无零假设检验时为空 |
| `p_definition` | 检验及多重比较校正口径 |
| `n` | 统计单位数量 |
| `unit` | 配对种子、国家、新闻平台观测或文章等统计单位 |
| `direction` | 差值方向或估计量尺度 |

该表是机器可读的报告索引。复核任何结论时，应同时查阅对应原始/处理表和冻结分析脚本，不能仅凭汇总表推断额外因果关系。
