# 已验收的结构稳健性与No Drift补充研究

2026-10-09 11:31（Asia/Shanghai），本批运行、只读验收、统计和报告四阶段全部通过。15个设定、两层α、每层200个新母seed，共6000区组、49,200个物理终点，0操作失败。整个补充研究只有200个独立seed；不同设定、α、分支和复用基线不增加独立样本数。

| 入口 | 内容 |
|---|---|
| [最终验收](postformal/robustness/execution_20261008/acceptance.json) | 四阶段通过和绑定身份 |
| [完整结果报告与图表](postformal/robustness/execution_20261008/report/report.md) | 48幅森林图，每幅PDF和PNG |
| [主结果表](postformal/robustness/execution_20261008/analysis/primary.csv) | 1362项处理差及效应变化，保留不可估计项 |
| [辅助表](postformal/robustness/execution_20261008/analysis/auxiliary.csv) | 3556行描述统计 |
| [冻结执行协议](postformal/robustness/registry_20261008/protocol.md) | 参数、种子、对比、支持、预算和停止规则 |
| [项目交接](postformal/postformal_handoff.md) | 已完成与待做事项 |
| [英国经验可行性](postformal/empirical_anchor/processed/feasibility_20261008/report_zh.md) | 24个调查开发值，数字配对尚未取得 |
| [发布范围和复核命令](publication/README.md) | 原始数据边界、依赖、统计重算和文件校验 |

设定内714项全部可估计，点态95%区间半宽全部≤0.05，378项经该族Holm校正拒绝。效应变化648项中594项可估计，156项经该族Holm拒绝；54项因样本方差数值退化而不提供区间/p值（200个配对有效、均值0），不是运行失败。其余594项中592项半宽达标，2项略超0.05。这两个Holm族分别控制，不与原E2–E4的102项族合并。

这些是看过主研究结果后登记的补充证据。完成验收不表示全部设定结论一致，也不能把“不显著变化”解释为等效或机制不重要。三项距离不是现实福利；没有检验相变、不可逆性或信任预警。E5/E6继续暂缓；全面结果解读和论文整合仍待完成。

本目录是精选发布，**不含约50GB的生产逐世界原始快照和轨迹**。完整统计记录、配对值、表图、验收记录和冻结源码已发布，可以复算统计；无法仅凭这个精选包重新进行完整原始轨迹重建。详见发布说明。旧[10月4日E2–E4发布](../10_abm_jasss/publication/README.md)原样保留，两个研究不拼接样本。
