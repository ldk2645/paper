# 项目接续记录：2026-10-02

当前活跃目录为 `ABM_JASSS/`，模型引擎保持 `0.5.1-dev`。**独立精度 pilot 已完成运行、只读验收及合并规划；下一阶段是正式设计与分析冻结。** `formal_ready=false`。

## 本轮已完成

- 修复后全量测试 **212 项通过**。
- 按9月30日登记的 N=100、T=300、α=0.25/0.75、seed61001–61040 完成两批。共40个独立seed、80个α×seed区组、1440条完整终点记录，0失败。
- 两批各9546个文件哈希核验通过；公开信号生成/交付、政府合法感知/排期、母状态/分支/共同供给、固定计划回放、世界汇总、配对值及精度规划均只读重建通过。
- 生成102项规划及20→40稳定性诊断：99项预算可行，41项稳定；3项超过预算，61项不稳定。没有继续追加pilot。
- 仅修改运行/验收/分析脚本及测试。冻结引擎源码哈希仍为 `67726e88836bbfc3c9cd8a6b214c48560ea46e637eac4c35573e3566fef332d1`，历史批次未改写。

## 从这里继续

1. 阅读 [本轮验收报告](precision_pilot_validation_20261002.md) 和 [合并规划报告](outputs/precision_pilot_20261002_planning/report.md)。完整逐项值在同目录 `planning.csv`、`planning.json`、`stability.json`。
2. 按 [正式冻结准备清单](formal_freeze_readiness_20261002.md) 完成样本量/预算决定、区间方法、多重比较和主次顺序。α=0.25的跨家族需求为184；α=0.75为1293，超过登记上限1000。截断至1000不代表达到原半宽目标，且不能忽略61项不稳定。
3. 在新seed正式运行前冻结总n、完整配置/估计器/缺失/窗口/时序、分析与溯源清单。当前没有登记正式seed，没有启动正式批次。
4. E5动态转变/恢复、结构稳健性、E6信任预警留出验证、经验配对材料及英文论文仍未完成；本轮pilot没有为这些任务提供精度规划。

## 实际产物与入口

- `outputs/precision_pilot_20261002_initial/`：seed61001–61020，40区组、720终点。
- `outputs/precision_pilot_20261002_expansion/`：seed61021–61040，40区组、720终点。
- `outputs/precision_pilot_20261002_acceptance/`：完整命令、测试日志、两批语义验收、验收摘要及证据哈希。
- `outputs/precision_pilot_20261002_planning/`：合并规划、稳定性、CSV、报告和输入/代码哈希。
- `scripts/execute_precision_pilot.py`：执行测试→两批→只读验收→合并分析。已完成批次无需重新运行；任何复现须使用未存在的新输出前缀，不增加独立样本数。
- `scripts/validate_precision_pilot.py OUTPUT --workers 3`：只读验收；完整引擎和相关分析脚本须匹配批次快照。
- `scripts/analyze_precision_pilot.py INITIAL EXPANSION --output NEW --validation-initial REPORT --validation-expansion REPORT`：绑定两份当前有效验收报告，写入新分析目录。

S0种子51001–51003，S1种子52001、52002及参考1052004、1052005，pilot种子61001–61040均不能并入新正式样本。本轮运行规模预检另用非pilot种子60992；旧预检60991及测试夹具种子也属于开发用途。α层之间复用seed进行配对，B0与I00一致；它们不额外增加独立重复数。

本机实际环境为Python 3.12.14、NumPy 2.3.5。ZLS及ABM_JASSS不是Git仓库，本轮未提交或推送。9月27/29日接续文件保留为历史记录，最新状态以本文件为准。
