# 2026-10-09 GitHub发布范围与复核

本目录发布已完成的估计器稳健性、No Drift、规模/时长补充研究。全流程完成于2026-10-09 11:31:24（Asia/Shanghai），运行、只读验收、分析和报告均passed。原E2–E4、历史发布目录及其冻结代码没有修改。

## 包含的材料

- 当前物理模型、共享运行/统计代码、全部307项测试源码、配置和合同文档。
- 完整补充登记包：配置、6000组名册、协议、源码/测试快照、种子审计、测试日志、完整开发预检报告及文件哈希。
- 完整validation、analysis和report：逐母统计记录、配对值、1362行主表、3556行辅助表、48 PDF及48 PNG。
- 原始生产批的4个根层文件：launch、manifest、progress.jsonl及全原始文件清单；这些不能代替未提供的原始世界。
- 开发计时/测试证据，以及完整预检的配置、报告和原始清单；预检逐世界原始产物未提供。
- 英国经验开发协议、代码、调查表、公开网页字节和来源元数据。仅24个调查值，Trends配对为0，未计算经验差距或噪声显著性。
- 为原样运行测试保留的小型历史夹具，包括旧登记包、pilot规划/验收、两波pilot的7个根文件、S0/S1验收及数值故障诊断快照。

[source_selection.json](source_selection.json)逐文件记录本机来源、原始/发布SHA256和复制方式；[package_manifest.json](package_manifest.json)绑定最终发布文件集合。复制的冻结模型、登记与科学结果保持原始字节。

## 缺少的原始数据

本包没有生产batch的 `raw/`、`derived/`、`groups/`、`initial_arrays/`、`mother_snapshots/`、`diagnostics/`，也没有开发预检的逐组原始世界。完整原始批约50GB，仍保留在作者本机，当前没有公开下载地址或DOI。

这些部分目录中的 `artifact_hashes.json` 描述完整本机原档案，不能在精选副本上运行全量库存/轨迹验收并期待通过。历史验收报告记录本机已实际完成的检查；本次发布校验只认证公开文件和统计重算，不能取代原始世界重建。

完整种子审计涉及51,968份历史/源码文件和695份开发JSON，并非全部随包提供。本包可核对归档审计身份，不能重新生成完全相同的全历史审计。原始数据公开归档仍是投稿前的待做工作。

## 发布副本的响应头处理

公开页面的响应体保持原字节。经验下载元数据里包含Cookie等HTTP头，只在发布副本中移除了这些头；没有改动本机原文件、页面正文、调查值或查询协议。[redaction_manifest.json](redaction_manifest.json)记录每份变更的原始/发布哈希及被移除字段路径，不包含被移除的值。元数据容器的原哈希与发布哈希因此不同，不能混用。

原验证/运行证据内的作者Windows路径作为来源信息保留。路径映射是本机 `ABM_JASSS/` 对应本目录 `11_postformal_20261009/`。这些绝对路径不是下载地址。`launch_20261008.py`引用本机绘图vendor，仅作为历史启动证据保存；跨机器使用下面通用命令，不直接调用该启动包装器。

## 不运行研究世界的复核

冻结环境为 **Python 3.12.14、NumPy 2.3.5**；登记检查会严格检查两者。先创建匹配的独立环境，以下命令在 `11_postformal_20261009/` 执行：

```text
python -m pip install -r requirements.txt
python -B publication/verify_release.py
python -B -m postformal.simulation.run plan postformal/robustness/registry_20261008
```

`verify_release.py`检查交付文件集合及SHA256、冻结登记、验收/分析/报告绑定和对应小产物清单，并从 `validation/records.json.gz` 原样重算全部主表、辅助表和配对值。它不创建/推进物理模型，不访问未提供的生产raw，不写入既有结果。上述重算不能独立核实输入记录本身是否忠实于未公开原始轨迹。

全套测试使用独立小型夹具和临时目录，会运行小型开发世界，但不重新执行6000组研究：

```text
python -B -m unittest discover -s tests -v
```

研究运行前的307项测试证据在冻结登记中保持不变；本次发布目录的搬迁复测结果另存 `publication/release_tests.json` 和 `release_tests.log`。

## 图表与完整重跑

图表已经提供，无需安装绘图依赖即可阅读。重新绘图可在保留NumPy2.3.5的独立环境安装 [requirements-reporting.txt](requirements-reporting.txt)，然后执行：

```text
python -m pip install -r publication/requirements-reporting.txt
python -B -c "from postformal.simulation.report import build_report; build_report('postformal/robustness/execution_20261008/analysis', 'postformal/robustness/recreated_report')"
```

新输出目录必须不存在；不同图形依赖、平台或字体可能改变图片字节，不改变已有表格和配对值。依赖版本取自已使用的绘图环境，本次发布不重新下载安装或认证另一平台环境。

需要从头生成全量原始世界时，确认磁盘和时间预算后，使用冻结名册和一个全新目录（不是给原研究追加样本）：

```text
python -B -m postformal.simulation.run pipeline postformal/robustness/registry_20261008 postformal/robustness/reproduction_new --workers 3
```

该命令会运行完整6000区组并依次验收、分析、出图；须预先安装绘图依赖。原批全流程约14小时39分钟，机器差异可能很大。冻结登记要求活源码、测试及环境匹配；不应通过修改冻结包去跳过检查。直接对本次精选原batch调用 `validate` 或 `build_analysis` 会因缺少raw而失败，应使用上述纯统计复核或完整重跑。

## 科学范围

设定内714项和效应变化648项是两个独立Holm族。54项效应变化方差退化而无区间/p；两项半宽略超0.05，均按原规则保留。不得因未达精度或不显著追加seed，也不能将运行验收成功解释为所有结论稳健。

经验数据目前只有调查侧开发切片。地理范围、跨查询共同尺度、语义映射和噪声模型均未冻结；无经验因果结论。论文整合、经验配对和全量数据公开归档仍待推进。
