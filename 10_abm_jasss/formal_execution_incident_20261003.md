# 正式批次导出边界故障与修复记录（2026-10-03）

**10月4日完成更新：2026-10-04 05:52:11（Asia/Shanghai）正式恢复批次完整通过。** 1184个区组、21312个物理终点、1000个独立seed，0失败；102项主分析实际精度半宽全部≤0.02，45项通过Holm检验，另有532项辅助结果。一次性Windows任务已成功自禁用，不再需要为本批次保持登录。正式证据见[执行验收](formal_execution_acceptance_20261004.md)、[论文方法](manuscript_methods_formal_20261004.md)、[论文结果](manuscript_results_formal_20261004.md)和[完整中文表图报告](outputs/formal_e2_e4_repaired_v2_20261004_report/report_zh.md)。原失败批与两次未正常收尾的恢复尝试均保留，不改变历史状态。

第二版隐藏进程也曾在源清单核验期间未正常收尾，原因未知，未创建目标批次目录。中断记录保留；10月4日00:18:30使用相同冻结源码启动Windows一次性计划任务，并在新输出路径完成上述验收。当前路径及接续记录见[10月4日接续记录](project_handoff_20261004.md)。下文先保留10月3日事件，再记录最终成功批。

原正式批次于2026-10-03 13:43:16启动、15:45:52结束（Asia/Shanghai），采用登记的184／1000规模、1000独立seed和12个工作进程。1183个区组成功，1个因已复现的数值导出边界错误失败。首次修复恢复于15:46:04启动，最后记录为395／1184区组；观察时已无Python进程，未生成恢复结果、最终manifest或文件清单，停止原因未知。截至该次中断观察时，正式推断尚未发布。

## 故障及证据

α=0.75、seed71100的E2 I11世界正常运行到300 tick。随后导出调用 `summarize_world()`，因 `signal_estimate_distance=1.0000000000000002` 超过严格上界1而报错。该值出现在tick265–269，比1大一个浮点单位 `2.220446049250313e−16`。信号和估计向量合法，使用 `math.fsum` 重算距离为1.0；故障发生于派生数据导出，没有改变物理推进。

- [原运行日志](outputs/formal_execution_20261003/run.log)持续保存全部区组完成及失败状态。
- [复现traceback](outputs/formal_failure_diagnostic_20261003/failure.json)、[距离检查报告](outputs/formal_failure_diagnostic_20261003/i11_distance_inspection/distance_report.json)和[完整诊断snapshot](outputs/formal_failure_diagnostic_20261003/i11_distance_inspection/snapshot.json.gz)保留原始值。
- 诊断只复现同一已登记单位，标记为 `eligible_for_formal_analysis=false`，不增加独立样本、不进入正式聚合。

原失败批次已保留失败状态、成功组、失败清单和完整文件哈希。所有登记单位仍须完成，失败组不删除、不替换种子。

## 已验证的修复

修复在独立目录 `formal_repair_20261003/`完成。`abm_jasss`模型包、依赖声明、正式配置、解析作业、推断政策和种子名册与父登记完全一致。仅变动8个允许的导出、恢复、登记、编排和相关测试文件。

派生层采用固定绝对容差 `1e−12`，仅规范有合法概率向量支持且重建一致的微小TV边界误差。原始snapshot、轨迹、事件及压缩记录保留原值；每次规范都记录字段、时间、来源、原值、派生值和容差。超容差、非有限值或非法向量继续拒绝，配置阈值仍严格检查，缺失及正式推断规则不变。完整政策见[修复协议](formal_repair_20261003/formal_numeric_repair_protocol_20261003.md)。

全量277项测试通过，日志用时274.443秒；包含新增11项数值修复、6项恢复及7项修复登记测试。回归使用已保存的真实故障snapshot，不再次推进该正式世界。另已确认正常派生值保持原值，成功组恢复不推进任何tick，所有原始gzip逐字节一致，旧产物的内容与修改时间不变。

修复登记于2026-10-03 14:32:52完成，当前证据位于[修复冻结验收](formal_repair_20261003/outputs/formal_repair_freeze_acceptance_20261003/acceptance.json)和[修复registry](formal_repair_20261003/outputs/formal_registry_repair_20261003/manifest.json)。

模型包哈希仍为 `67726e88836bbfc3c9cd8a6b214c48560ea46e637eac4c35573e3566fef332d1`；修复registry manifest哈希为 `9eb7fb9ba27db77cd657f87d50e6eba540795cbcba1631735ce0d546c4c4cf42`。继承原冻结时的种子审计，声明 `additional_independent_samples=0`，不把已运行seed重新声称为未使用seed。

## 首次恢复中断与第二版接续

[首版恢复编排](outputs/formal_repair_execution_20261003/execute.py)在原进程结束后提升已冻结文件并开始恢复。日志最后停在395个完整区组，没有最终验收；进程停止原因尚无可核实证据。[中断观察记录](outputs/formal_repair_interruption_20261003/observation.json)保存观察时间、完整组名单、既有编排文件哈希和缺失的最终文件。原失败批与首次未完成恢复目录均原样保留。

新工作副本 `formal_repair_resume_20261003/` 仅优化恢复入口及对应测试：完整组逐字节复制原gzip，从snapshot用既有纯函数重建metadata及修复后的派生数据，不构造或推进物理世界；唯一失败组仍用原seed重跑完整18臂。第二版仍以原冻结登记为父，保留固定数值政策、物理模型、设计、推断及独立样本数。

第二版全量279项测试通过，日志用时138.623秒，于2026-10-03 19:13:02冻结。[冻结验收](outputs/formal_repair_v2_freeze_acceptance_20261003/acceptance.json)绑定新registry manifest哈希 `f80eb9f1756f49de37655bd53f4d687276b3ebdb55dcfeff27f81cbac1e56230`，模型包哈希保持不变。本次相对第一修复仅提升恢复脚本及其测试；新协议见[恢复流程重新冻结协议](formal_numeric_repair_resume_protocol_20261003.md)。

[第二版历史编排](outputs/formal_repair_v2_execution_20261003/execute.py)于19:17:26在隐藏后台启动（原启动PID29252，仅为历史身份，该进程已停止），候选及提升后的计划门禁均通过。启动记录和控制台日志位于[launcher](outputs/formal_repair_v2_launcher_20261003/process.json)。它原拟在 `outputs/formal_e2_e4_repaired_v2_20261003/` 恢复，并顺序执行完整只读语义验收、固定分析及中文图表导出，但在源清单核验期间未正常收尾，未创建目标批次或发布正式分析。1184区组、21312终点及22496条统计臂记录齐全且验收通过的门禁在随后成功重试中仍完整执行。

第一版未完成恢复目录 `outputs/formal_e2_e4_repaired_20261003/` 不覆盖。第二版该次尝试原拟使用 `...repaired_v2_20261003_analysis/` 和 `...repaired_v2_20261003_report/`，没有形成可引用正式结果。每条件1000上限、3项pilot规划预算风险和61项pilot方差不稳定说明保留；不追加样本，不依结果更改推断方法。

## 10月4日最终成功恢复与验收

一次性Windows任务 `ABM_JASSS_Formal_Recovery_20261004` 于2026-10-04 00:18:30启动[重试编排](outputs/formal_repair_v2_retry_execution_20261004/execute.py)，使用同一第二版冻结registry，未再次提升或修改冻结源码。最终[全流程验收](outputs/formal_repair_v2_retry_execution_20261004/acceptance.json)于05:52:11写入 `status=passed`；计划核对、恢复、完整只读语义验收、固定分析及中文图表导出五个阶段退出码均为0。

- 成功恢复批：`outputs/formal_e2_e4_repaired_v2_20261004/`，batch ID为 `formal_recovered_245a476e7f5646e7bdb8a17b430f1ad6`。1184区组、21312物理终点、1000独立seed、0失败；1183个完整区组的原始gzip逐字节保留，原唯一失败区组使用原seed重跑完整18臂，`additional_independent_samples=0`。
- 原批 `outputs/formal_e2_e4_20261003/` 的最终状态仍为失败，`original_status_retained=failed`；首次未完成恢复和第二次中断证据也保留。成功恢复不抹去故障，不把重跑或目录副本计作新样本。
- [完整只读验收](outputs/formal_repair_v2_retry_execution_20261004/validation.json)与成功批manifest、整批文件清单绑定；[分析manifest](outputs/formal_e2_e4_repaired_v2_20261004_analysis/analysis_manifest.json)和[报告摘要](outputs/formal_e2_e4_repaired_v2_20261004_report/summary.json)继续绑定该验收身份。
- 102项主分析全部可估计，α=0.25联合有效分母均为184，α=0.75均为1000，主项缺失计数全0；532项辅助结果有效分母也等于总分母。观察半宽为0.000076385至0.019920800，全部≤0.02；102项Holm校正后45项拒绝。
- 3项pilot规划预算风险及61项pilot方差不稳定说明保留。3项规划风险对应的正式实际半宽均已达标；不能把规划风险写成3项正式精度不足，也不能据本次达标删除历史方差诊断。
- [任务完成记录](outputs/formal_repair_v2_task_20261004/task_result.json)和[自禁用记录](outputs/formal_repair_v2_task_20261004/disable_result.json)退出码均为0。任务已完成并成功自禁用，不再要求保持登录，不重复启动。

正式论文使用[执行验收说明](formal_execution_acceptance_20261004.md)、[方法稿](manuscript_methods_formal_20261004.md)、[结果稿](manuscript_results_formal_20261004.md)及[全部102项中文表图](outputs/formal_e2_e4_repaired_v2_20261004_report/report_zh.md)。主表点态区间与102项Holm检验应分开解释；辅助结果只作描述。本次数据恢复不构成E5机制恢复实验，不扩大既定模型与设计的推断范围。
