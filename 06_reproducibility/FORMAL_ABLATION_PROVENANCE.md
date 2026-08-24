# 五条件正式消融冻结复现包：来源与复现说明

## 1. 冻结范围

本目录记录政府—平台—公众智能体模型正式消融实验的代码、数据与统计结果来源。冻结包保持原始代码内容不变，并保留原程序所依赖的相对目录结构。

正式实验由两个相互衔接的阶段组成：

1. 原协议的四个条件：`full`、`no_emotion`、`no_drift`、`no_response`；
2. 后续正式增补条件：`no_trust`。

每个条件扫描 21 个 alpha 水平（0.00 至 1.00，步长 0.05），每个“条件 × alpha”单元使用共同随机种子 73000–73049，共 50 次重复。前四条件产生 4,200 次运行，增补条件产生 1,050 次运行，五条件合计 5,250 次运行。

## 2. 代码来源与目录

冻结代码位于 `02_experiment_code/formal_ablation_frozen/`：

```text
formal_ablation_frozen/
├─ 研究设计.docx
├─ 原始版本/
│  ├─ src/src/reverse_black_box_abm/
│  │  ├─ __init__.py
│  │  ├─ model.py
│  │  └─ experiments.py
│  └─ formal_ablation_n50_nonspatial/
│     ├─ PROTOCOL.md
│     ├─ run_formal_ablation.py
│     ├─ analyze_formal_ablation.py
│     ├─ verify_unified_model.py
│     └─ qa_formal_ablation.py
└─ model_validation_round3/src/
   ├─ run_no_trust.py
   └─ analyze_five_conditions.py
```

`研究设计.docx`被一并冻结，是因为四条件运行器会在写入运行清单时计算该文件的 SHA-256。所有 Python、Markdown 和 DOCX 文件均按来源文件逐字节复制，没有修改代码或协议文字。

## 3. 原协议与后续增补的边界

`PROTOCOL.md`定义的是最初四条件实验，并明确没有把 `no_trust`列入该协议。因此，`no_trust`应表述为原四条件实验完成后的正式增补，而不是原协议预先列出的条件。

增补实验只把`trust_feedback_strength`设为 0。信任状态仍继续更新和记录；被移除的是信任状态对后续互动概率的反馈。其余参数扫描、种子、公众数量、时间步和稳态窗口沿用四条件设计。

## 4. 正式数据文件

正式数据位于`03_data/formal_ablation/`。

### 原始数据与运行清单

| 文件 | 含义 | 数据行数 |
|---|---|---:|
| `raw/formal_replicates_4conditions.csv` | 原四条件逐次运行结果；来源文件名为`formal_replicates.csv`，复制时仅为避免歧义而改名，文件内容未变 | 4,200 |
| `raw/formal_manifest.json` | 原四条件设计、配置、种子、运行环境和源文件哈希 | — |
| `raw/no_trust_replicates.csv` | `no_trust`逐次运行结果 | 1,050 |
| `raw/no_trust_manifest.json` | 增补条件定义、配置、种子、运行环境和源文件哈希 | — |
| `raw/formal_replicates_5conditions.csv` | 五条件最终合并统计输入 | 5,250 |

五条件合并表包含 105 个“条件 × alpha”单元，每个单元 50 行；`condition_id + alpha + seed`组成的键无重复。

### 最终处理结果

| 文件 | 主要内容 | 数据行数 |
|---|---|---:|
| `processed/condition_summary_5conditions.csv` | 各条件、alpha和指标的均值、标准差及区间 | 420 |
| `processed/paired_effects_5conditions.csv` | 四种消融相对完整模型的逐 alpha 配对效应 | 336 |
| `processed/auc_effects_5conditions.csv` | 四种消融在整条 alpha 曲线上的 AUC 配对效应 | 16 |
| `processed/critical_bootstrap_5conditions.csv` | 五条件临界点区组 Bootstrap 抽样 | 25,000 |
| `processed/critical_points_5conditions.json` | 临界点、区间及识别信息 | — |
| `processed/ablation_primary_alpha.csv` | 完整模型主临界点处的 16 项主要比较 | 16 |
| `processed/fig4_agenda_effect_chart_data.csv` | Fig. 4议程偏离面板的精简绘图数据 | 21 |
| `processed/five_condition_results.json` | 五条件分析摘要 | — |

## 5. 软件环境差异及限制

两个运行阶段使用了不同的软件环境：

| 阶段 | Python | NumPy | Pandas | 清单记录的平台 |
|---|---:|---:|---:|---|
| 原四条件 | 3.12.13 | 2.3.5 | 3.0.1 | Windows 11 / 10.0.26200 |
| `no_trust`增补 | 3.11.3 | 2.2.6 | 2.3.1 | Windows 10 / 10.0.26200 |

两阶段使用了相同的随机种子编号和相同的参数设置，但软件版本并不完全相同。因此，现有结果可按保存的代码、清单和数据审计；若需要最严格的逐字节再现或重新证明跨条件的随机数路径完全一致，应先建立单一锁定环境，再统一重跑全部五个条件，并重新生成全部处理结果和哈希。

当前冻结包忠实保存已完成实验，不对上述环境差异进行事后掩盖。

## 6. 从头运行的顺序

以下命令从仓库根目录执行。`--workers`可以按机器资源调整。

```powershell
python 02_experiment_code/formal_ablation_frozen/原始版本/formal_ablation_n50_nonspatial/verify_unified_model.py
python 02_experiment_code/formal_ablation_frozen/原始版本/formal_ablation_n50_nonspatial/run_formal_ablation.py --workers 8
python 02_experiment_code/formal_ablation_frozen/原始版本/formal_ablation_n50_nonspatial/analyze_formal_ablation.py
python 02_experiment_code/formal_ablation_frozen/model_validation_round3/src/run_no_trust.py --workers 8
python 02_experiment_code/formal_ablation_frozen/model_validation_round3/src/analyze_five_conditions.py
```

运行器按照原始相对路径把新结果写入冻结代码树中的`raw/`和`processed/`目录。为避免覆盖本仓库冻结的正式证据，建议在干净副本或单独分支中执行，再与`03_data/formal_ablation/`中的文件比较。

原始`qa_formal_ablation.py`也已按要求冻结。它包含对原四条件历史报告和历史图件的完整检查；这些历史展示文件不属于本次最小五条件数据包，因此发布级复核应以本目录的 SHA-256 清单、行数、单元数、共同种子集合和主键唯一性检查为准。

## 7. 核心哈希锚点

| 对象 | SHA-256 |
|---|---|
| 模型`model.py` | `AB78E6C64AFB6FD487E40A48FBBCD1B09A84EE3FBC9085530F8833DE3543D7EC` |
| 原四条件运行器 | `623E4F37C93A2CAED89EE9A4E358012BB449B6FB1423A709BCBF2442B2037BBC` |
| `no_trust`运行器 | `50D2AEC51A3A1F6781357C2BE63700A8B92A8649343B89499BE7F2455368B032` |
| 研究设计文档 | `62A2216DA8FA356926AEF16C57BE8F599C1DC53C6895E191830393F6BD139751` |
| 原四条件逐次结果 | `644104CE8C82D90C4F024D872DA265B2B4580B263527BFEE2CAE3E124B0708C2` |
| `no_trust`逐次结果 | `1A466A8FEA648AE0AB0BABFDF521A577C0BFC7560C0492849C2AF3CE28EA0BF5` |
| 五条件合并结果 | `FC95B5A40BFEFD62A19284F6070A7B80F83F81A0403F4CB4FE5760F694C1DB91` |

所有冻结文件的逐文件哈希见`06_reproducibility/formal_ablation_sha256.csv`。该清单不记录自身哈希，以避免自引用。
