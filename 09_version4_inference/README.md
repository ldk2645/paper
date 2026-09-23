# ABM：算法推荐下的公众偏好推断

当前版本 0.3.1（2026-09-24）。按用户要求重新实现，研究目标面向 JASSS 的解释性 ABM；当前交付是经过测试的研究代码和开发试验，不是已完成的投稿论文。旧文稿的数值与图表不能与本版本结果拼接。

## 从这里开始

- [研究计划](research_plan.md)：研究问题、实验阶段和投稿前缺口。
- [开发试验结果](diagnostic_report.md)：本次实际运行结果及其解释边界。
- [ODD 模型说明](ODD.md)：英文公式、时序和实现映射。
- [参数表](parameters.md)：代码默认值、试跑覆盖值及假设性质。
- `abm_jasss/model.py`：模型；`abm_jasss/cli.py`：批量运行、区间与图表。

## 运行

已验证环境：Windows、Python 3.12.14、NumPy 2.3.5。PowerShell 在此目录运行：

```powershell
.\run.ps1 -Mode test
.\run.ps1 -Mode pilot
.\run.ps1 -Mode suite -Workers 2
.\run.ps1 -Mode feedback -Workers 2
```

启动器优先使用本机已安装的 bundled Python，也可通过 `-PythonPath '完整的python.exe路径'` 指定环境。其他电脑先在独立 Python 环境安装 `python -m pip install -r requirements.txt`，然后运行：

```text
python -m unittest discover -s tests -v
python -m abm_jasss.cli --config configs/pilot.json --output outputs/my_new_run --workers 2
python scripts/run_pilot_suite.py --output outputs/my_new_suite --workers 2
```

输出目录必须为空或尚不存在，程序拒绝覆盖历史结果。`configs/main_candidate.json` 是尚未冻结的正式规模候选配置；本轮没有执行它。每个无反馈世界同时评价四种估计器，因此 11 个 α × 50 个种子是 550 个世界、2200 条估计器汇总；有反馈时每种策略分别生成世界。

## 结果如何追溯

每个实验目录包含 `manifest.json`（版本、环境、哈希、运行数量、耗时）、`source_snapshot`（实际源码）、`resolved_design.json`（完整参数和种子）、逐世界 JSON、`trajectories`、`runs.csv`、`aggregate.csv`、`paired_contrasts.csv`、SVG 和简报。失败写入 `failures.json`，不生成部分成功样本的聚合推断。

重跑历史版本时，把该次 `source_snapshot/abm_jasss` 复制到一个独立目录，在该目录使用 manifest 中的 specification 保存为 JSON 后运行模块；依赖版本也应与 manifest 一致。浮点结果跨平台不承诺逐字节相同。已测试本机串行与双进程输出一致。

本发布包包含 `outputs/diagnostics_v030_20260924`（8 个情景共 320 个世界）和 `outputs/feedback_v030_20260924`（36 个世界）。运行结果记录了生成时的模型版本；0.3.1 只增加历史源码溯源字段，仿真轨迹来自 0.3.0。

## 历史源代码审阅

原文对应仓库为 [ldk2645/paper](https://github.com/ldk2645/paper)。审阅时其 `release_qa.json` 的12项完整性检查均通过；仓库包含冻结 V1 模型、正式五条件消融数据、敏感性运行、外部数据表及完整图表溯源。它们值得作为历史证据保留。

V1 的议程外类别在初始化时固定，相关的“风暴”和“议程偏离”是相对预设议程的模型结果，并不直接测量模拟总体的真实偏好。信任更新和信任系数也是模型内机制，外部回归系数只是行为先验。故新版不复制旧模型输出或校准到旧阈值。可以借鉴的机制是政府按公开活动阈值排队、延迟并响应，以及风暴持续时间记录；研究计划把它们列为后续独立机制对照。新版每个新运行的 `manifest.json` 会带上 V1 模型哈希及历史来源说明，便于版本追溯。

## 当前范围与下一步

已实现平台观测、直接调查、固定权重融合、完美信息基准；可关闭的偏好漂移；两种排序；调查偏差和报告噪声；等人数平台面板；内容保护期；依赖估计的延迟政府发布。无反馈时估计器共享同一个世界，随机数按用途分流。

下一阶段先补历史样本校准的竞争性估计器、调查设计公平性和供给/人口尺度检验，再冻结主实验。当前曝光直接视为消费；调查无噪声基线直接读出抽中个体的模型偏好；固定平台面板与每轮重抽调查并非完全同构抽样；政府发布不是完整治理行动。这些均属于待检验假设。不能据此声称现实政策阈值、相变、不可逆性、公众福利或 JASSS 录用概率。
