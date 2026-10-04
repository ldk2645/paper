# 正式结果报告生成器

此目录与冻结源码分开，仅整理已经验收、由正式入口发布的 `formal-analysis-1` 分析包。生成器不创建模型、不读取运行中raw、不修改输入、不重算检验、不补样。输出目录必须全新且不能位于输入目录内。

从项目根目录调用：

```powershell
& 'C:\Users\17003\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B outputs/formal_reporting_tools_20261003/report_formal_results.py outputs/<已验收分析目录> outputs/formal_registry_20261003 --output outputs/<全新报告目录>
```

门禁复核分析整包 `artifact_hashes.json`、`semantic_validation_complete=true`、`additional_sampling=false`、冻结登记及源/设计哈希、102项完整名册、CSV与推断JSON一致、固定样本数和父seed名册。复用项目现有只读registry校验；正式批次的raw语义验收仍由 `run_formal_study.py validate/analyze` 完成，本脚本不替代该验收。

输出：

- `primary_zh.csv`：全部102项中文主表，保留全部数值、支持计数、p数值下限、Holm和实际半宽标记，以及逐项pilot预算/方差提示。
- `auxiliary_zh.csv`：逐臂回应发生率、覆盖、等待等全部辅助描述，保留总数与有效数。
- 六组 `forest_alpha_*_primary_*.pdf/.svg/.png`：两层α×三个主指标，每图17项对比；同一指标共用轴范围。区间为点态95%CI，填充圆表示全102项Holm校正后拒绝。
- `summary.json`、`report_zh.md`：精度/支持汇总及完整102行摘要，保留3项pilot预算不足和61项方差不稳定说明。
- `reporting_manifest.json`：输入分析/冻结登记/批次/语义验收哈希、脚本哈希、绘图库/NumPy/Pillow/Python版本和中文字体哈希。
- `artifact_hashes.json`：报告产物清单。

`vendor` 是隔离绘图环境，由主代理安装；仅此生成器显式加入该路径。仿真及冻结研究代码继续使用原环境。字体使用Windows微软雅黑；Matplotlib缓存位于本目录。PDF/SVG为矢量，PNG为220dpi。

`check_reporting_fixture.py` 使用独立虚构数值，覆盖正常推断、联合有效不足、数值退化、无均值、输入/哈希篡改和旧目录保护。模拟registry仅用于测试门禁，没有生产跳过验证参数。夹具报告标题及manifest明确写明“合成夹具，非正式结果”。

```powershell
& 'C:\Users\17003\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B outputs/formal_reporting_tools_20261003/check_reporting_fixture.py --render-output outputs/formal_reporting_tools_20261003/<全新合成预览目录>
```

正式统计结果应始终解释为各对比共同可测母世界的条件配对差；四格交互、闭环、固定计划回放和分叉结果不能套用同一总体因果解释。主表保留各项支持缺失，辅助表补充逐臂回应与覆盖。
