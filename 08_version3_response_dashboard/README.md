# Version 3：政府每日发布、回应降温实验与双榜诊断

## 版本定位

Version 3（V3）是在不覆盖 Version 1（V1）或 Version 2（V2）的前提下建立的独立版本。它继续使用英国议会电子请愿700024的制度时间线，并增加三项内容：

1. 政府每个模拟日发布一条日常信息；
2. 在相同回应流程下比较 `response_heat_multiplier=1.00` 与 `0.70`；
3. 同时记录模型内部“热度热点榜”与“模拟公众潜在诉求榜”的偏离程度，并提供一个与模型分离的、离线的“微博热搜×领导留言板”指数适配器。

V3模型标识为：

```text
3.0.0-response-dashboard-pilot
```

父版本V2模型的冻结SHA-256为：

```text
83BCD501B5A22C59832CC5441FFDF1054361E46C75E1BEE39F70E8E8CA0FC8DF
```

V1祖先模型的冻结SHA-256为：

```text
AB78E6C64AFB6FD487E40A48FBBCD1B09A84EE3FBC9085530F8833DE3543D7EC
```

当前状态：**120次探索性pilot已经完成；计划中的10,500次正式实验尚未运行。** Pilot用于检查机制、配对设计与信号，不是正式论文证据。项目目前没有一组同时满足时间、地区、主题口径、授权和隐私要求的真实“微博热搜—领导留言板”成对数据，因此外部指数模块目前只是离线适配器和合成/受控输入测试工具，不能宣称已经完成外部验证。

## V3新增了什么

### 每日政府信息

`Version3Config`固定启用：

```text
enable_routine_government_publication = True
publish_interval = 1
```

因此，300步运行会产生300条日常政府信息。回应到期的那一天还会额外产生一条 `government_response` 信息，所以该日一共发布两条政府来源信息。

“发布”不等于“公众看见”。日常政府信息仍须进入与其他内容相同的推荐池，由原有推荐公式排序；模型没有给它保留席位，也没有保证曝光。V3分别记录：

- 日常政府信息发布数；
- 日常政府信息在推荐结果中的注意力份额和触达人数份额；
- 请愿回应信息的注意力份额和触达人数份额。

120次pilot中，每次运行都发布了300条日常政府信息和1条请愿回应；开放期日常政府信息注意力份额的跨运行均值约为1.01%，触达份额均值约为3.91%。回应信息在回应后14日窗口中的平均注意力份额为0。后者说明“生成一条回应信息”本身并不能保证它被推荐，而不是说明现实政府回应没有受众。这些只是模型机制诊断，不是现实曝光率估计。

### 回应热度的两组设置

| 条件 | `response_heat_multiplier` | 准确含义 |
|---|---:|---|
| `response_heat_100` | 1.00 | 政府照常排程并发布回应，但不在回应瞬间强制改变焦点请愿热度 |
| `response_heat_070` | 0.70 | 政府照常排程并发布回应，并在回应瞬间把焦点请愿热度乘以0.70 |

`1.00`不是“无回应”或“无政府”组。两组都有每日政府信息、制度门槛、等待队列、正式回应信息、`no_policy_change`政策立场和一次性回应事件；唯一计划内差别是是否在回应瞬间强制降低30%请愿热度。`direct_response_trust_signal`在两组都保持0，因此V3没有把“政府回应”自动解释为信任上升。

V3把立即作用与当日后续结果分开记录：

- `response_heat_before_immediate`：乘法之前的请愿热度；
- `response_heat_after_immediate`：乘法之后、公众当日互动之前的请愿热度；
- `realized_heat_reduction_fraction`：实际立即降幅；
- `petition_heat_end_of_response_day`：又经历了当日推荐和互动之后的热度。

### 模型内部双榜诊断

每个时间步形成三组四议题分布：

- `hotspot_share_*`：当前可见信息按热度聚合的模型内部热点分布；
- `current_demand_share_*`：公众经过推荐、互动和偏好漂移后的当前潜在偏好分布；
- `baseline_demand_share_*`：同一批公众初始化时的潜在偏好分布。

模型计算总变差距离、归一化Jensen–Shannon散度、Top-2重合率、Top-1一致率和排序相关。`government_dashboard_mode="compare_only"`表示这些指标只用于观察，不会改变政府当天发布哪个议题，也不会反过来改变推荐公式。

这里的“诉求”是模拟偏好代理，不是领导留言板真实留言，更不是所有公民的真实需求。模型内部指标与外部真实指数的区别见 [EXTERNAL_INDEX_GUIDE.md](05_documents/EXTERNAL_INDEX_GUIDE.md)。

## 单步行动顺序

一个时间步约定为一天，顺序为：

1. 政府发布一条日常信息，并检查是否执行已到期的请愿回应；
2. 系统生成普通自发信息；
3. 平台按 `alpha × 归一化热度 + (1-alpha) × 偏好相似度` 推荐；
4. 公众消费、互动，信息获得局部热度，公众偏好可漂移；
5. 模型记录请愿曝光和合成模式下的唯一签署者；
6. 计算议程、信任和风暴等指标；
7. 监测请愿门槛并至多排程一次回应；
8. 更新学习成本与政府信任；
9. 计算热点—潜在诉求诊断并写入逐步记录；
10. 信息热度衰减，普通低热度信息被清理，焦点请愿对象保留审计状态。

案例日历模式在第14步达到10,000签名。11天组在第25步回应，57天组在第71步回应。政府行动位于每日循环开头，所以立即热度乘法先于当日公众互动。

## 120次pilot设计

Pilot是一个完整的四因素配对矩阵：

| 因素 | 水平 |
|---|---|
| `alpha` | 0.40、0.60、0.80 |
| 回应时延 | 11天（条件样本P5附近）、57天（条件样本P95附近） |
| 共同随机种子 | 73000–73009，共10个 |
| 回应热度乘数 | 1.00、0.70 |

总运行数为 `3 × 2 × 10 × 2 = 120`；每次300名公众、300步。输出包括120行运行摘要、36,000行逐步指标、36,720行事件日志和一个带代码/数据哈希的清单。

声明的主要估计量是：在同一 `alpha` 和同一种子内，以回应后14日请愿热度AUC的 `log1p` 为结果，计算“早回应减晚回应”在0.70组与1.00组之间的配对差分中的差分：

\[
\Delta_\alpha=
\left[Y_{11,0.70}-Y_{57,0.70}\right]
-\left[Y_{11,1.00}-Y_{57,1.00}\right].
\]

它隔离的是“强制热度乘法是否改变早晚回应差异”，不是政府回应的全部现实因果作用。Pilot只有10个种子/单元格，不应用其显著性检验替代正式实验。

### Pilot结果应怎样解读

所有0.70组都在回应动作的瞬间实现了精确0.30降幅，所有1.00组的立即降幅为0，说明机制按设计执行。以回应后14日 `log1p(AUC)` 为结果，0.70相对1.00的配对降温效应在六个 `alpha × 时延` 单元中为0.2000–0.3287，约对应18.1%–28.0%的AUC降低；六个双侧精确符号翻转检验均为 `p=0.001953`。这是代码中30%瞬时降温规则产生的模型后果，不是现实政府回应的经验因果估计。

如果只看0.70组，11日早回应在三个alpha下都比57日晚回应具有更低的14日热度AUC。然而，真正控制1.00组之后，三个alpha等权汇总的“时机×降温”交互为−0.0049，种子整块bootstrap 95% CI为[−0.0414, 0.0302]，精确 `p=0.8008`，没有检出稳定的“越早回应，额外降温越强”。分层结果方向不一致：`alpha=0.40`的交互为负且Holm校正 `p=0.0352`，`alpha=0.60`和0.80在Holm校正后不显著。合理结论是“pilot检出了直接降温机制，但尚未检出稳健的早晚时机调节，而且可能存在alpha异质性”。

完整数值、效应量和解释边界见 [V3_PILOT_STATISTICAL_REPORT.md](05_outputs/pilot/V3_PILOT_STATISTICAL_REPORT.md)，论文图见 [Figure_V3_response_pilot.pdf](04_figures/Figure_V3_response_pilot.pdf)。

## 计划中的正式实验

正式设计已写入运行器，但尚未执行：

- 5个时延条件：3、11、22、57天及222条已回应请愿的条件经验重抽样；
- 21个 `alpha`：0.00、0.05、……、1.00；
- 50个共同随机种子：73000–73049；
- 2个回应热度乘数：1.00和0.70；
- 合计 `5 × 21 × 50 × 2 = 10,500` 次。

经验重抽样使用与智能体模型分离的随机流；同一种子的抽样时延在全部 `alpha` 和两个热度条件中保持一致。只有当10,500行摘要、3,150,000行逐步数据、主键、每格重复数、哈希和统计分析均通过正式QA后，才能把结果写成正式结论。

## 外部“微博热搜×领导留言板”指数

[build_hotspot_demand_index.py](02_experiment_code/build_hotspot_demand_index.py)是一个无网络采集功能的离线适配器。它只接受本地、来源标注完整、去除个人信息的标准CSV，输出：

- 七日滚动主题分布；
- 热点—诉求对齐度、盲区度和Top-K覆盖率；
- 可选的政府发布倾向 `HotBias`；
- 分主题可见性缺口；
- 输入哈希与运行元数据。

公开入口可用于理解数据语义和评估授权，不代表允许批量抓取：

- [微博实时热搜榜](https://s.weibo.com/top/summary?cate=realtimehot)
- [微博热搜相关说明](https://kefu.weibo.com/faqdetail?id=21636)
- [人民网领导留言板](https://liuyan.people.cn/)
- [领导留言板数据报告入口](https://leaders.people.com.cn/GB/178291/462227/index.html)
- [领导留言板帮助与用户规则](https://liuyan.people.com.cn/help)

当前仓库没有获授权、同时间、同地区、同主题口径的真实成对输入，因此没有外部真实指数结果。详见 [EXTERNAL_INDEX_GUIDE.md](05_documents/EXTERNAL_INDEX_GUIDE.md)。

## 目录

```text
08_version3_response_dashboard/
├─ README.md
├─ CHANGELOG_FROM_V2.md
├─ VERSION.json
├─ 01_model/
│  ├─ base_v1.py
│  ├─ base_v2.py
│  └─ model_v3.py
├─ 02_experiment_code/
│  ├─ run_v3_experiment.py
│  ├─ analyze_v3_pilot.py
│  ├─ build_v3_pilot_figure.py
│  └─ build_hotspot_demand_index.py
├─ 03_data/
├─ 04_tests/
├─ 04_figures/
├─ 05_documents/
│  ├─ MODEL_CARD_V3.md
│  └─ EXTERNAL_INDEX_GUIDE.md
├─ 05_outputs/
│  ├─ pilot/
│  └─ external_index_demo/
└─ 06_reproducibility/
```

## 运行方法

从仓库根目录执行模型测试：

```powershell
python -m unittest discover -s 08_version3_response_dashboard/04_tests -v
```

重建pilot会替换当前pilot文件，只有明确需要时才使用 `--overwrite`：

```powershell
python 08_version3_response_dashboard/02_experiment_code/run_v3_experiment.py --scope pilot --workers 4 --overwrite
python 08_version3_response_dashboard/02_experiment_code/analyze_v3_pilot.py --overwrite
python 08_version3_response_dashboard/02_experiment_code/build_v3_pilot_figure.py --overwrite
```

正式设计命令如下；该命令会执行10,500次运行，而不是快速测试：

```powershell
python 08_version3_response_dashboard/02_experiment_code/run_v3_experiment.py --scope formal --workers 8
```

外部适配器只读取本地标准CSV：

```powershell
python 08_version3_response_dashboard/02_experiment_code/build_hotspot_demand_index.py `
  --input path/to/authorised_standard_input.csv `
  --output-dir 08_version3_response_dashboard/05_outputs/external_index `
  --window-days 7 `
  --top-k 3 `
  --weibo-weight rank
```

## 最低报告口径

引用V3时至少同时报告：模型版本和Git提交、V1/V2父哈希、触发模式、回应时延、`alpha`、随机种子、`response_heat_multiplier`、`direct_response_trust_signal`、每日政府发布规则、发布与曝光的区别，以及结果属于pilot还是正式实验。使用外部指数时还必须报告数据授权、时间与地区覆盖、主题编码规则、缺失日处理、`data_scope`和输入文件SHA-256。
