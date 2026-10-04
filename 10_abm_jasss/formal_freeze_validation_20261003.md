# E2–E4正式冻结验收（2026-10-03）

**正式设计与分析冻结已通过；登记的正式样本尚未运行。** 用户确认的每条件1000个母世界上限已落实，3项规划精度不足与61项方差不稳定均保留。冻结包的 `formal_ready=true` 仅放行本次E2/E3/E4固定设计和执行工具，不表示已有正式研究结果。

## 实际验收

| 项目 | 结果 |
|---|---|
| 全量测试 | 253项通过，测试日志用时128.083秒；无失败或跳过 |
| 正式流程专项 | 41项：统计17、登记9、原始运行/重建8、整批衔接7 |
| 种子审计 | 1972个文件；1000个候选seed，零碰撞 |
| 冻结清单 | 121个文件哈希通过，另有清单文件自身；覆盖65个源码/测试/依赖文件 |
| 模型版本 | 0.5.1-dev；模型包源码未变 |
| 环境 | Windows、Python 3.12.14、NumPy 2.3.5 |
| 正式seed已执行数 | 0；微型测试夹具独立于正式种子 |
| 冻结状态 | `status=frozen`、`formal_ready=true`；配置模板仍为false |

实际执行入口为 `python -B scripts/freeze_formal_design.py`，内部先运行 `python -B -m unittest discover -s tests -v`，再构建、只读校验冻结包并核验执行计划。完整Python路径、返回码、源码哈希和日志见 [tests.json](outputs/formal_freeze_acceptance_20261003/tests.json) 与 [tests.log](outputs/formal_freeze_acceptance_20261003/tests.log)。冻结完成时间为2026-10-03 12:14:00（Asia/Shanghai）。

专项测试覆盖母世界配对和联合支持、t分布数值与尾部、全102项Holm校正、缺失/零方差处理、已有目录保护、种子碰撞、代码或登记变更拦截、原始记录只读重建、失败记录保留、陈旧验收报告拒绝，以及无回应时的主3缺失和辅助结果分母。微型端到端测试实际运行模型后生成102项结果，但不足最低有效数的项不生成推断。测试夹具不构成正式样本。

## 冻结规模与精度限制

| α | 每条件母世界数 | 固定seed | α×seed区组 | 物理终点 |
|---|---:|---|---:|---:|
| 0.25 | 184 | 71001–71184 | 184 | 3312 |
| 0.75 | 1000 | 71001–72000 | 1000 | 18000 |
| 合计 | 各家族共享 | 1000个独立seed | 1184 | 21312 |

每区组18个物理终点；E3闭环baseline复用E2 I00，统计名册每区组19臂，共22496条。跨α嵌套seed、继承前缀和处理臂均不增加独立重复。完整N=100、T=300、末窗200–299、分叉150及估计器设定保存在 [配置](configs/formal_design_20261003.json) 和 [执行协议](formal_execution_protocol_20261003.md)。

三项不足全部在α=0.75：

| 对比 | 指标 | 未截断母世界总需求 | 冻结总n |
|---|---|---:|---:|
| E3闭环 delay0−baseline(delay3) | 主1：平台表征差距 | 1293 | 1000 |
| 同上 | 主3：触发时目标错配 | 1071 | 1000 |
| E3回放 delay3−delay0 | 主1：平台表征差距 | 1002 | 1000 |

全部102项保留；61项pilot方差变化超过25%的不稳定说明保留在冻结证据中。固定样本不保证正式半宽≤0.02；正式结果将报告实际有效数与半宽，不根据效果、显著性或精度追加样本。

主分析的条件支持集、点态t区间、全102项Holm校正、数值下限和异常处理已登记；辅助结果按母世界等权并报告各自有效分母。正式区间假设及适用限制见协议，pilot规划不能代替实际正式精度。

## 溯源证据

- [冻结manifest](outputs/formal_registry_20261003/manifest.json)、[完整哈希清单](outputs/formal_registry_20261003/artifact_hashes.json)：配置、作业、推断政策、种子登记、协议/合同、源码、测试和证据快照。
- [种子审计](outputs/formal_registry_20261003/seed_audit.json)：历史配置/输出seed字段和源码整数扫描，记录逐文件哈希；不声称能求值任意Python表达式。
- [验收摘要](outputs/formal_freeze_acceptance_20261003/acceptance.json)、[只读登记校验](outputs/formal_freeze_acceptance_20261003/registry_validation.json)、[执行计划](outputs/formal_freeze_acceptance_20261003/execution_plan.json)与[验收证据清单](outputs/formal_freeze_acceptance_20261003/evidence_hashes.json)。
- `evidence/project/`保存pilot验收/规划、已验收原始产物的清单绑定与选定汇总输入，以及S0/S1验收和最终测试日志。冻结时重建汇总规划；完整pilot raw仍保留在原批次，不在冻结包重复拷贝。

模型包SHA-256：`67726e88836bbfc3c9cd8a6b214c48560ea46e637eac4c35573e3566fef332d1`。

冻结manifest SHA-256：`707b7d97cf8c3b0ada81caa246610fc6346b9fc4c224897b00171cf19931a3d8`。

## 下一阶段与边界

下一阶段按固定名册运行21312个终点，完成raw只读验收后生成主表、辅助表及推断JSON。命令见 [项目接续记录](project_handoff_20261003.md)。正式入口核查冻结配置、代码和合同；修改后不能沿用本次测试证据。所有新批次、验收文件和分析目录均使用新路径，历史产物不覆盖。

E5动态转变/恢复、结构稳健性、E6信任预警留出验证、经验动机材料及英文论文仍待另行完成，本冻结不为它们提供精度承诺。ZLS和ABM_JASSS不是Git仓库；本轮无提交或推送。
