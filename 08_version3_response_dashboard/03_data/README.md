# Version 3 数据说明

## 1. 本目录实际包含什么

| 文件 | 行/结构 | 在V3中的用途 |
|---|---|---|
| `case_700024_parameters.json` | 单案事件和参数映射 | 记录英国议会电子请愿700024的制度时间线与证据边界 |
| `uk_petition_response_delays_222.csv` | 222行、2列 | 提供11、22、57天条件时延情景及正式设计的经验重抽样池 |
| `source_metadata.json` | 来源与筛选元数据 | 记录官方入口、检索时间、许可、上游哈希和条件样本筛选 |

本目录**不包含**微博热搜逐条数据、领导留言板逐条数据、政府每日发布真实数据，也没有真实“微博—留言板”指数结果。

## 2. 英国议会电子请愿来源

公开官方入口：

- [英国议会电子请愿首页](https://petition.parliament.uk/)
- [请愿制度与10,000/100,000门槛说明](https://petition.parliament.uk/help)
- [已有回应请愿JSON查询](https://petition.parliament.uk/petitions.json?state=with_response)
- [请愿700024 JSON](https://petition.parliament.uk/petitions/700024.json)
- [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)

两列最小处理表SHA-256：

```text
F88BE53E79989B755106C406C5311E41559930AEB58BBFC8A2A56BCB319692BC
```

它与V2发布的最小表相同，V3没有修改请愿编号或回应时延。

## 3. 222条时延样本如何形成

上游查询限定为具有政府回应的请愿。原始查询得到357条记录，之后要求：

- 达到10,000签名的时间在2024-07-01（含）到2026-01-01（不含）；
- 10,000门槛时间和政府回应时间都完整；
- 回应时间晚于门槛时间。

筛选后得到222条。时延为：

```text
response_delay_days =
  (government_response_at - threshold_reached_at) / 24小时
```

复核统计：最小6.21天、P5约11.07天、中位数约21.65天、均值约24.41天、P95约56.52天、最大128.01天。700024自身约为21.793天。

这是**条件于已经观察到政府回应**的样本。它不能估计所有请愿的回应概率，也可能低估尚未回应或超出观察窗的长等待。

## 4. 数据在V3中的使用

Pilot只使用两个固定条件：

- `early_p05_11`：11天；
- `late_p95_57`：57天。

正式设计声明五个条件：3、11、22、57天，以及从222个时延中按种子抽取一个值并四舍五入为至少1天。经验抽样使用与ABM分离的随机流；同一种子的抽样值在21个 `alpha`和两个回应热度乘数中保持不变。

10,000和100,000是现实绝对签名门槛。默认 `observed_calendar`模式直接重放案例里程碑，不把10,000或100,000换算成300个智能体的比例。`synthetic_unique_support`模式使用模拟支持比例，只用于反事实机制实验。

## 5. `case_700024_parameters.json`的版本提示

该JSON从V2继承，用于保存案例事实和V2父版本的参数证据边界。其中：

```text
model_defaults.enable_routine_government_publication = false
```

描述的是V2父版本默认值，不是V3有效配置。V3在 `Version3Config`中固定覆盖为：

```text
enable_routine_government_publication = true
publish_interval = 1
```

同理，JSON中的 `response_heat_multiplier=1.0`仍是中性基准；V3 pilot在不改变其他条件的情况下另加入0.70组。每日发布规则和0.70都属于研究设计，不是700024观测参数。

## 6. 数据没有提供什么

请愿API没有提供：

- 个体用户推荐或曝光日志；
- 连续社交媒体舆情热度；
- 回应前后的政府信任量表；
- 随机化回应时间；
- 政府内部排程、阅读或决策日志。

因此，`alpha`、30%立即降温、偏好漂移、每日发布频率、热度衰减和信任机制都不能被这222条时延或700024单案识别。

## 7. 微博热搜与领导留言板：当前数据状态

公开入口：

- [微博实时热搜榜](https://s.weibo.com/top/summary?cate=realtimehot)
- [人民网领导留言板](https://liuyan.people.cn/)
- [领导留言板聚合数据报告](https://leaders.people.com.cn/GB/178291/462227/index.html)

公开可浏览不等于开放数据许可。当前项目没有得到一份可再利用、同时间、同地区、同主题口径且去除个人信息的成对数据快照，所以没有把任何真实微博或留言板数据放进本目录。

`build_hotspot_demand_index.py`定义了未来授权数据的标准输入模式，但不会自行采集数据。其严格列集合为：

```text
source, observed_at, region, topic, rank, heat, count,
record_id, access_route, license_note, data_scope
```

其中 `data_scope`必须明确标记数据是合成测试、授权真实数据还是其他范围。标准输入不得包含昵称、账号、正文、手机号、邮箱、精确地址或其他可识别个人的信息。

## 8. 后续真实数据接入的最低要求

1. 先确认服务条款、版权、个人信息保护、伦理审批和再发布许可；
2. 预先固定日期、地区、采集频率和统一主题代码本；
3. 仅保存必要的主题级、日期级、地区级聚合；
4. 记录缺失日、审核公开规则和采集故障；
5. 保存输入文件SHA-256、获取路径、许可说明和代码本版本；
6. 合成数据必须标记为 `synthetic_test`，不能与真实分析混合；
7. 未同时具备微博与留言板正质量分布的窗口不得生成核心对齐指数。

详细格式、公式和解释限制见 [EXTERNAL_INDEX_GUIDE.md](../05_documents/EXTERNAL_INDEX_GUIDE.md)。
