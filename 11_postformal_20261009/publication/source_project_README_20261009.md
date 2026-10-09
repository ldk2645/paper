# ABM：反向黑箱与政府回应的结构性限度

**2026-10-09完成：** 稳健性、No Drift及规模/时长补充研究于11:31完整通过运行、只读验收、统计和报告四阶段：6000区组、49,200物理终点、200个独立seed，0失败，1362项主结果及3556行辅助描述已输出。见[最终验收](postformal/robustness/execution_20261008/acceptance.json)、[结果报告](postformal/robustness/execution_20261008/report/report.md)和[最新接续记录](postformal/postformal_handoff.md)。这表示模拟全流程完成，不表示所有设定结论一致；经验线仍只有24个调查开发值，Trends配对和论文整合尚待推进。

当前主线为独立的 **0.5.1-dev 识别引擎**。E2/E3/E4正式恢复批次于 **2026-10-04 05:52:11（Asia/Shanghai）完整通过**恢复、只读验收、固定统计和中文表图导出：1184个区组、21312个物理终点、1000个独立seed，0失败；102项主分析全部实际精度半宽≤0.02，45项通过Holm检验，另有532项辅助结果。Windows一次性任务已成功自禁用，不再需要为本批次保持登录。详见[正式执行验收](formal_execution_acceptance_20261004.md)和[完整中文结果报告](outputs/formal_e2_e4_repaired_v2_20261004_report/report_zh.md)。原失败批次的1183成功／1失败状态、两次未正常收尾的恢复尝试及全部历史产物仍保留，见[运行与修复记录](formal_execution_incident_20261003.md)。

用户已确认保留每条件1000上限；正式跨family共享n固定为α=0.25的184和α=0.75的1000。正式seed71001–72000，低α取前184；共1184个α×seed区组、21312个物理终点。102项分析全部保留；3项pilot规划预算风险和61项pilot方差不稳定说明也保留。冻结时不保证实际精度，本次正式样本的102项观察半宽现已全部达标，不能将3项规划风险写成正式结果仍有3项精度不足。见[正式执行与分析协议](formal_execution_protocol_20261003.md)。

2026-10-02的 [独立精度pilot](precision_pilot_validation_20261002.md)保留原验收证据：212项测试、40个独立seed、80区组、1440终点、0失败，两批各9546文件哈希及重建通过。pilot已按40个seed停止，不追加或并入正式样本。

2026-09-29 的 [P1/S1验收](s1_validation_20260929.md)保留原有证据：163项测试，串行与双进程各134条记录（120完整、14动态检查点），0失败，全部产物重建与比较通过。

0.5.0-dev 的 [S0 验收](s0_validation_20260928.md)及24个四格世界、30条分支后缀原始产物保持完整，历史复核通过。各版本应使用对应存档源码复现。

0.4.0（2026-09-26）旧引擎及历史结果保留。研究主线为政府在算法中介下的双重信息弱势、放大与阻尼的竞争、行政回应节律及工具边界、信任反馈、可能的临界变化。0.3.x的偏好测量模块保留为诊断层；主问题是政府在怎样的注意力架构下能够纠偏、何时受到结构性限制。保留理论问题不意味着保留未经新版检验的旧阈值和结论。

2026-09-27 r2计划以[正式实验协议](formal_experiment_protocol.md)为总纲，[信号与结果合同](signal_and_outcome_contract.md)明确P/E/S/P̂分层、源信号与已交付包、缺失和完成率规则；[落实表](technical_checklist_response_20260927.md)保留原19项并补6项合同任务。计划文件中的历史状态以当日为准，最新实现及验收见[research_engine.md](research_engine.md)和[正式执行验收](formal_execution_acceptance_20261004.md)；本阶段正式运行、只读验收及结果分析均已完成，下一步是据验收结果推进论文。

## 从这里开始

- [下一阶段计划](postformal_next_steps_20261004.md)：**暂缓E5/E6，优先经验锚点、结构稳健性与No Drift**；先准备新增协议/预算并核查英国数据可行性，再按冻结设计执行，既有E2–E4保持不变。
- [正式执行验收](formal_execution_acceptance_20261004.md)、[论文正式方法](manuscript_methods_formal_20261004.md)与[论文正式结果](manuscript_results_formal_20261004.md)：本阶段完整验收、固定推断口径和可引用结果；[完整中文表图报告](outputs/formal_e2_e4_repaired_v2_20261004_report/report_zh.md)保留全部102项主结果。
- [英文Methods工作稿](manuscript_work_20261004/methods_en.md)与[结果证据对应表](manuscript_work_20261004/results_evidence_map.md)：论文工作材料，以正式验收和上述方法／结果稿为当前依据；[方法核对表](manuscript_work_20261004/methods_evidence_audit.md)记录术语、分母和解释边界。
- [10月4日接续记录](project_handoff_20261004.md)：本次成功恢复批路径、系统任务完成状态及保留的中断证据。
- [正式运行与修复记录](formal_execution_incident_20261003.md)：原批1 ULP导出故障、279项测试、两次未正常收尾的恢复及最终成功批；原失败状态保留。
- [项目接续记录](project_handoff_20261003.md)、[正式冻结验收](formal_freeze_validation_20261003.md)、[正式执行协议](formal_execution_protocol_20261003.md)与[原冻结包](outputs/formal_registry_20261003/manifest.json)：原设计、固定预算和推断规则；当前恢复批绑定[第二版修复冻结包](outputs/formal_registry_repair_v2_20261003/manifest.json)。
- [pilot实测验收报告](precision_pilot_validation_20261002.md)与[历史冻结准备清单](formal_freeze_readiness_20261002.md)：规划依据和保留的限制。
- [pilot运行前登记](precision_pilot_protocol_20260930.md)与[合并规划报告](outputs/precision_pilot_20261002_planning/report.md)：固定20+20预算、102项规划、样本量候选与稳定性诊断。
- [新引擎说明](research_engine.md)：0.5系列的时序、权限、快照、随机流与产物。
- [S1 实测验收报告](s1_validation_20260929.md)：固定计划回放、机制四格、动态诊断和完整产物验收。
- [S1执行登记](s1_execution_protocol_20260929.md)与[动态说明](s1_dynamic_protocol.md)：实际设计、参考条件及计数边界。
- [S0 实测验收报告](s0_validation_20260928.md)：测试、批次、复现命令、修复及后续工作。
- [修订研究计划](research_plan.md)：原创新主线、三层机制识别和待做实验。
- [创新保留对照](innovation_preservation.md)：原文依据、已恢复机制与仍需检验的命题。
- [论文论证修订](manuscript_core_revision.md)：题目、引言主线与可检验命题。
- [七章行文框架](paper_outline_jasss.md)：整合用户初步框架，区分三层模型结果与两类经验材料。
- [经验动机协议](empirical_motivation_protocol.md)：第3章数据候选、可比性和结论范围。
- [0.3.0开发记录](diagnostic_report.md)：仅对应旧测量诊断版本，不能用于反驳原完整模型的相变命题。
- [新引擎英文ODD](ODD_research.md)：0.5.1-dev实际模型与开发实验；[历史ODD](ODD.md)保留0.4.0说明。
- [参数表](parameters.md)：旧引擎默认值、试跑覆盖值及假设性质；新引擎以 research_config.py 和批次 resolved_design.json 为准。
- [修改与验证记录](revision_validation_20260926.md)：43项通过测试、480次开发仿真及行文框架对应的后处理。
- `abm_jasss/research_world.py`、`research_s1_cli.py`：当前识别引擎与S1入口；`research_cli.py`为S0入口；`model.py`、`governance.py`、`cli.py`保留旧引擎入口。

## 运行

已验证环境：Windows、Python 3.12.14、NumPy 2.3.5。从 `ABM_JASSS/`可只读检查正式计划；该命令不启动仿真。本阶段已经完成，不重复启动已有批次。实际执行证据见[正式执行验收](formal_execution_acceptance_20261004.md)，历史命令保留在[接续记录](project_handoff_20261003.md)。

```powershell
python -B scripts/run_formal_study.py plan outputs/formal_registry_repair_v2_20261003
```

以下为pilot已执行的入口与验收/分析命令记录；所列历史输出路径现已存在，运行及分析入口均拒绝覆盖。

```powershell
python -B scripts/execute_precision_pilot.py --config configs/precision_pilot_20260930.json --prefix precision_pilot_20261002 --workers 3
python -B scripts/validate_precision_pilot.py outputs/precision_pilot_20261002_initial --workers 3
python -B scripts/validate_precision_pilot.py outputs/precision_pilot_20261002_expansion --workers 3
python -B scripts/analyze_precision_pilot.py outputs/precision_pilot_20261002_initial outputs/precision_pilot_20261002_expansion --output outputs/precision_pilot_20261002_planning --validation-initial outputs/precision_pilot_20261002_acceptance/validate_initial.json --validation-expansion outputs/precision_pilot_20261002_acceptance/validate_expansion.json
```

`execute_precision_pilot.py`依次执行全量测试、两批运行、两批只读验收及合并规划；实际Python路径、各子命令、日志和哈希见 `outputs/precision_pilot_20261002_acceptance/acceptance.json`。校验不推进物理tick；合并分析绑定对应批次的验收报告。S1开发入口保留如下：

```powershell
python -B -m unittest discover -s tests -v
python -B -m abm_jasss.research_s1_cli --config configs/research_s1.json --output outputs/my_s1 --workers 2
python -B scripts/validate_s1_outputs.py outputs/my_s1
python -B scripts/validate_s1_outputs.py outputs/research_s1_20260929_serial --compare outputs/research_s1_20260929_parallel
```

新批次路径必须尚不存在；校验及比较只读取已有批次。允许执行本地PowerShell脚本的环境也可用 `run_research.ps1` 的 `test/s1/validate-s1/compare-s1` 模式；比较参数为 `-Output <第一批> -CompareWith <第二批>`。S0保留原 `s0/validate/compare` 模式。本次实测使用上述Python入口；9月28日直接执行`.ps1`曾被本机执行策略拒绝。

以下是 **0.4.0 历史引擎** 的运行方式：

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

当前可引用正式批为 `outputs/formal_e2_e4_repaired_v2_20261004/`，完整只读验收和全流程通过记录位于 `outputs/formal_repair_v2_retry_execution_20261004/validation.json`、`acceptance.json`。主表、辅助表、分析manifest及文件哈希在 `outputs/formal_e2_e4_repaired_v2_20261004_analysis/`，中文表图在 `outputs/formal_e2_e4_repaired_v2_20261004_report/`。1183个完整区组保留原始gzip字节，唯一失败区组按原登记seed重跑完整18臂；新增独立样本为0。原批 `outputs/formal_e2_e4_20261003/`仍是失败批，不能与成功恢复批混称，也不能将两个批次相加计数。

独立pilot的两批产物位于 `outputs/precision_pilot_20261002_initial/` 和 `outputs/precision_pilot_20261002_expansion/`。每批保存完整配置/解析设计、源码/测试/协议快照、母状态、供体计划、政府合法输入与评价真值、确定性gzip原始日志、逐世界汇总及全部母ID/缺失模式。`outputs/precision_pilot_20261002_planning/`保存 `planning.json`、`planning.csv`、`stability.json`、报告与输入/分析代码哈希；只读验收和命令证据位于对应 `_acceptance/`目录。相同seed跨α复用、E3 baseline复用I00、E4 B0复现I00均不增加独立样本数。

0.5系列批次包含manifest、配置、解析设计、源码快照、分世界raw、derived、checks、配对诊断和全文件哈希。S0母状态在 `snapshots/`；S1另保存 `dynamic_snapshots/` 和 `diagnostics/`，最终世界状态在各raw的 `evaluator/snapshot.json`。政府输入与评价真值分目录，统计可重建。S1历史重建需匹配完整存档引擎；S0校验器保持原有分析器版本规则。

0.4.0 旧实验目录包含 `manifest.json`、`source_snapshot`、`resolved_design.json`、逐世界 JSON、`trajectories`、`events`、`runs.csv`、测量统计、`governance_metrics.csv` 和简报。事件记录区分排期、执行、回应发文与即时热度变化；期末未执行动作和未结束事件保留。失败写入 `failures.json`，不生成部分成功样本的聚合推断。`governance_metrics.csv` 区分政府议程、公众偏好失配与信任结果，不把三者合成一个“治理成功”指标。

重跑历史版本时，把该次 `source_snapshot/abm_jasss` 复制到一个独立目录，在该目录使用 manifest 中的 specification 保存为 JSON 后运行模块；依赖版本也应与 manifest 一致。浮点结果跨平台不承诺逐字节相同。已测试本机串行与双进程输出一致。

0.3.0历史开发结果位于 `outputs/diagnostics_v030_20260924` 和 `outputs/feedback_v030_20260924`。恢复版试跑入口是 `outputs/core_restoration_v040_20260926/core_pilot_report.md`；只在全部情景完成后生成该汇总。各版本的真值、政府工具和结果指标不同，不能拼接成同一统计样本。历史 `scripts/document_results.py` 仅重建0.3.0报告；当前参数表用 `python scripts/document_parameters.py` 生成。

## 历史源代码审阅

原文对应仓库为 [ldk2645/paper](https://github.com/ldk2645/paper)。审阅时其 `release_qa.json` 的12项完整性检查均通过；仓库包含冻结 V1 模型、正式五条件消融数据、敏感性运行、外部数据表及完整图表溯源。它们值得作为历史证据保留。

V1 的议程外类别与公众潜在偏好含义不同。新版同时保留政府议程指标与公众偏好指标，明确二者可能不一致。0.4.0已经实现阈值排队、延迟热度调节、日常发布、回应曝光、信任反馈和持续事件，不再只将它们登记为未来参考。信任方程做了可解释的重新参数化，并提供替代规则；外部回归系数未直接迁入，因此不是V1数值复现。

## 当前范围与下一步

P0/S0、P1/S1技术验收、独立精度pilot以及E2–E4冻结正式运行、完整只读验收和结果分析均已完成。下一步是将本次已验收证据纳入论文，保留固定预算、条件估计对象和多重比较规则。E5动态转变／机制恢复与结构稳健性、E6信任预警、经验配对材料和英文论文仍待完成；这些研究任务不同于本次已完成的数据导出故障恢复。

用户初步行文框架已整合为七章结构，详见paper_outline_jasss.md。旧三层诊断结果位于`outputs/response_alignment_v040_20260926/report.md`：480世界的93,879组执行回应已计算触发/执行目标错配，空动作NA。该批配置的曝光偏差与平台估计误差按定义重合，尚无独立公开S；不能当作r2新主1 TV(P,S_public)的结果。经验动机章节尚未形成配对数据或经验结论。

主模型启用情绪—互动—热度—曝光回路、偏好漂移、有限排期能力的延迟回应与信任反馈。消融区分无定向回应（保留日常发布）、仅取消热度调节（保留回应发文）、取消信任对互动的反馈（保留信任状态更新）。信任有暴露惩罚与偏好匹配两种规则；调查、融合和公众偏好oracle用于分解信息限制。

本次E2检验信息条件四格，E3区分闭环时序与固定计划回放，E4比较同一状态分支后的下游回应和上游排序干预；具体范围见[论文正式方法](manuscript_methods_formal_20261004.md)与[论文正式结果](manuscript_results_formal_20261004.md)。初值／正反扫描／机制恢复检验及信任诊断留出验证仍未由本批完成。公众偏好oracle不等于算法透明；不同α各自从头运行不等于同状态架构干预；短时窗未恢复不等于不可逆。旧文的创新命题保留为可被推翻的研究问题，0.4.0开发结果不能替代本次正式证据。
