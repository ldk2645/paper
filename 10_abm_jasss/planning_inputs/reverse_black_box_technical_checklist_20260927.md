# 反向黑箱项目：正式实验前技术补充清单

版本：2026-09-27  
用途：发送给技术侧，作为正式实验冻结前的开发与识别任务清单。  
原则：**不再新增理论变量，优先补识别、记录、反事实与复现模块。**

---

## 一、P0：正式实验前必须完成

| 优先级 | 需要补的内容 | 技术实现要求 | 作用 |
|---|---|---|---|
| P0 | **政府感知模块 `government_sensing`** | 政府不能再直接复制当期曝光。单独生成 `P_true(t)`、`A_platform(t)`、`P_hat_gov(t)`。Baseline 只能根据过去若干窗口的公开热度/互动信号估计偏好，可设置窗口长度、平滑和观测噪声。 | 将 `P→A` 的平台表示失真与 `A→P_hat` 的政府感知误差真正拆开；这是“反向黑箱”能否在模型内成立的核心。 |
| P0 | **信息权限层 / 防 information leakage** | 给 government agent 设置明确 whitelist。Baseline 禁止读取 citizen preference、真实曝光概率、未来状态等隐藏字段；所有实验记录政府当轮实际可访问的信息字段。 | 防止模型在代码层“偷看真值”，保证感知误差具有识别意义。 |
| P0 | **双重遮蔽 2×2** | 两因素分别实现：① preference information：无/有；② algorithm information：不透明/透明。四格必须真实改变政府决策信息集，而不只是切换标签。 | 分别识别“看不到公众偏好”和“看不到平台排序机制”各自造成多少治理损失；不能再用 oracle 等同算法透明。 |
| P0 | **算法透明的实际决策规则** | 明确 transparency 后政府获得什么，例如排序公式+参数、历史曝光概率/日志；然后实现政府如何利用这些信息修正 `P_hat` 或选择回应。仅显示 α 不算 treatment。 | 让“算法透明”成为真正有治理后果的实验条件，而不是信息展示。 |
| P0 | **同状态分叉 `state_snapshot / fork`** | 在指定 \(t^*\) 完整保存系统状态，从完全相同 snapshot 复制多个分支；后续外生内容流尽量保持一致。 | 支持真正的反事实比较，避免“两个不同运行恰好结果不同”。 |
| P0 | **同状态干预组** | 从同一 snapshot 至少分出：No intervention、Better preference information、Faster response、Greater capacity、Ranking intervention；如保留 response strength 可另设一组。 | 直接回答“政府是看错了、来晚了，还是工具作用层级不对”，支撑 Structural Limits of Responsiveness。 |
| P0 | **三层核心 outcome** | 每 tick 保存：`TV(P,A)`、`TV(P,P_hat)`；回应阶段保存 `P_trigger`、`P_execution`、response target/resource vector。没有回应时不要强行归一化为 0。 | 分别测量 platform representation gap、government perception error、response mismatch，避免继续使用含混的“治理绩效”。 |

---

## 二、P1：正式设计冻结时完成

| 优先级 | 需要补的内容 | 技术实现要求 | 作用 |
|---|---|---|---|
| P1 | **回应结果拆成 targeting 与 timing 两部分** | 不建议只用一个 `TV(R,P)`。单独输出 `targeting_error`、`waiting_time`、`unmet_priority`、`execution_count`、未完成事件右删失标记。 | 区分“回应对象选错”和“对象没错但来晚了”，避免规范性过强。 |
| P1 | **触发时偏好 vs 执行时偏好** | 对每次 response 保存 `P_trigger` 与 `P_execution`，同时计算相对两者的目标错配。 | 观察行政延迟期间公众偏好已经发生多少移动；但不要把两者差值自动解释为 delay 的因果效应。 |
| P1 | **Zero-delay 时间顺序重新定义** | 如果正式需要 `delay=0`，必须明确同一 tick 中“观察→决策→发布→推荐→消费”的先后；当前 delay≥1 的逻辑不能简单把参数改成 0。 | 避免零延迟产生逻辑穿越；用于识别行政时滞本身。 |
| P1 | **随机数流拆分** | 至少分为 content generation、citizen behavior、government process、intervention 四类 RNG stream；记录每个 stream 的 seed。 | 不同机制改变函数调用次数后，单一相同整数 seed 并不保证面对相同外生冲击；提升 paired comparison 的可信度。 |
| P1 | **正式 Monte Carlo 精度模块** | Pilot 先估主 DV 的 run-to-run variance；依据预设 CI 半宽或 Monte Carlo SE 决定每格种子数，而不是固定 50。正式种子与开发种子分开。 | 防止按显著性补种子，也避免重复数不足或浪费计算。 |
| P1 | **路径依赖 / 恢复正式协议** | 支持细 α 网格、多初值、延长 T、不同 N；增加 forward/reverse continuation；恢复事件未完成时标记右删失。 | 只有满足这些条件才能讨论 nonlinear transition、hysteresis、path dependence；否则只能称 nonlinear amplification。 |
| P1 | **完整 heat-channel 对照** | `α=0` 只关闭排序中的 heat weight，不等于关闭热度通道。另实现 full heat-off，包括清理/热度反馈替代规则。 | 防止把 `α=0` 错写成“无算法/无热度反馈”。 |
| P1 | **信任降级并模块化** | `trust_feedback`、`trust_update` 分开开关；允许 frozen trust。主 DV 不依赖 trust 才能计算。 | 检验 trust 是反馈机制还是结果变量；如果效果弱可直接移附录，不拖住主论文。 |
| P1 | **正式运行 metadata** | 每个 world 保存 `run_id / code_version / config_hash / seed / scenario / α / N / T / initial_condition / treatment / snapshot_id`。 | 保证正式结果能完整追溯和复现。 |
| P1 | **关键 invariants / tests** | 增加测试：分布和为1；baseline 政府不能访问真值；四格信息权限正确；fork 起点完全相同；无漂移时 preference 固定；无回应仍保留常规政府发布等。 | 防止“代码跑通但实验含义错了”。 |

---

## 三、P2：投稿与复现阶段完成

| 优先级 | 需要补的内容 | 技术实现要求 | 作用 |
|---|---|---|---|
| P2 | **经验数据接口** | 导出与现实外部数据一致的 topic taxonomy、时间窗口，以及 `P/A` 聚合表；主结果支持 TV，同时可离线计算 JSD、Spearman、Top-k overlap。 | 方便第3章现实 `preference–attention divergence` 与模型指标使用相同口径。 |
| P2 | **一键复现管线** | formal config → batch simulation → raw outputs → aggregate statistics → figures/tables；正式运行后禁止手工修改中间结果。 | 最终用于复现包和投稿审计。 |

---

## 四、P0 完成后的 sanity batch

P0 完成后，不要直接大规模 formal run。先跑一个小规模 sanity batch，只确认以下三件事：

1. **`P→A→P_hat` 三层不再机械相等。**
2. **双重遮蔽 2×2 的信息条件确实改变 government decisions。**
3. **同一个 snapshot 的不同 intervention 可以从完全相同起点正确分叉。**

三项通过后，再冻结 formal design。

---

## 五、正式运行前需要冻结的内容

正式运行前建议冻结：

- 三个 primary outcomes 的精确定义；
- E2–E4 的 treatment matrix；
- Monte Carlo 精度标准与停止规则；
- 正式代码版本，例如 `v0.5.0-formal`；
- 正式 seed 清单；
- 主分析与 robustness 的分界；
- topic taxonomy 与外部经验数据口径。

正式版本冻结后，不允许因为结果“不理想”而修改主机制重新运行；新设定只能进入 robustness 或后续版本。

---

## 六、当前明确不要做的事项

1. **不要再加入新的 trust / learning-cost / digital-government 复杂方程。**
2. **不要为了重现旧稿而硬拟合 α≈0.55。**
3. **不要把当前 480 次 pilot 当作正式 Results。**
4. **不要把公众偏好 oracle 等同于算法透明。**
5. **不要把 α=0 写成“无算法”或“无热度反馈”。**
6. **不要把有限运行内未恢复写成“不可逆”。**
7. **不要把单条陡峭曲线直接写成“相变”。**
8. **不要把政府议程等同于公众真实需求或公共福利。**

---

## 七、技术侧完成后的交付物

技术侧完成本轮补充后，至少应交付：

- 更新后的代码版本；
- 更新后的 ODD；
- E2 双重遮蔽 2×2 配置表；
- E3 回应边界配置表；
- E4 同状态干预配置表；
- outcome 字典；
- information whitelist / permissions 文档；
- RNG stream 说明；
- unit / invariant tests 报告；
- sanity batch 报告；
- formal run 配置模板；
- metadata schema；
- reproducibility pipeline 说明。

---

## 八、项目目标

本轮不是增加模型复杂度，而是完成以下三个识别目标：

\[
	ext{Platform representation gap}
\]

\[
	ext{Government perception error}
\]

\[
	ext{Response misalignment}
\]

并通过双重遮蔽、同状态反事实和工具层级比较回答：

> 政府究竟是“看错了”“来晚了”，还是“手里的工具作用在错误的层级”？

这三类机制被干净地区分后，即可进入正式 Monte Carlo、外部经验数据分析和全文写作阶段。
