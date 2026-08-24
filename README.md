# 政府—平台—公众智能体模型：正式复现与补充材料包

本仓库整理了当前论文版本所需的冻结模型、正式五条件消融、公开数据一致性检验、S1 外部验证、S2 正式敏感性分析、投稿图件及完整审计记录。目录按“模型—代码—数据—图—文档—复现”排列，避免把历史探索结果与正式结果混在一起。

## 一、核心结论边界

1. 正式模型以 `01_model_core/model.py` 为唯一核心快照，SHA-256 为 `AB78E6C64AFB6FD487E40A48FBBCD1B09A84EE3FBC9085530F8833DE3543D7EC`。S2 参数扰动只覆盖配置值；执行顺序检验写在独立运行器子类中，核心文件没有改动。
2. 正式消融包括完整模型、无情绪优势、无偏好漂移、无有效政府回应、无信任—互动反馈五个条件；每个条件使用21个 α 水平和50个共同随机种子，共5,250次运行。`No trust` 是原四条件协议之后追加的正式消融，复现说明没有把它伪装成原协议内容。
3. S2 新增14个参数扰动、2个替代回应策略和3种执行顺序，共19,950次运行；与完整模型和无有效回应参照合并后的分析输入为22,050行。三种代码内置回应策略是 `hard`、`selective` 和 `wait`；冻结代码没有“自适应强度”实现，因此本仓库没有编造该结果。
4. S1 使用世界银行、OECD和UCI公开数据检查机制方向或数量级是否相容。它不是因果识别，也不是把模拟参数校准成现实常数。尤其是2025 GTMI晚于2023政府信任，只能作为跨版本描述性比较。

## 二、目录

| 目录 | 内容 |
|---|---|
| `01_model_core/` | 唯一冻结核心模型及边界说明 |
| `02_experiment_code/` | S2运行、分析、报告和绘图代码；字节级冻结的正式消融与外部验证代码 |
| `03_data/` | 正式消融、S2敏感性、公开数据和逐图源数据；raw与processed分开 |
| `04_figures/` | 主图、补充图的可编辑SVG/PDF及600 dpi PNG/TIFF |
| `05_documents/` | 研究设计、附录A/B、S1、S2和完整图注 |
| `06_reproducibility/` | 环境、数据字典、协议溯源、SHA-256清单和发布QA |

推荐阅读顺序是：`05_documents/研究设计.docx` → `附录A_B_模型公式与指标.md` → `补充材料S1_外部验证细节.md` → `补充材料S2_敏感性分析.md`。

## 三、快速复现 S2

以下命令在仓库根目录运行；Windows PowerShell的完整环境步骤见 `06_reproducibility/ENVIRONMENT.md`。

```powershell
python -m pip install -r requirements.txt
python 02_experiment_code/run_formal_sensitivity.py --workers 8
python 02_experiment_code/analyze_formal_sensitivity.py
python 02_experiment_code/write_s2_report.py
python 02_experiment_code/build_figure_s1_decay.py
python 02_experiment_code/build_figure_s2_sensitivity.py
python 06_reproducibility/build_release_manifest.py
python 06_reproducibility/validate_release.py
```

运行器支持按 `scenario_id + alpha + seed` 断点续跑。已有正式CSV属于发布证据；若只是阅读或复核统计，不需要覆盖重跑。

## 四、如何读取结果

- 五条件消融的逐次结果在 `03_data/formal_ablation/raw/formal_replicates_5conditions.csv`，统计检验和效应量在相邻 `processed/`。
- S2新增逐次结果在 `03_data/sensitivity/raw/sensitivity_replicates.csv`；临界点、完整曲线、α=0.60配对效应和AUC配对效应在 `processed/`。
- S1完整回归、15项相关、HC3、逐国剔除和衰减曲线在 `03_data/external/processed/`。
- 图件不是数据源；每张定量图都能追溯到 `03_data/**/source_data/` 或明确列出的处理表。

`system_stability` 的代码含义是末100步议程偏离度的总体方差；数值越大代表波动越强，不能把较大值解释成“更稳定”。`response_strength` 的含义是回应后热度保留率，例如0.70表示保留70%、降低30%。

## 五、审计与限制

- `06_reproducibility/release_manifest.csv`记录发布文件的大小和SHA-256；清单按惯例不自引用。
- `06_reproducibility/release_qa.json`是最终结构、行数、主键、图件格式和占位符检查结果。
- 历史前四条件与后续`No trust`运行使用了不同的Python/NumPy/Pandas环境；共同种子设计仍然保留，但严格的逐比特重现限制已在`FORMAL_ABLATION_PROVENANCE.md`披露。
- 代表性轨迹图使用预先选择的seed 73048，只用于展示时间形态，不是跨种子统计推断。
- 仓库没有自动授予代码再许可；公开数据的来源、许可或使用条款见`03_data/README.md`和`dataset_sources.csv`。
