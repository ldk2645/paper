# ABM：反向黑箱与政府回应的结构性限度

当前版本 0.4.0（2026-09-26）。根据用户要求恢复原文章核心创新：政府在算法中介下的双重信息弱势、放大与阻尼的竞争、行政回应节律及工具边界、信任反馈、可能的临界变化。0.3.x的偏好测量模块保留为诊断层；主问题恢复为政府在怎样的注意力架构下能够纠偏、何时受到结构性限制。保留理论问题不意味着保留未经新版检验的旧阈值和结论。

2026-09-27已根据用户技术清单更新研究计划，新增[正式实验协议](formal_experiment_protocol.md)和[19项落实表](technical_checklist_response_20260927.md)。这次是计划修订，模型代码仍为0.4.0；P0/P1开发与正式实验尚未完成。

## 从这里开始

- [修订研究计划](research_plan.md)：原创新主线、三层机制识别和待做实验。
- [创新保留对照](innovation_preservation.md)：原文依据、已恢复机制与仍需检验的命题。
- [论文论证修订](manuscript_core_revision.md)：题目、引言主线与可检验命题。
- [七章行文框架](paper_outline_jasss.md)：整合用户初步框架，区分三层模型结果与两类经验材料。
- [经验动机协议](empirical_motivation_protocol.md)：第3章数据候选、可比性和结论范围。
- [0.3.0开发记录](diagnostic_report.md)：仅对应旧测量诊断版本，不能用于反驳原完整模型的相变命题。
- [ODD 模型说明](ODD.md)：英文公式、时序和实现映射。
- [参数表](parameters.md)：代码默认值、试跑覆盖值及假设性质。
- [修改与验证记录](revision_validation_20260926.md)：43项通过测试、480次开发仿真及行文框架对应的后处理。
- `abm_jasss/model.py`：模型；`governance.py`：回应控制、信任与持续事件；`cli.py`：批量运行与结果记录。

## 运行

已验证环境：Windows、Python 3.12.14、NumPy 2.3.5。PowerShell 在此目录运行：

```powershell
.\run.ps1 -Mode test
.\run.ps1 -Mode core -Workers 2
.\run.ps1 -Mode core-suite -Workers 2
```

启动器优先使用本机已安装的 bundled Python，也可通过 `-PythonPath '完整的python.exe路径'` 指定环境。其他电脑先在独立 Python 环境安装 `python -m pip install -r requirements.txt`，然后运行：

```text
python -m unittest discover -s tests -v
python -m abm_jasss.cli --config configs/restored_core.json --output outputs/my_core --workers 2
python scripts/run_core_suite.py --output outputs/my_core_suite --workers 2
python scripts/analyze_response_targets.py --source outputs/my_core_suite --output outputs/my_response_diagnostics
```

输出目录必须为空或尚不存在。旧 `pilot/suite/feedback` 模式仍可运行嵌套的测量模型。`configs/main_candidate.json` 是0.3.x的未执行测量候选，已不代表新主实验。恢复主模型的正式设计须在机制与动态检验完成后另行冻结。有反馈时每个信息策略分别生成世界；配置中可用 `arms` 指定要运行的策略。

## 结果如何追溯

每个实验目录包含 `manifest.json`、`source_snapshot`、`resolved_design.json`、逐世界 JSON、`trajectories`、`events`、`runs.csv`、测量统计、`governance_metrics.csv` 和简报。事件记录区分排期、执行、回应发文与即时热度变化；期末未执行动作和未结束事件保留。失败写入 `failures.json`，不生成部分成功样本的聚合推断。`governance_metrics.csv` 区分政府议程、公众偏好失配与信任结果，不把三者合成一个“治理成功”指标。

重跑历史版本时，把该次 `source_snapshot/abm_jasss` 复制到一个独立目录，在该目录使用 manifest 中的 specification 保存为 JSON 后运行模块；依赖版本也应与 manifest 一致。浮点结果跨平台不承诺逐字节相同。已测试本机串行与双进程输出一致。

0.3.0历史开发结果位于 `outputs/diagnostics_v030_20260924` 和 `outputs/feedback_v030_20260924`。恢复版试跑入口是 `outputs/core_restoration_v040_20260926/core_pilot_report.md`；只在全部情景完成后生成该汇总。各版本的真值、政府工具和结果指标不同，不能拼接成同一统计样本。历史 `scripts/document_results.py` 仅重建0.3.0报告；当前参数表用 `python scripts/document_parameters.py` 生成。

## 历史源代码审阅

原文对应仓库为 [ldk2645/paper](https://github.com/ldk2645/paper)。审阅时其 `release_qa.json` 的12项完整性检查均通过；仓库包含冻结 V1 模型、正式五条件消融数据、敏感性运行、外部数据表及完整图表溯源。它们值得作为历史证据保留。

V1 的议程外类别与公众潜在偏好含义不同。新版同时保留政府议程指标与公众偏好指标，明确二者可能不一致。0.4.0已经实现阈值排队、延迟热度调节、日常发布、回应曝光、信任反馈和持续事件，不再只将它们登记为未来参考。信任方程做了可解释的重新参数化，并提供替代规则；外部回归系数未直接迁入，因此不是V1数值复现。

## 当前范围与下一步

用户初步行文框架已整合为七章结构，详见paper_outline_jasss.md。三层诊断的新增结果位于`outputs/response_alignment_v040_20260926/report.md`：既有480世界的93,879组执行回应已按触发和执行时点计算目标错配，空动作保持NA并记录数量。第一、二层在当前平台基线中按定义重合，仍需信息和感知规则对照。经验动机章节尚未形成配对数据或经验结论。

主模型启用情绪—互动—热度—曝光回路、偏好漂移、有限排期能力的延迟回应与信任反馈。消融区分无定向回应（保留日常发布）、仅取消热度调节（保留回应发文）、取消信任对互动的反馈（保留信任状态更新）。信任有暴露惩罚与偏好匹配两种规则；调查、融合和公众偏好oracle用于分解信息限制。

下一阶段重点：独立解除排序规则与偏好遮蔽的对照、算法/行政时标比、同一状态下下游回应与上游排序干预的比较、初值/正反扫描/恢复检验，以及信任诊断的留出验证。当前公众偏好oracle不等于算法透明；不同α各自从头运行不等于同状态架构干预；短时窗未恢复不等于不可逆。旧文的创新命题均保留为可被推翻的研究问题。0.4.0只是恢复研究主线后的开发版本，仍需正式实验与英文稿。
