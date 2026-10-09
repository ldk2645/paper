# 项目接续记录：2026-10-03

**10月4日完成更新：E2/E3/E4正式恢复批次于2026-10-04 05:52:11（Asia/Shanghai）完整通过。** 恢复、只读验收、固定分析和中文表图均已完成：1184个区组、21312个物理终点、1000个独立seed，0失败；102项主分析全部实际精度半宽≤0.02，45项通过Holm检验，532项辅助结果。3项pilot规划预算风险及61项pilot方差不稳定说明保留，不代表正式结果仍有精度不足。一次性Windows任务已成功自禁用，不再需要为本批次保持登录。

当前可引用证据见[正式执行验收](formal_execution_acceptance_20261004.md)、[论文正式方法](manuscript_methods_formal_20261004.md)、[论文正式结果](manuscript_results_formal_20261004.md)和[完整中文结果报告](outputs/formal_e2_e4_repaired_v2_20261004_report/report_zh.md)。成功恢复批为 `outputs/formal_e2_e4_repaired_v2_20261004/`，分析目录为 `outputs/formal_e2_e4_repaired_v2_20261004_analysis/`，完整验收及全流程记录为 `outputs/formal_repair_v2_retry_execution_20261004/validation.json`、`acceptance.json`。当前冻结源码仍匹配 `outputs/formal_registry_repair_v2_20261003/`，模型包和正式设计未改动。

原批1183成功／1失败的状态及两次未正常收尾的恢复尝试均保留。成功批复用1183个完整区组的原始gzip字节，按原seed重跑唯一失败区组的完整18臂，新增独立样本为0。不要将原失败批改称成功，也不要把不同恢复目录相加计算样本。接续详情见[10月4日记录](project_handoff_20261004.md)和[运行与修复记录](formal_execution_incident_20261003.md)。

## 10月3日恢复过程历史记录

第二版恢复曾于2026-10-03 19:17在隐藏后台启动，当时正式推断尚待完整验收。原批1183个区组成功，1个数值导出失败；首次恢复在395个完整区组后未正常收尾，原因未确定，旧目录保留。新恢复流程通过279项测试，于2026-10-03 19:13冻结，19:17启动。该次后台编排为 `outputs/formal_repair_v2_execution_20261003/execute.py`，启动记录及控制台日志位于 `outputs/formal_repair_v2_launcher_20261003/`；后来在源清单核验期间停止，原因未知，未创建目标批次。10月4日一次性系统任务使用相同冻结代码在新输出路径完成全流程。不要修改冻结源码、覆盖已有批次或重复启动历史示例。下文保留历史交接，不表示seed现在未使用。

当时可从 `ABM_JASSS/` 使用以下观察器只读查看该次后台状态；它对应已停止的历史尝试：

```powershell
python -B outputs/formal_repair_v2_launcher_20261003/status.py
```

该观察器不是验收门禁；阶段开始记录仅说明曾启动，单独出现部分区组或图表不能替代全流程验收。该历史尝试未产生最终验收；当前成功证据是上文20261004重试目录的 `acceptance.json` 及其绑定的完整验收报告。

以下为原启动前历史说明：当时活跃目录为 `ABM_JASSS/`，模型为0.5.1-dev，E2/E3/E4正式设计与分析冻结已验收，正式seed尚未仿真。原证据见 [冻结验收报告](formal_freeze_validation_20261003.md)。

## 原启动前已完成与已确认

- 用户选择保留每条件1000上限，明确报告3项pilot规划预算风险；61项pilot方差不稳定也保留。此处为冻结前规划判断，正式实际精度见顶部完成更新。
- 正式共享n固定为α=0.25的184、α=0.75的1000。新seed71001–72000，低α取前184；共1000独立seed、1184区组、21312个物理终点、22496条统计臂记录。
- [执行与分析协议](formal_execution_protocol_20261003.md)、[完整配置](configs/formal_design_20261003.json)、102项主分析与辅助结果均冻结。不根据正式结果追加样本或更改推断方法。
- 全量253项测试通过；种子审计1972文件、零碰撞；冻结包121文件哈希通过。
- 模型包仍为 `67726e88836bbfc3c9cd8a6b214c48560ea46e637eac4c35573e3566fef332d1`，历史pilot和S0/S1产物未改写。

## 原冻结入口与产物

- `outputs/formal_registry_20261003/`：通过验收的不可覆盖冻结包。manifest为 `formal_ready=true`，配置模板仍为false；勿手改此状态。
- `outputs/formal_freeze_acceptance_20261003/`：测试日志/证据、登记校验、执行计划及验收清单。
- `scripts/run_formal_study.py`：固定名册 `plan/run/validate/analyze` 入口；无样本量、seed、条件或窗口覆盖选项。
- `scripts/formal_runtime.py`、`formal_artifacts.py`：正式原始产物及只读重建；保持pilot物理行为，不改变旧pilot模块全局状态。
- `scripts/formal_inference.py`：母世界配对、联合可测支持、点态t区间与102项Holm校正；辅助结果另作描述。

原冻结包保存当时代码/测试/依赖和合同哈希；成功恢复批使用顶部所列第二版修复冻结包。执行或验收须使用匹配版本，不得修改冻结文件。README、本文和验收说明不属于冻结模型合同，可以记录后续状态。实际环境为Python 3.12.14、NumPy 2.3.5；本机Python路径为 `C:\Users\17003\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`。

## 历史启动示例（仅保留记录，不重复运行）

以下是原启动前为 `ABM_JASSS/`准备的命令示例。编写时`plan`已由冻结编排核验，正式名册尚未运行；该状态现已过时，实际执行路径及命令应以上文成功验收记录为准。示例不构成重新运行授权，也不表示所列输出路径现在仍未使用。

```powershell
python -B scripts/run_formal_study.py plan outputs/formal_registry_20261003
python -B scripts/run_formal_study.py run outputs/formal_registry_20261003 --output outputs/formal_e2_e4_batch01 --workers 3
```

运行完成后，将只读校验的JSON报告保存到批次目录之外；失败时先处理错误，不进入分析：

```powershell
$reportPath = 'outputs/formal_e2_e4_batch01_validation.json'
if (Test-Path -LiteralPath $reportPath) { throw 'Validation report already exists' }
$validationText = python -B scripts/run_formal_study.py validate outputs/formal_e2_e4_batch01 --workers 3
if ($LASTEXITCODE -ne 0) { throw 'Formal validation failed' }
$validationText | Set-Content -LiteralPath $reportPath -Encoding utf8
python -B scripts/run_formal_study.py analyze outputs/formal_e2_e4_batch01 --output outputs/formal_e2_e4_batch01_analysis --validation $reportPath
```

分析校验报告与当前manifest和整批文件清单绑定；验收后原始或派生产物改变会阻止分析。输出包括102行主表 `primary.csv`、带有效分母的辅助表 `auxiliary.csv`、推断JSON、说明、分析manifest及文件哈希。无回应的主3保持缺失；不足30联合有效或数值退化仅报告描述值，不补样。操作性失败保留traceback和原母世界，不替换seed或发布不完整正式分析。

## 后续研究范围

E2/E3/E4正式结果现已生成并通过完整验收，可按[论文正式结果](manuscript_results_formal_20261004.md)与绑定主表写本次登记条件下的方向和Holm结论。E5动态转变／机制恢复、结构稳健性、E6信任预警留出验证、经验材料及英文论文继续待办；不能将已完成的数据恢复误作这些机制实验。pilot40个独立seed及其他开发种子均不能并入正式样本；跨α共用seed及E3 baseline复用也不增加独立重复。

9月27/29日及10月2/3日接续内容保留为历史记录，最新状态以本文顶部完成更新、[10月4日接续记录](project_handoff_20261004.md)及[正式执行验收](formal_execution_acceptance_20261004.md)所绑定产物为准。
