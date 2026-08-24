# 数据目录与公开数据使用说明

## 1. 这份目录解决什么问题

本目录把“模型自己产生的实验数据”和“公开数据形成的外部一致性检验”分开保存。基本原则是：

- `raw/` 只放原始输入或逐次模拟输出，不在其中手工改数；
- `processed/` 放由脚本从 `raw/` 计算得到的汇总、统计检验和效应量；
- `source_data/` 放能够直接重绘论文图的最小数据表；
- 图像文件放在 `../04_figures/`，不把图像当作分析数据；
- `external/dataset_sources.csv` 是公开数据来源索引，`external/final_conclusion_data.csv` 是跨实验的结论数据长表；这两个文件均为上游结果的原样副本。

外部公开数据只用于检验模型机制与现实数据是否呈现相容的统计模式，未用于反向调参，也不能单独构成因果验证。

## 2. 目录结构

| 路径 | 内容 | 分析单位与用途 |
|---|---|---|
| `formal_ablation/raw/` | 正式消融逐次运行结果、运行清单；`formal_replicates_5conditions.csv` 合并完整模型及四个单机制消融 | 一行是一个“条件 × α × 共同随机种子”运行；用于所有正式消融统计 |
| `formal_ablation/processed/` | 条件汇总、配对效应、α 曲线面积效应、临界点 bootstrap 及作图数据 | 从正式消融原始表派生；不能替代原始逐次结果 |
| `sensitivity/raw/` | 参数、回应策略和执行顺序敏感性逐次运行结果及设计清单 | 一行是一个“情景 × α × 共同随机种子”运行；CSV 由可续跑运行器追加 |
| `sensitivity/processed/` | 敏感性分析完成后生成的汇总与临界点结果 | 仅在完整性检查通过后解释；运行尚未完成时不得据局部行数报告结论 |
| `external/raw/` | 公开数据的下载原件或经许可随包分发的原始子集 | 输入数据；不要手工清洗或覆盖 |
| `external/processed/` | 国家层面匹配表、相关/回归/逐国剔除结果、新闻回归和注意力衰减表 | 由冻结脚本从外部原始数据生成 |
| `external/source_data/` | 补充图的可重绘数据 | 与 `04_figures/supplementary/` 中图件一一对应 |
| `external/dataset_sources.csv` | 来源、URL、许可、下载文件、实际使用范围和研究角色 | 公开数据来源索引 |
| `external/final_conclusion_data.csv` | 正式消融与外部验证的核心估计、95% CI、p 值定义和样本量 | 便于核对文稿数字，不是新的统计分析 |
| `../04_figures/` | PDF、SVG、PNG、TIFF 等成图 | 展示产物；图的数值依据应回到 `source_data/` |

正式消融使用 21 个 α 值（0.00 至 1.00，步长 0.05）和 50 个共同随机种子（73000 至 73049）。`formal_replicates_5conditions.csv` 的主键是 `(condition_id, alpha, seed)`，共 5,250 行。详细字段见 `../06_reproducibility/DATA_DICTIONARY.md`。

## 3. 公开数据：为什么使用、实际用了什么、怎样转换

### 3.1 World Bank GovTech Maturity Index（GTMI）

**为什么使用。** GTMI 及其四个分项提供国家层面的数字政府能力指标，可用于检查“数字政府成熟度—公众政府信任”关系是否与模型中的政府和公众机制在方向上相容。

**实际使用。** 从 2025 工作簿的 `GTMI_Data` 工作表读取 `Year`、`Code`、`Economy`、`GTMI`、`CGSI`、`PSDI`、`DCEI`、`GTEI`，保留 2020、2022、2025 三个版本；与有 OECD 2023 信任数据的国家取交集后，每个版本 30 个国家，共 90 个“国家 × GTMI 版本”观测。五项指标分别是综合指数、核心政府系统、公共服务交付、数字公民参与和 GovTech 赋能因子。

**转换。** 年份和五项指数转为数值，国家代码去除首尾空白，再按三位国家代码与 OECD、WDI 合并。相关分析直接使用指标秩；回归中把目标指标、互联网使用率和对数人均 GDP 分别标准化。

**来源与许可。** [World Bank GovTech Dataset](https://datacatalog.worldbank.org/search/dataset/0037889/govtech-dataset)，CC BY 4.0。实际下载文件名和使用范围记录在 `external/dataset_sources.csv`。

**局限。** 国家样本只有 30，统计功效有限；国家层面相关不能代表个体层面的因果效应。尤其要注意：**2025 版 GTMI 晚于 2023 年 OECD 信任结果**，不存在合理的前因—后果时间顺序，因此 2025 配对只能作为“当前版本指标与较早信任结果的一致性/敏感性比较”，绝不能表述为数字政府导致 2023 年信任变化。较接近时间顺序的是 2022 GTMI 对 2023 信任，但它仍是观察性横截面检验，不是因果识别。

### 3.2 OECD 2023 年国家政府信任

**为什么使用。** 该数据直接提供公众对国家政府的信任比例，是国家层面外部检验的结果变量。

**实际使用。** 在 OECD Government at a Glance 2025 的 “Trust, security and dignity” 数据中，筛选 `MEASURE = TRUST_NG`、`SCALE = HMH`、`TIME_PERIOD = 2023` 及三位 `REF_AREA`，使用 `OBS_VALUE` 作为“对国家政府有高度或中高度信任的百分比”；最终 30 个国家。

**转换。** 将 `REF_AREA` 重命名为 `Code`、`OBS_VALUE` 重命名为 `trust_national_pct`，再与 GTMI 和 WDI 按国家代码内连接/左连接。

**来源与许可。** [OECD Data Explorer：Trust, security and dignity](https://data-explorer.oecd.org/vis?df%5Bag%5D=OECD.GOV.GIP&df%5Bds%5D=DisseminateFinalDMZ&df%5Bid%5D=DSD_GOV_INT%40DF_GOV_TDG_2025&df%5Bvs%5D=1.1&lc=en)，适用 OECD 条款与条件。

**局限。** 指标是国家聚合的调查比例，受调查设计、文化回答差异和未观测国家因素影响；不能与模型中的个体信任状态逐值等同。

### 3.3 World Bank World Development Indicators（WDI）

**为什么使用。** 互联网普及和经济发展可能同时关联数字政府成熟度与政府信任，因此作为国家层面回归的两个预先说明的控制变量。

**实际使用。** 指标为互联网使用人口比例 `IT.NET.USER.ZS` 和按购买力平价、2017 年不变国际元计的人均 GDP `NY.GDP.PCAP.PP.KD`。

**转换。** 从 API 返回的 2022—2025 记录中，只保留三位国家代码和非缺失值；为避免使用 2023 信任之后的信息，对每国取**截至 2023 年**最新的非缺失值；人均 GDP 再取自然对数。回归中将互联网比例和对数人均 GDP 标准化。

**来源与许可。** [World Bank Indicator API](https://datahelpdesk.worldbank.org/knowledgebase/articles/898599-indicator-api-queries)，适用 World Bank Data Terms。精确 API URL 已固化在 `../02_experiment_code/external_validation_frozen/download_external_data.ps1`。

**局限。** 两个控制变量不能覆盖制度、政治、调查方法等全部混杂因素；“最新非缺失值”也可能导致国家间控制变量年份略有差异。

### 3.4 UCI News Popularity in Multiple Social Media Platforms（Dataset 432）

**为什么使用。** 这套公开数据同时包含标题情感、跨平台反馈和 20 分钟间隔的反馈时间序列，可分别检查模型中的“情绪与互动”机制和“注意力随时间衰减”假设。

**情绪—反馈检验实际使用。** `News_Final.csv` 有 93,239 条新闻，读取 `IDLink`、`Topic`、`PublishDate`、`SentimentHeadline`、`Headline` 以及 Facebook、GooglePlus、LinkedIn 三个平台反馈。宽表转成长表后共有 279,717 个候选“新闻 × 平台”行；排除平台反馈为 `-1` 的 23,091 行，保留 256,626 行，对应 87,492 个新闻聚类。

**情绪—反馈转换。** 因变量为 `log1p(popularity)`；情绪强度为 `abs(SentimentHeadline)` 并标准化；负面标题为 `SentimentHeadline < 0` 的二元变量；标题长度先计算字符数、再 `log1p` 并标准化；加入主题、平台和发布月份虚拟变量。OLS 的标准误按 `IDLink` 聚类。情绪五分位仅用于描述表。原始 Spearman 相关在大样本下使用 Fisher-z 近似区间，不是行级 bootstrap。

**衰减检验实际使用。** 使用 `Facebook_Obama.csv` 和 `Facebook_Palestine.csv`。保留至少有 72 个有效 20 分钟观测（覆盖 24 小时）且 24 小时累计反馈大于 0 的文章，共 27,244 篇（Obama 22,463；Palestine 4,781）。

**衰减转换。** 对累计时间序列先做一阶差分得到每 20 分钟新增反馈，负差分截为 0，再除以该文章 24 小时新增反馈总量。逐时间格曲线为跨文章平均份额，95% 区间用跨文章标准误的正态近似；前 6 小时和前 12 小时份额在文章层面计算，并用 t 区间汇总。

**来源与许可。** [UCI Dataset 432](https://doi.org/10.24432/C5H029)，CC BY 4.0。

**局限。** 数据来自特定时期、主题与平台，平台反馈不是完整的阅读/认知注意力；标题情感与反馈的关系仍可能受未观测内容质量和事件重要性影响。该数据只检验经验形态是否相容，不把回归系数直接写回模型参数。

## 4. 外部验证的统计链条

1. `download_external_data.ps1` 从上述固定 URL 下载公开原件并解压 UCI 数据。
2. `analyze_external_data.py` 构造国家匹配表、15 个 Spearman 相关及 Holm 校正、HC3 回归、逐国剔除范围、新闻聚类稳健回归和 24 小时衰减曲线。
3. `build_evidence_tables.py` 将正式消融和外部验证中的核心结果整理为 `final_conclusion_data.csv`，同时生成 `dataset_sources.csv`。

三份脚本在 `../02_experiment_code/external_validation_frozen/` 中按上游文件原样保存，便于审计。它们的相对路径仍遵循原项目布局：若在本发布目录中重跑，应在临时复现工作区按 `src/`、`external/raw/`、`external/processed/`、`processed/` 的原相对结构放置脚本和数据，不要改动冻结脚本本身。

最小复现入口如下（Python 依赖为 `numpy`、`pandas`、`scipy`、`openpyxl`）：

```powershell
# 在临时复现工作区中，把三份冻结脚本放入 src/ 后执行
powershell -ExecutionPolicy Bypass -File src/download_external_data.ps1
python src/analyze_external_data.py
```

若还要重建跨实验结论表，应先把正式消融的 `paired_effects_5conditions.csv` 和 `auc_effects_5conditions.csv` 放入该临时工作区的 `processed/`，再执行：

```powershell
python src/build_evidence_tables.py
```

`download_external_data.ps1` 会访问网络并下载最新可用的固定目标文件；严格复核本次归档时还应核对文件哈希和数据版本日期。`source_data/` 是图的数值入口，而 `../04_figures/` 是渲染结果，二者不要互相替代。

## 5. 可解释范围

- 正式消融回答“在同一模型与共同随机种子下，移除某机制会怎样改变模拟输出”。
- 外部宏观数据回答“国家层面的数字政府指标与 2023 信任是否呈现稳定的观察性关联”。
- UCI 新闻数据回答“情绪—反馈和时间衰减这两种经验模式是否存在”。
- 三者可以互相约束解释，但不能合并成现实世界的因果证明，也不能声称外部数据已经识别模型的全部参数。
