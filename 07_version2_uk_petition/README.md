# Version 2：英国议会电子请愿案例约束模型

## 版本定位

Version 2（V2）是在**不覆盖 Version 1（V1）**的前提下建立的案例约束版本。它以英国议会电子请愿700024“Ban fossil fuel advertising and sponsorship”为说明性个案，把“请愿公开—越过制度门槛—等待—政府正式回应—进入辩论考虑—关闭”的制度链加入原有公众—平台—政府三方智能体模型。

V2的目的不是把英国请愿网站说成个性化社交媒体，也不是把一个英国案例当作完整现实验证。它只把有官方记录支持的制度时间和回应时延用于约束一个政策原型；推荐权重、偏好漂移、热度变化和信任变化仍由模型作反事实探索。

V1核心文件保持不变。V2携带一份逐字节相同的V1基线快照，再在独立文件中扩展。冻结V1的SHA-256为：

```text
AB78E6C64AFB6FD487E40A48FBBCD1B09A84EE3FBC9085530F8833DE3543D7EC
```

当前状态：**代码与复现接口就绪；15次烟雾运行已完成（5个条件×3个 `alpha`×1个种子），单元测试11/11通过，独立发布QA 9/9通过。烟雾结果不是正式研究证据；计划中的5,250次正式实验尚未运行。**

## V2增加了什么

1. 一个具有唯一编号、开放期和关闭时点的持续性请愿信息对象；它不会像普通低热度信息一样在开放期内被清理。
2. 累积支持、一次性门槛事件、待回应队列和一次性正式回应，避免同一请愿被反复排程。
3. 10,000签名政府回应门槛与100,000签名议会辩论考虑门槛的制度事件。
4. 两种不可混用的触发模式：案例日历回放与合成唯一支持者实验。
5. 将“回应已发布”“政策诉求是否被采纳”“回应是否改变热度”“回应是否直接改变信任”拆成四个字段和过程。
6. 请愿曝光、互动、唯一签署者、回应队列年龄、回应前后热度积分等逐步指标，以及带证据类型的事件日志。
7. 3、11、22、57天及条件经验重抽样五种回应时延情景的统一运行器。

完整差异见 [CHANGELOG_FROM_V1.md](CHANGELOG_FROM_V1.md)，模型适用范围见 [MODEL_CARD_V2.md](05_documents/MODEL_CARD_V2.md)，字段解释见 [DATA_DICTIONARY_V2.md](05_documents/DATA_DICTIONARY_V2.md)。

## 四类信息必须分开

| 类别 | V2中的内容 | 可以怎样表述 | 不应怎样表述 |
|---|---|---|---|
| 700024单案观测 | 公开后约14天越过10,000；约22天后回应；第177天越过100,000；第182天关闭；快照110,519签名；政府未采纳主要诉求 | 单案制度时间线 | 英国全部请愿的平均规律 |
| 222条条件样本 | 已回应请愿中，门槛到回应时延P5约11天、中位数约22天、P95约57天 | 条件于已回应的时延情景依据 | 所有请愿的回应概率或无偏总体时延 |
| 从V1继承 | 三类智能体、推荐公式、偏好漂移、互动增热、自然衰减、风暴和学习成本/信任动力学等 | 保持模型结构可比 | 已经被英国案例校准 |
| 反事实假设 | `alpha`、合成签署概率、合成门槛、回应热度乘数、直接信任信号等 | 情景参数或研究设计假设 | 现实英国参数估计值 |

## 两种触发模式：不能换算

### `observed_calendar`（默认）

该模式按700024的观测日历重放制度里程碑：第14步达到10,000签名，第177步达到100,000签名，第182步关闭。这里一个时间步约定为一天。模型在第14步排程政府回应，再按所选 `response_delay` 等待。

此模式中的 `observed_signature_count` 不由300个模拟公众产生：10,000、100,000和110,519来自案例里程碑；初始值5来自英国请愿提交需5名支持者的制度规则，并不是API记录的700024公开瞬间签名数。现实的10,000与100,000是绝对签名数。

### `synthetic_unique_support`

该模式用于反事实机制实验。模拟公众只有在请愿仍开放且被推荐到时才可能签署，每名智能体至多签一次；累计唯一签署者占300名模拟公众的比例达到 `synthetic_support_threshold_fraction` 后，模型排程一次回应。

这个比例的分母是模拟公众数，不是英国人口，也不是现实签名数。因此：

> **不得把10,000个现实签名换算成300个智能体中的某个比例；不得在同一条结果中混用 `observed_signature_count` 与 `cumulative_unique_signers`。**

## 一次运行的行动顺序

每个时间步按以下顺序执行：

1. 政府检查并执行已到期的请愿回应；
2. 系统生成普通自发信息；
3. 平台用V1的推荐公式为公众排序可见信息；关闭后的请愿不再进入推荐候选；
4. 公众消费和互动，互动增加对应信息热度；V1偏好漂移继续运行；
5. V2记录请愿曝光，并在 `synthetic_unique_support` 模式中抽取新的唯一签署者；
6. 计算议程、舆情风暴等指标；
7. 监测门槛并至多排程一次政府回应；
8. 更新学习成本和政府信任；
9. 写入逐步记录；
10. 信息热度自然衰减并清理普通低热度信息；焦点请愿对象保留以供审计。

因为政府行动位于时间步开头，而门槛监测位于同一步后段，触发于第14步、延迟22天的回应会在第36步执行，正好满足 `14 + 22 = 36`。

## 回应、采纳、降温和信任的解耦

| 问题 | 字段/事件 | 默认值 | 证据边界 |
|---|---|---:|---|
| 回应是否发布 | `government_response_published`、`response_executed_step` | 按门槛与时延发布一次 | 单案可观测 |
| 政策诉求是否采纳 | `response_disposition` | `no_policy_change` | 来自700024回应文本的质性编码 |
| 回应是否让请愿降温 | `response_heat_multiplier`、`response_heat_delta` | 1.00，即不强制改变热度 | 反事实；官方数据不能识别因果降温 |
| 回应是否直接改变信任 | `direct_response_trust_signal` | 0.00 | 反事实；请愿数据没有信任量表 |

默认设置有意保持中性：政府发布回应，但不因“发布了”就自动断言政策接受、热度下降或信任上升。V1中由推荐曝光、学习成本和议程外曝光产生的信任动力学仍继续运行；这里只把**回应事件的直接信任信号**单独设为零。

## 关键默认参数

| 参数 | V2默认值 | 来源/解释 |
|---|---:|---|
| `steps` | 300 | 继承V1运行长度；V2约定一步为一天 |
| `population_size` | 300 | 继承V1；不代表300人对应多少现实签名 |
| `alpha` | 0.50 | 继承V1、反事实扫描参数；案例不能识别 |
| `response_delay` | 22 | 222条已回应条件样本的中位数21.65天四舍五入 |
| `petition_open_step` | 0 | 以700024正式公开为日历原点 |
| `observed_response_threshold_step` | 14 | 单案约14.28天，取整数步 |
| `observed_debate_threshold_step` | 177 | 单案从公开到100,000签名，取整数步 |
| `petition_close_step` | 182 | 单案从公开到关闭，取整数步 |
| `observed_debate_step` | 237 | 单案实际辩论日的元数据；不等于100,000门槛日 |
| `observed_final_signatures` | 110,519 | 单案关闭后的官方快照 |
| `response_disposition` | `no_policy_change` | 回应没有采纳“禁止广告和赞助”的主要诉求 |
| `response_heat_multiplier` | 1.00 | 中性反事实基准，不强制降温 |
| `direct_response_trust_signal` | 0.00 | 中性反事实基准，不强制增信 |
| `synthetic_support_threshold_fraction` | 0.20 | 合成模式研究设计假设，非现实换算 |
| `signature_probability_on_exposure` | 0.02 | 合成模式研究设计假设，非案例估计 |

V1的热度衰减率、偏好漂移率、互动规则、学习成本和信任系数在V2中仍被继承，但它们没有因为“一步=一天”而自动变成英国每日参数。

## 目录

```text
07_version2_uk_petition/
├─ README.md
├─ CHANGELOG_FROM_V1.md
├─ VERSION.json
├─ 01_model/
│  ├─ base_v1.py
│  └─ model_v2.py
├─ 02_experiment_code/
│  └─ run_v2_experiment.py
├─ 03_data/
│  ├─ README.md
│  ├─ case_700024_parameters.json
│  ├─ parameter_crosswalk_v1_v2.csv
│  ├─ source_metadata.json
│  └─ uk_petition_response_delays_222.csv
├─ 04_tests/
├─ 05_documents/
│  ├─ MODEL_CARD_V2.md
│  └─ DATA_DICTIONARY_V2.md
├─ 05_outputs/
│  └─ smoke/
│     ├─ v2_run_summaries.csv
│     ├─ v2_event_log.csv
│     └─ v2_run_manifest.json
└─ 06_reproducibility/
   ├─ build_v2_manifest.py
   ├─ release_qa_v2.json
   └─ validate_v2.py
```

运行器和验证器只把V2结果写入V2目录，不会覆盖V1正式实验数据。

## 环境与测试

从仓库根目录执行：

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s 07_version2_uk_petition/04_tests -v
python 07_version2_uk_petition/06_reproducibility/validate_v2.py
```

验证内容包括V1哈希不变、V2基线副本逐字节相同、同一配置可重复、门槛只触发一次、回应按期且只执行一次、请愿对象持续存在、两种触发模式不混用，以及经验时延按种子而非按 `alpha` 重抽样。

## 烟雾验证

```powershell
python 07_version2_uk_petition/02_experiment_code/run_v2_experiment.py --scope smoke --workers 1 --overwrite
```

当前烟雾矩阵已经完成15次运行：5个时延条件×`alpha={0.40,0.60,0.80}`×种子73000，共生成15行摘要和90行事件。它只检查数据管道、场景生成、输出字段和可重复性，不能作为论文的正式估计或置信区间输入。运行清单把证据状态明确写为 `smoke_only_not_formal_evidence`。

## 正式5,250次实验

```powershell
python 07_version2_uk_petition/02_experiment_code/run_v2_experiment.py --scope formal --workers 8
```

正式设计为：

- 5个回应时延条件：理论基准3天、条件样本P5的11天、条件样本中位数的22天、条件样本P95的57天、按222条条件样本经验重抽样；
- 21个 `alpha`：0.00、0.05、……、1.00；
- 50个共同随机种子：73000–73049；
- 合计 `5 × 21 × 50 = 5,250` 次完整运行；
- 每次300名公众、300个时间步，摘要使用末100步窗口；
- 经验重抽样时，同一个种子只抽取一次整数天时延，并在该种子的21个 `alpha` 水平保持相同，防止破坏配对设计。

正式实验运行前后都应执行测试和V2验证器。仅当原始结果行数、主键、每格重复数、时延取值、运行签名和文件哈希全部通过QA后，才可把结果写成论文过去时结论。

## 数据来源与许可

`03_data/uk_petition_response_delays_222.csv`包含222条已回应请愿的编号和“越过10,000签名门槛到政府回应”的天数。样本来自英国议会官方请愿API的 `state=with_response` 查询，经固定时间窗与完整时间戳筛选。数据依照 Open Government Licence v3.0 使用。

这222条记录**条件于已经获得回应**，不能估计所有请愿的回应概率，也可能遗漏尚未回应的长等待记录。单案、总体条件样本及模型反事实参数的详细边界见模型卡和数据字典。

## 最低引用口径

在论文或报告中引用V2时，至少同时写明：

1. V2版本号与Git提交；
2. 使用的触发模式；
3. 所用时延条件；
4. `alpha` 与随机种子；
5. `response_disposition`、`response_heat_multiplier` 和 `direct_response_trust_signal`；
6. 222条样本是“条件于已回应”；
7. V2是案例约束政策原型，不是对英国制度或中国数字政府的完整因果验证。
