# 独立精度 pilot 实测验收（2026-10-02）

**独立pilot的运行、只读语义验收及合并规划已完成。** 修复后212项测试通过，两批共1440条完整终点记录、0失败。正式研究尚未冻结：`formal_ready=false`。

本轮严格执行 [9月30日运行前登记](precision_pilot_protocol_20260930.md) 和 [完整配置](configs/precision_pilot_20260930.json)。引擎仍为0.5.1-dev，包源码哈希仍为 `67726e88836bbfc3c9cd8a6b214c48560ea46e637eac4c35573e3566fef332d1`。没有改模型方程、处理、目标精度、预算或种子；没有把历史开发世界加入pilot。

## 实际规模与验收

N=100、T=300，α=0.25/0.75；末窗200–299，分叉边界tick150。先运行seed61001–61020，再无条件运行61021–61040。两层共用seed形成区组配对，因此只有40个独立seed，不能把80个α×seed区组或1440条终点当成独立重复数。

| 项目 | initial | expansion |
|---|---:|---:|
| 独立seed | 20 | 20 |
| α×seed区组 | 40 | 40 |
| 完整终点记录 | 720 | 720 |
| 失败区组 | 0 | 0 |
| 核验的文件哈希 | 9546 | 9546 |
| 存档轨迹记录 | 216000 | 216000 |
| 原始产物与统计重建 | 通过 | 通过 |

每区组18条物理终点：E2四格、E4五分支、E3闭环五个额外条件及E3回放四条件。统计名册复用E2 I00作为E3闭环baseline，因此每区组19条统计臂；复用不增加样本。E4 B0与不中断I00一致，其前缀和存档轨迹记录也不增加独立信息。

只读验收检查：完整文件清单与哈希；manifest/config/源码快照；公开计数到源信号、窗口包及交付队列；政府合法感知与排期；分叉母状态、旧计划继承及共同供给；B0完整状态等价；回放供体及计划；世界汇总、配对名册、回放诊断和精度规划。验收不推进物理世界tick。

运行与检查使用3个工作进程。命令耗时：全量测试99.3秒，initial 422.1秒，expansion 408.5秒，两批验收分别364.0秒和459.2秒，合并分析4.1秒。环境为Python 3.12.14、NumPy 2.3.5。实际命令、返回码、完整日志及日志哈希见 [acceptance.json](outputs/precision_pilot_20261002_acceptance/acceptance.json)。

## 精度规划结果

每个α分别对17个对比的3个主指标规划，共102项。目标半宽h=0.02，最低30联合有效，每条件上限1000；每母世界先汇总，再构造配对差或四格交互，使用样本标准差及联合可测率Wilson95%下界。详细输入、逐母差值、支持模式和规划见 [合并报告](outputs/precision_pilot_20261002_planning/report.md) 与 [CSV](outputs/precision_pilot_20261002_planning/planning.csv)。

| 家族 | α | 未截断总数需求 | 预算内候选 | 预算状态 |
|---|---:|---:|---:|---|
| E2 | 0.25 | 33 | 33 | 可行 |
| E2 | 0.75 | 661 | 661 | 可行 |
| E3闭环 | 0.25 | 116 | 116 | 可行 |
| E3闭环 | 0.75 | 1293 | 1000 | 不足 |
| E3固定计划回放 | 0.25 | 33 | 33 | 可行 |
| E3固定计划回放 | 0.75 | 1002 | 1000 | 不足 |
| E4 | 0.25 | 184 | 184 | 可行 |
| E4 | 0.75 | 706 | 706 | 可行 |

跨家族共享需求为α=0.25时184、α=0.75时1293。前者由E4 B4−B0的主2决定，该项稳定；后者由E3闭环delay0−baseline的主1决定，该项不稳定。预算内候选数不等于已冻结正式n，也不代表自动达到精度。

**99/102项预算可行，3项超过1000：**

| α=0.75下的对比 | 指标 | 配对样本SD | 有效数需求 | 总数需求 | 方差相对变化20→40 |
|---|---|---:|---:|---:|---:|
| E3闭环delay0−baseline(delay3) | 主1公开表征差距 | 0.350339 | 1179 | 1293 | 32.60% |
| E3闭环delay0−baseline(delay3) | 主3触发目标错配 | 0.318821 | 977 | 1071 | 28.48% |
| E3回放delay3−delay0 | 主1公开表征差距 | 0.308388 | 914 | 1002 | 59.74% |

全部102项在合并pilot中均40/40联合可测，Wilson95%下界均为0.9123754607496077。仍按登记使用该下界调整样本量，没有把点估计100%当成未来必然全部可测。所有方差均可估、无零方差或不可规划项目。

**41/102项通过稳定性诊断，61项不稳定全部由方差相对变化超过25%导致。** α=0.25有25项不稳定，α=0.75有36项；联合支持变化超限为0，有效数不足30为0。稳定性是20对40的诊断，不能视为正式推断保证；低α的不稳定项中23项仍由最低有效数约束给出总n=33，也必须保留不稳定标记。完整诊断见 [stability.json](outputs/precision_pilot_20261002_planning/stability.json)。

40个seed的预算已达到，pilot停止。没有因这些结果追加、删除对比、改模型或查看显著性后调整设计。

## 运行前修复与验证证据

真实pilot开始前发现并修复以下脚本问题，均未修改冻结引擎：

1. 验收报告原先只绑定manifest。现绑定完整产物清单哈希；合并时复核全部当前文件，拒绝产物改变后的旧报告。验收开始与结束也核对清单未变化。
2. 原公开信号日志与轨迹未独立连接到发布器。现由存档聚合计数和已登记随机地址重建信号、窗口包、已交付/未交付队列，并核对轨迹的源信号及可用信号。
3. 合并时JSON列表与解析设计中的tuple直接比较，会拒绝合法批次。现统一JSON表示后比较。
4. 支持率变化恰好0.10可能因浮点舍入被判超标。阈值比较仅容忍绝对误差1e-12；登记的0.10和0.25阈值保持不变。

新增合并分析、重哈希变更、公开信号重建及浮点边界回归测试。全量测试由201项增加至212项，全部通过；见 [tests.log](outputs/precision_pilot_20261002_acceptance/tests.log)。此前单区组预检 `precision_preflight_20260930` 保留原样，不当作完整pilot批次。本轮另以非pilot种子60992验证300 tick规模可以正常运行，不加入统计样本。

## 产物、复现与后续

- 原始批次：[initial manifest](outputs/precision_pilot_20261002_initial/manifest.json)、[expansion manifest](outputs/precision_pilot_20261002_expansion/manifest.json)。raw JSON采用确定性gzip，各批保存完整源码/测试/协议快照。
- 语义验收：[initial](outputs/precision_pilot_20261002_acceptance/validate_initial.json)、[expansion](outputs/precision_pilot_20261002_acceptance/validate_expansion.json)。两份报告分别绑定对应manifest及整批文件清单。
- 分析溯源：[analysis_manifest.json](outputs/precision_pilot_20261002_planning/analysis_manifest.json)，`semantic_validation_complete=true`，`formal_ready=false`。
- 验收证据清单15个文件、合并分析清单5个文件另行只读复核通过。原始批次各9546个文件的完整检查由上述语义验收完成。

本轮实际入口（该前缀现已存在；复现时必须使用新的前缀）：

```powershell
python -B scripts/execute_precision_pilot.py --config configs/precision_pilot_20260930.json --prefix precision_pilot_20261002 --workers 3
```

已有批次的只读检查：

```powershell
python -B scripts/validate_precision_pilot.py outputs/precision_pilot_20261002_initial --workers 3
python -B scripts/validate_precision_pilot.py outputs/precision_pilot_20261002_expansion --workers 3
```

历史重建使用批次匹配的完整引擎及相关分析脚本。重跑同一seed用于复现，不增加样本；不要修改既有raw或覆盖分析目录。

下一步见 [正式冻结准备清单](formal_freeze_readiness_20261002.md) 与 [最新接续记录](project_handoff_20261002.md)。正式总n、预算取舍、区间/多重比较方法、新seed、完整配置与分析仍须冻结。本轮不提供正式政策效果结论，不覆盖动态转变、结构稳健性、信任预警、经验配对材料或英文论文。
