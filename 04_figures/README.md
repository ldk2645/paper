# 正式论文图件说明

本目录收录论文主图与补充图。每张图均同时提供可编辑矢量格式（SVG、PDF）和高分辨率预览格式（600 dpi PNG、600 dpi TIFF）。Fig. 2–6及两张既有补充图由正式分析结果逐字节归档；Fig. S1和Fig. S2由本发布包内的当前脚本从随附源数据生成。

## 实验口径

- 正式仿真采用 21 个推荐权重 `α`（0.00–1.00，步长 0.05）、每个“条件 × α”单元 50 个共同随机种子（73000–73049）。
- 每次运行含 300 名公众智能体和 300 个时间步；稳态汇总窗口为第 200–299 步，共 100 步。
- `N = 50` 表示每个实验单元的独立随机种子重复数，不是公众智能体数量。
- 图中的置信区间只在明确标注时构成跨随机种子或跨观测单位的不确定性估计；代表性轨迹图不承担跨随机种子推断。

## 主图

| 图件 | 核心结论与证据角色 | 源数据 | `n` 与区间定义 |
|---|---|---|---|
| `main/Fig2_phase_transition` | 随 `α` 增大，完整模型的议程偏离和舆情风暴占比上升、政府信任下降；主要变化集中在 `α = 0.55–0.60` 附近。四个面板分别展示议程偏离、偏离方差、风暴时间占比和政府信任。 | `fig2_phase_source_data.csv` | 每个 `α` 为 50 个种子的均值；阴影为双侧 95% Student-*t* 均值置信区间（df = 49）。 |
| `main/Fig3_critical_point` | 以议程偏离曲线的三点移动平均最大内部梯度定义临界点，完整模型的点估计为 `αc = 0.60`，95% 区间为 `[0.55, 0.60]`。 | `fig3_critical_curve_source_data.csv`、`fig3_critical_bootstrap_source_data.csv` | 原曲线每个 `α` 含 50 个种子；临界点区间来自 5,000 次“完整 α 曲线”的配对种子块自助法，识别率为 100%，区间取 2.5% 与 97.5% 分位数。 |
| `main/Fig4_formal_ablation` | 四种机制消融对系统结果的影响具有指标依赖性和 `α` 依赖性。在预设主比较点 `α = 0.60`，移除情绪优势对议程偏离与风暴占比的改变最大；其余机制对偏离、波动和信任表现出不同方向与幅度的影响。 | `fig4_ablation_source_data.csv` | 纵轴为“消融条件 − 完整模型”；同一 `α` 下按共同随机种子配对，`n = 50` 对；阴影为 10,000 次配对种子自助法的双侧 95% 分位数区间。该图不含任何旧的单次重复探索结果。 |
| `main/Fig5_representative_trajectories` | 用一个预先按规则选出的代表性共同种子，展示低、中、较高 `α`（0.30、0.55、0.70）下议程偏离、政府信任与离题峰值份额的时间演化，并标出稳态窗口。 | `fig5_trajectory_source_data.csv`、`representative_seed_selection.csv` | 仅使用代表性种子 **73048**。细线为逐步原始值，粗线为 7 步居中移动平均；没有跨种子置信区间，因此该图用于机制与过程展示，不用于总体推断。 |
| `main/Fig6_public_data_validation` | 公开数据提供三类外部证据：跨国数字政府水平与政府信任的关系较弱且对年份敏感；控制主题、平台、月份和标题长度后，新闻情绪强度与平台反馈呈小幅正关联；公共事务新闻反馈在最初数小时高度集中。 | `macro_country_panel.csv`、`macro_spearman.csv`、`news_sentiment_regression_cluster.csv`、`facebook_public_affairs_decay_curve.csv`；来源说明见 `dataset_sources.csv` | 面板 a、b：30 个国家；面板 b 的相关系数区间为 5,000 次国家重抽样的 95% 分位数区间。面板 c：256,626 个有效“新闻 × 平台”观测，按 87,492 个新闻 ID 聚类的稳健标准误与双侧 95% *t* 区间；回归因变量为 `log(1 + 平台反馈量)`，图中系数转换为 `100 × (exp(β) − 1)`。面板 d：27,244 篇公共事务新闻，每篇按 24 小时反馈总量归一化；每个 20 分钟区间显示跨文章均值及 `均值 ± 1.96 × SE`。 |

## 补充图

| 图件 | 核心结论与证据角色 | 源数据 | `n` 与区间定义 |
|---|---|---|---|
| `supplementary/FigS_storm_dynamics` | 将总体风暴占比分解为风暴频率、平均峰值和平均持续时间，展示三项动态量如何随 `α` 改变。 | `figs_storm_source_data.csv` | 每个 `α` 为 50 个种子的均值；阴影为双侧 95% Student-*t* 均值置信区间（df = 49）。 |
| `supplementary/FigS_trust_polarization` | 展示三个代表性 `α` 下公众政府信任的均值与群体内部离散程度如何随时间变化。 | `fig5_trajectory_source_data.csv` | 仅使用代表性种子 **73048**；曲线为每步 300 名公众智能体的平均信任，色带为同一步公众智能体的 `均值 ± 1 个总体标准差`（截断至 0–1），不是置信区间，也不是跨种子推断。 |
| `supplementary/FigS1_attention_decay` | 对比27,244篇公共事务文章的24小时经验反馈曲线与按同一72段窗口归一化的λ=0.95几何参照。 | `03_data/external/source_data/FigS1_attention_decay_*.csv` | 逐段色带为跨文章均值的点位95%区间；6小时和12小时点为跨文章95% *t* 区间；几何参照是确定性曲线。 |
| `supplementary/FigS2_formal_sensitivity` | 汇总14组参数扰动、三种执行顺序和三种内置回应策略的临界点，并展示回应策略的完整议程偏离曲线。 | `03_data/sensitivity/source_data/FigS2_*.csv` | 临界点区间来自5,000次种子整曲线Bootstrap；曲线每个α为50个共同种子的均值和95% *t* 区间。 |

## 公开数据来源

- 世界银行 GovTech Maturity Index：2020、2022、2025 年 GTMI 及四个分项，用于与 2023 年政府信任进行跨国比较。
- OECD *Government at a Glance 2025*：2023 年对国家政府具有较高或中等偏高信任的比例，作为跨国结果变量。
- 世界银行 World Development Indicators：互联网使用率和人均实际 PPP GDP，作为跨国回归控制变量。
- UCI News Popularity in Multiple Social Media Platforms：用于情绪—反馈回归与公共事务新闻的 24 小时注意力衰减分析。平台回归先形成 279,717 个候选“新闻 × 平台”观测，排除反馈量编码为 `−1` 的 23,091 行后保留 256,626 行。

完整 URL、许可证和实际使用字段记录在 `../03_data/figures/source_data/dataset_sources.csv`。

## 绘图代码

- `../02_experiment_code/figure_generation_frozen/build_external_validation_figure.py`：生成 Fig. 6 的原始 Python/matplotlib 脚本。
- `../02_experiment_code/build_figure_s1_decay.py`：生成 Fig. S1。
- `../02_experiment_code/build_figure_s2_sensitivity.py`：生成 Fig. S2。

Fig. 6脚本按原文件逐字节复制，作为审计与复现依据。Fig. 2–5及既有补充图保留矢量成品和逐图源数据；本包没有收录与这些定量图无关的附加绘图模块。
