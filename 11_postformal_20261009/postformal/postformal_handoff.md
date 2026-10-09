# 后续工作接续记录（更新至2026-10-09）

原E2–E4正式研究已完成，原批次、102项推断及历史冻结证据保持不变。本次接续按10月4日方案推进估计器稳健性、No Drift、规模/时长及英国经验锚点；E5/E6继续暂缓。

## 模拟当前状态

协议、配置、完整运行/验收/分析/报告入口已经就绪。全套307项测试通过，含28项新增测试；独立开发seed920101的30个完整区组、246个物理终点全部通过只读重建。固定生产设计为15设定×2α×200母seed，合计6000区组、49,200物理终点，整个研究200个独立seed；设定内714项和效应变化648项分别作Holm校正。新seed为910001–910200，不并入旧正式样本。

历史及开发种子审计已通过：核查51,968个历史/源码文件和695个开发JSON，200个新seed无碰撞。独立登记包已经冻结并验证。生产编排于 **2026-10-08 20:52:42（Asia/Shanghai）** 启动，原主进程PID为 **29988**，3个worker，批次ID为 `postformal_98e9fc197e1b4c4a958215acc75fe2c6`。已于 **2026-10-09 11:31:24（Asia/Shanghai）** 完整通过运行、验收、分析和报告四阶段，最终 `acceptance.json` 与控制 `completion.json` 均为passed。进程已正常结束，不需为本批继续保持电脑运行。

登记manifest SHA256为 `0ae062e628c305a4aa801fe12a3bf3545a5259fb1828aa0d5908142651986790`。完整只读验收核查171,603个文件，重建15,420,000条轨迹记录和12,590,581条回应事件；6000区组、49,200物理终点，0操作失败。完整统计包含1362项主结果、3556行辅助描述。设定内714项均可估计且点态半宽≤0.05；648项效应变化中594项可估计，其中592项半宽达标。缺失区间、数值退化及精度不足应按表保留，不能把运行成功概括为所有结论都稳健。

当前下一步是解释全部新增结果并整合论文，以及继续经验数据可行性。模拟执行已完成，不重启、不追加seed。`readiness_20261008.json`是启动前的历史放行记录，其 `study_acceptance_complete=false` 不代表当前状态；当前完成依据为[最终acceptance](robustness/execution_20261008/acceptance.json)、[只读验收](robustness/execution_20261008/validation/validation.json)和[完整报告](robustness/execution_20261008/report/report.md)。

10月9日小产物独立复核通过：acceptance/validation/analysis/report绑定一致，分析4个文件及报告98个文件的清单和逐文件SHA256正确；报告包含48份PDF和48份PNG。54项未估计效应变化均为数值方差退化（200个配对有效、均值0），不是缺失或运行失败。两项半宽略超0.05的结果均为高α的E2交互及平台表征差距：grid6约0.051985、population200约0.050935；两者Holm调整p均为1。该复核未重复读取约50GB原始批次，完整原始重建以已绑定的validation为准。

| 用途 | 相对ABM_JASSS路径 |
|---|---|
| 执行协议 | `postformal/simulation/protocol_20261007.md` |
| 固定配置 | `postformal/robustness/configs/supplement_20261007.json` |
| 测试证据 | `postformal/simulation/development/tests_20261008/tests.json`、`tests.log` |
| 完整开发预检 | `postformal/simulation/development/preflight_v2_20261008/report.json` |
| 预算说明 | `postformal/robustness/budget_20261008.md` |
| 种子审计 | `postformal/robustness/seed_audit_20261008.json` |
| 独立登记包 | `postformal/robustness/registry_20261008/` |
| 生产控制回执/输出日志 | `postformal/robustness/launch_20261008/` |
| 生产编排及最终acceptance | `postformal/robustness/execution_20261008/` |

只读进度命令（在ABM_JASSS内执行）：

```text
python -B -m postformal.simulation.status postformal/robustness/execution_20261008
```

该命令现在返回passed及四阶段验收记录。完成依据为 `execution_20261008/acceptance.json` 及其绑定的批次、validation、analysis和report；主进程不存在是正常完成状态。若后续发现原始产物或绑定证据变化，先诊断并按协议重新验收，不覆盖旧目录启动新样本。

运行前估算原始批次47.4 GiB，3worker理想运行/验收约10.1小时；实际含授权、文件hash、统计和绘图的全流程约14小时39分钟。控制脚本已按固定名册完成运行→验收→分析→报告，没有追加或恢复。

后台启动采用Python隐藏子进程。两次PowerShell Start-Process尝试因环境中Path/PATH键重复在创建进程前失败，没有生成研究批次；实际唯一启动回执为 `launch_20261008/process_spawn.json` 和 `launch.json`。这不是登录计划任务，也未设置唤醒或系统重启恢复；现已正常结束，完成回执为同目录 `completion.json`。

## 本次修复和验证

- 修正新增测试入口，绑定测试日志、全体测试源码、物理模型和实际使用的共享脚本。
- 冻结并检查完整依赖快照、原正式来源身份、配置、seed、开发计时和Python/NumPy版本；缓存只复用设计解析，每次授权仍重哈希文件和检查当前源码。
- 补齐批次manifest、启动记录和逐组进度日志的身份/数量绑定；验收前后重查原始文件。
- No Drift核查个体期末及每tick总体偏好，拒绝截短向量、非有限值和均值不变但个体改变的记录。
- 独立测试配对共同支持、四格交互、效应变化、两个完整Holm族、缺失、退化、篡改拒绝和只读重建。
- 已验证报告绘图依赖和12份合成测试PDF/PNG。先加载NumPy2.3.5再追加现有绘图vendor，避免vendor中的另一个NumPy版本改变物理模型环境。

首次完整臂预检目录 `preflight_20261008/` 在补完冻结检查时主动停止，保留其开发记录。最终放行使用v2完整通过报告。合成绘图材料与开发原始世界都不是科学研究结果。

## 英国经验线

[可行性报告](empirical_anchor/processed/feasibility_20261008/report_zh.md)已生成，可由 `empirical_anchor/feasibility.py`重建。四议题×2018年前六个月得到24个调查值，样本量、访问日期、来源和原始字节哈希齐全，逐格复核通过。当前归档历史表包含2018-01至2023-10的67个月度行，范围内未列2020-03、2020-05、2020-08；这不等于确认这些月份没有调查。

经验配对值仍为0。已保留Trends首次请求HTTP429失败，未执行后续桥接或重复下载；共同尺度、Great Britain与查询英国范围的地理匹配、语义映射及噪声模型尚未验收。因此不冻结完整经验面板、不计算差距显著性、不把缺失填零。后续先解决合法数据导出及测量可比性，再冻结完整协议。

经验原始页面在10月7日补抓；首次网络失败和成功获取均保留。本轮未修改原论文的科学结论，也未上传远程仓库。

## 下一接续点

1. 固定批次全流程验收已经完成；无需继续运行或等待后台进程。
2. 核对并解释全部1362项主结果和3556行辅助描述，包括反向、不显著、支持不足与精度不足项，再更新论文；不要先挑结果。
3. 继续英国数字数据可行性和口径冻结；经验限制不阻止报告独立模拟结果。
4. 本批未发生生产中断；保留全部冻结、开发及完成记录，不覆盖或重新启动已验收批次。
