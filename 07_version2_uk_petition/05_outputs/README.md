# 输出状态

`smoke/`包含15次执行链验证：5种回应时延条件 × 3个α（0.40、0.60、0.80） ×
1个随机种子（73000）。它只检查模型、事件日志以及固定/经验时延是否正常，
不能用于统计推断或论文结果报告。

烟雾输出包括：

- `v2_run_summaries.csv`：每次运行的汇总指标；
- `v2_event_log.csv`：请愿公开、越过门槛、回应排程、回应发布、100,000门槛和关闭事件；
- `v2_run_manifest.json`：模型、运行器、数据哈希，运行签名和软件环境。

正式设计已经完成。5,250次结果位于本目录下的`formal/`，复现命令为：

```powershell
python 07_version2_uk_petition/02_experiment_code/run_v2_experiment.py --scope formal --workers 8
python 07_version2_uk_petition/02_experiment_code/analyze_v2_formal.py
```

正式设计为5个时延条件 × 21个α × 50个共同随机种子。经验重抽样条件中，同一seed的
21个α固定使用同一个抽样时延。`formal/`包含原始运行汇总、事件日志、运行清单、描述统计、
配对比较、种子区组合并比较及Markdown结果报告。所有时延条件均有政府回应，因此结果不等于
“回应相对于不回应”的效应。
