# 论文形成过程：必要报告归档（2026-10-04）

本文件夹汇集论文形成过程中的核心报告、关键验收证据和已完成的正式结果。**E2–E4 正式批次已完成；这不是论文全部完成或已达到投稿条件的声明。**

截至本归档所依据的正式验收，1,184 个 α×seed 区组、21,312 个物理终点和 1,000 个独立 seed 已全部通过，失败区组为 0；102 项主分析、532 项辅助结果及 6 幅森林图已经生成。102 项主分析的实际点态 95% 区间半宽均不超过 0.02，45 项通过一次全 102 项 Holm 校正。正式完成时间为 2026-10-04 05:52:11（北京时间）。

**仍需另行完成：** E5 动态转变／机制恢复与结构稳健性、E6 信任预警、经验动机配对材料，以及完整英文论文。这里的英文 Methods、Results 是工作稿，不能据此称整篇英文论文完成。试点的 3 项预算风险和 61 项方差不稳定标记仍保留；它们与正式结果的实际精度达标是两个不同阶段的事实。

原文件全部保留原处：`D:/UserData/Desktop/ZLS/ABM_JASSS/`。本归档的 `sources/ABM_JASSS/` 按原相对路径复制文件，复制内容逐字节核对 SHA256；未重写报告，也未移动或删改原始资料。历史报告按各自日期和模型版本解释，旧报告中的“尚未运行”等表述不代表当前状态。

## 从这里阅读

- [正式执行验收](sources/ABM_JASSS/formal_execution_acceptance_20261004.md)：本批次的完成范围、统计口径和复核依据。
- [最新接续记录](sources/ABM_JASSS/project_handoff_20261004.md)：当前状态与历史恢复路径。
- [完整中文结果报告](sources/ABM_JASSS/outputs/formal_e2_e4_repaired_v2_20261004_report/report_zh.md)：完整主结果和全部表图入口。
- [英文方法](sources/ABM_JASSS/manuscript_work_20261004/methods_en.md)与[英文结果](sources/ABM_JASSS/manuscript_work_20261004/results_en.md)：当前论文工作稿。

## 归档范围与复现边界

此处是报告阅读与核对包，**不是全量复现包**。未复制海量 raw、母状态和动态快照、逐区组输出，也未复制约 34 MB 的正式原始文件哈希清单。完整数据和源码仍在原项目中。源码、模型配置或协议的文中链接可能因此指向未收录的文件；请看独立的 [链接审计](link_audit.json)，不要以报告中的链接存在推断所有文件均已归档。

原冻结包和修复 v2 冻结包仅收录 manifest、配置、推断规范、种子及哈希索引等关键文件，**都是不完整副本**；其 `artifact_hashes.json` 是原包的溯源索引，不是本归档已包含所有条目的声明。S0/S1、pilot、原冻结、修复冻结、最终执行、分析、图表及发布复核的小型证据目录按目录整体复制；原始成功／失败批次仅选取标识、失败名册与恢复来源。

共收录 **157 个源文件，9,068,614 字节（8.65 MiB）**。逐文件来源、用途、大小与 SHA256 见 [manifest.csv](manifest.csv) 和 [manifest.json](manifest.json)。复制及原文件复核见 [archive_verification.json](archive_verification.json)。

Markdown 链接审计共记录 348 处链接；281 处本地链接可在归档内找到，52 处本地引用未被归档完整覆盖。逐条列出归档目标、原始目标及原目标是否存在；外部网址和文内锚点不作可达性验证。保留原报告字节优先，不通过改写报告或复制 raw 补齐链接。

## 按阶段索引

### 00 当前状态与阅读入口

- [README.md](sources/ABM_JASSS/README.md)：当前正式阶段状态和接续入口；其中历史段落按其日期解释。

- [project_handoff_20261004.md](sources/ABM_JASSS/project_handoff_20261004.md)：当前正式阶段状态和接续入口；其中历史段落按其日期解释。



### 01 研究计划与创新

- [formal_experiment_protocol.md](sources/ABM_JASSS/formal_experiment_protocol.md)：保留原核心创新、研究设计演变、实验范围和技术落实依据。

- [innovation_preservation.md](sources/ABM_JASSS/innovation_preservation.md)：保留原核心创新、研究设计演变、实验范围和技术落实依据。

- [research_plan.md](sources/ABM_JASSS/research_plan.md)：保留原核心创新、研究设计演变、实验范围和技术落实依据。

- [technical_checklist_response_20260927.md](sources/ABM_JASSS/technical_checklist_response_20260927.md)：保留原核心创新、研究设计演变、实验范围和技术落实依据。



### 02 模型与开发验收

- [ODD_research.md](sources/ABM_JASSS/ODD_research.md)：现行模型、测量合同、核心恢复与 S0/S1 开发验收。

- [research_engine.md](sources/ABM_JASSS/research_engine.md)：现行模型、测量合同、核心恢复与 S0/S1 开发验收。

- [revision_validation_20260926.md](sources/ABM_JASSS/revision_validation_20260926.md)：现行模型、测量合同、核心恢复与 S0/S1 开发验收。

- [s0_validation_20260928.md](sources/ABM_JASSS/s0_validation_20260928.md)：现行模型、测量合同、核心恢复与 S0/S1 开发验收。

- [s1_validation_20260929.md](sources/ABM_JASSS/s1_validation_20260929.md)：现行模型、测量合同、核心恢复与 S0/S1 开发验收。

- [signal_and_outcome_contract.md](sources/ABM_JASSS/signal_and_outcome_contract.md)：现行模型、测量合同、核心恢复与 S0/S1 开发验收。

- [outputs/research_s0_acceptance_20260928/](sources/ABM_JASSS/outputs/research_s0_acceptance_20260928/acceptance.json)：完整小型包，5 个文件；开发阶段测试、串并行比较与验收的完整小型证据包。

- [outputs/research_s1_acceptance_20260929/](sources/ABM_JASSS/outputs/research_s1_acceptance_20260929/acceptance.json)：完整小型包，8 个文件；开发阶段测试、串并行比较与验收的完整小型证据包。



### 03 独立精度 pilot

- [precision_pilot_protocol_20260930.md](sources/ABM_JASSS/precision_pilot_protocol_20260930.md)：独立 pilot 运行前协议、固定预算和实测验收。

- [precision_pilot_validation_20261002.md](sources/ABM_JASSS/precision_pilot_validation_20261002.md)：独立 pilot 运行前协议、固定预算和实测验收。

- [outputs/precision_pilot_20261002_acceptance/](sources/ABM_JASSS/outputs/precision_pilot_20261002_acceptance/acceptance.json)：完整小型包，16 个文件；独立精度规划及验收；保留 3 项预算风险和 61 项方差不稳定标记。

- [outputs/precision_pilot_20261002_planning/](sources/ABM_JASSS/outputs/precision_pilot_20261002_planning/report.md)：完整小型包，6 个文件；独立精度规划及验收；保留 3 项预算风险和 61 项方差不稳定标记。



### 04 正式冻结

- [formal_execution_protocol_20261003.md](sources/ABM_JASSS/formal_execution_protocol_20261003.md)：正式固定样本、种子、估计对象、102 项检验和冻结时状态。

- [formal_freeze_validation_20261003.md](sources/ABM_JASSS/formal_freeze_validation_20261003.md)：正式固定样本、种子、估计对象、102 项检验和冻结时状态。

- [outputs/formal_freeze_acceptance_20261003/](sources/ABM_JASSS/outputs/formal_freeze_acceptance_20261003/acceptance.json)：完整小型包，6 个文件；原正式冻结验收与测试证据。

- [outputs/formal_registry_20261003/artifact_hashes.json](sources/ABM_JASSS/outputs/formal_registry_20261003/artifact_hashes.json)：冻结溯源关键文件；此归档仅保存选集，未包含完整冻结包。

- [outputs/formal_registry_20261003/configuration.json](sources/ABM_JASSS/outputs/formal_registry_20261003/configuration.json)：冻结溯源关键文件；此归档仅保存选集，未包含完整冻结包。

- [outputs/formal_registry_20261003/inference_spec.json](sources/ABM_JASSS/outputs/formal_registry_20261003/inference_spec.json)：冻结溯源关键文件；此归档仅保存选集，未包含完整冻结包。

- [outputs/formal_registry_20261003/manifest.json](sources/ABM_JASSS/outputs/formal_registry_20261003/manifest.json)：冻结溯源关键文件；此归档仅保存选集，未包含完整冻结包。

- [outputs/formal_registry_20261003/seed_audit.json](sources/ABM_JASSS/outputs/formal_registry_20261003/seed_audit.json)：冻结溯源关键文件；此归档仅保存选集，未包含完整冻结包。

- [outputs/formal_registry_20261003/seed_registry.json](sources/ABM_JASSS/outputs/formal_registry_20261003/seed_registry.json)：冻结溯源关键文件；此归档仅保存选集，未包含完整冻结包。

- [outputs/formal_registry_repair_v2_20261003/artifact_hashes.json](sources/ABM_JASSS/outputs/formal_registry_repair_v2_20261003/artifact_hashes.json)：冻结溯源关键文件；此归档仅保存选集，未包含完整冻结包。

- [outputs/formal_registry_repair_v2_20261003/configuration.json](sources/ABM_JASSS/outputs/formal_registry_repair_v2_20261003/configuration.json)：冻结溯源关键文件；此归档仅保存选集，未包含完整冻结包。

- [outputs/formal_registry_repair_v2_20261003/inference_spec.json](sources/ABM_JASSS/outputs/formal_registry_repair_v2_20261003/inference_spec.json)：冻结溯源关键文件；此归档仅保存选集，未包含完整冻结包。

- [outputs/formal_registry_repair_v2_20261003/manifest.json](sources/ABM_JASSS/outputs/formal_registry_repair_v2_20261003/manifest.json)：冻结溯源关键文件；此归档仅保存选集，未包含完整冻结包。

- [outputs/formal_registry_repair_v2_20261003/seed_audit.json](sources/ABM_JASSS/outputs/formal_registry_repair_v2_20261003/seed_audit.json)：冻结溯源关键文件；此归档仅保存选集，未包含完整冻结包。

- [outputs/formal_registry_repair_v2_20261003/seed_registry.json](sources/ABM_JASSS/outputs/formal_registry_repair_v2_20261003/seed_registry.json)：冻结溯源关键文件；此归档仅保存选集，未包含完整冻结包。



### 05 数值修复与恢复

- [formal_execution_incident_20261003.md](sources/ABM_JASSS/formal_execution_incident_20261003.md)：保留原失败事实、1 ULP 数值修复边界、中断及恢复过程。

- [formal_numeric_repair_protocol_20261003.md](sources/ABM_JASSS/formal_numeric_repair_protocol_20261003.md)：保留原失败事实、1 ULP 数值修复边界、中断及恢复过程。

- [formal_numeric_repair_resume_protocol_20261003.md](sources/ABM_JASSS/formal_numeric_repair_resume_protocol_20261003.md)：保留原失败事实、1 ULP 数值修复边界、中断及恢复过程。

- [outputs/formal_repair_v2_freeze_acceptance_20261003/](sources/ABM_JASSS/outputs/formal_repair_v2_freeze_acceptance_20261003/acceptance.json)：完整小型包，6 个文件；修复 v2 冻结前 279 项测试与登记检查的完整证据包。

- [outputs/formal_e2_e4_20261003/failures.json](sources/ABM_JASSS/outputs/formal_e2_e4_20261003/failures.json)：原始批次失败状态和失败名册；未改写为成功。

- [outputs/formal_e2_e4_20261003/manifest.json](sources/ABM_JASSS/outputs/formal_e2_e4_20261003/manifest.json)：原始批次失败状态和失败名册；未改写为成功。

- [outputs/formal_registry_repair_v2_20261003/numeric_repair_policy.json](sources/ABM_JASSS/outputs/formal_registry_repair_v2_20261003/numeric_repair_policy.json)：修复 v2 数值边界政策与修复上下文。

- [outputs/formal_registry_repair_v2_20261003/repair_context.json](sources/ABM_JASSS/outputs/formal_registry_repair_v2_20261003/repair_context.json)：修复 v2 数值边界政策与修复上下文。

- [outputs/formal_repair_interruption_20261003/observation.json](sources/ABM_JASSS/outputs/formal_repair_interruption_20261003/observation.json)：保留恢复中断的独立观察记录。

- [outputs/formal_repair_v2_interruption_20261004/observation.json](sources/ABM_JASSS/outputs/formal_repair_v2_interruption_20261004/observation.json)：保留恢复中断的独立观察记录。



### 06 正式结果与验收

- [formal_execution_acceptance_20261004.md](sources/ABM_JASSS/formal_execution_acceptance_20261004.md)：当前 E2–E4 正式批次完成、统计输出、来源与独立复核的总验收。

- [outputs/formal_e2_e4_repaired_v2_20261004_analysis/](sources/ABM_JASSS/outputs/formal_e2_e4_repaired_v2_20261004_analysis/report.md)：完整小型包，6 个文件；已通过正式分析、完整表图、全流程验收或独立复核的小型完整包。

- [outputs/formal_e2_e4_repaired_v2_20261004_report/](sources/ABM_JASSS/outputs/formal_e2_e4_repaired_v2_20261004_report/report_zh.md)：完整小型包，24 个文件；已通过正式分析、完整表图、全流程验收或独立复核的小型完整包。

- [outputs/formal_release_review_20261004/](sources/ABM_JASSS/outputs/formal_release_review_20261004/verification.json)：完整小型包，2 个文件；已通过正式分析、完整表图、全流程验收或独立复核的小型完整包。

- [outputs/formal_repair_v2_retry_execution_20261004/](sources/ABM_JASSS/outputs/formal_repair_v2_retry_execution_20261004/acceptance.json)：完整小型包，22 个文件；已通过正式分析、完整表图、全流程验收或独立复核的小型完整包。

- [outputs/formal_e2_e4_repaired_v2_20261004/configuration.json](sources/ABM_JASSS/outputs/formal_e2_e4_repaired_v2_20261004/configuration.json)：成功批次标识、配置、零失败和恢复来源；不包含完整原始数据。

- [outputs/formal_e2_e4_repaired_v2_20261004/failures.json](sources/ABM_JASSS/outputs/formal_e2_e4_repaired_v2_20261004/failures.json)：成功批次标识、配置、零失败和恢复来源；不包含完整原始数据。

- [outputs/formal_e2_e4_repaired_v2_20261004/manifest.json](sources/ABM_JASSS/outputs/formal_e2_e4_repaired_v2_20261004/manifest.json)：成功批次标识、配置、零失败和恢复来源；不包含完整原始数据。

- [outputs/formal_e2_e4_repaired_v2_20261004/recovery_provenance.json](sources/ABM_JASSS/outputs/formal_e2_e4_repaired_v2_20261004/recovery_provenance.json)：成功批次标识、配置、零失败和恢复来源；不包含完整原始数据。

- [outputs/formal_repair_v2_task_20261004/disable_result.json](sources/ABM_JASSS/outputs/formal_repair_v2_task_20261004/disable_result.json)：后台执行成功结束并自禁用的机器记录。

- [outputs/formal_repair_v2_task_20261004/task_result.json](sources/ABM_JASSS/outputs/formal_repair_v2_task_20261004/task_result.json)：后台执行成功结束并自禁用的机器记录。



### 07 论文写作

- [empirical_motivation_protocol.md](sources/ABM_JASSS/empirical_motivation_protocol.md)：论文结构、中英方法及结果工作稿、证据映射和经验动机边界。

- [manuscript_core_revision.md](sources/ABM_JASSS/manuscript_core_revision.md)：论文结构、中英方法及结果工作稿、证据映射和经验动机边界。

- [manuscript_methods_formal_20261004.md](sources/ABM_JASSS/manuscript_methods_formal_20261004.md)：论文结构、中英方法及结果工作稿、证据映射和经验动机边界。

- [manuscript_results_formal_20261004.md](sources/ABM_JASSS/manuscript_results_formal_20261004.md)：论文结构、中英方法及结果工作稿、证据映射和经验动机边界。

- [manuscript_work_20261004/methods_en.md](sources/ABM_JASSS/manuscript_work_20261004/methods_en.md)：论文结构、中英方法及结果工作稿、证据映射和经验动机边界。

- [manuscript_work_20261004/methods_evidence_audit.md](sources/ABM_JASSS/manuscript_work_20261004/methods_evidence_audit.md)：论文结构、中英方法及结果工作稿、证据映射和经验动机边界。

- [manuscript_work_20261004/results_en.md](sources/ABM_JASSS/manuscript_work_20261004/results_en.md)：论文结构、中英方法及结果工作稿、证据映射和经验动机边界。

- [manuscript_work_20261004/results_evidence_map.md](sources/ABM_JASSS/manuscript_work_20261004/results_evidence_map.md)：论文结构、中英方法及结果工作稿、证据映射和经验动机边界。

- [paper_outline_jasss.md](sources/ABM_JASSS/paper_outline_jasss.md)：论文结构、中英方法及结果工作稿、证据映射和经验动机边界。



### 08 历史开发附录

- [diagnostic_report.md](sources/ABM_JASSS/diagnostic_report.md)：历史开发证据；模型版本和测量定义不同，不能合并为正式样本。

- [outputs/core_restoration_v040_20260926/core_pilot_report.md](sources/ABM_JASSS/outputs/core_restoration_v040_20260926/core_pilot_report.md)：历史开发证据；模型版本和测量定义不同，不能合并为正式样本。

- [outputs/response_alignment_v040_20260926/report.md](sources/ABM_JASSS/outputs/response_alignment_v040_20260926/report.md)：历史开发证据；模型版本和测量定义不同，不能合并为正式样本。


