# 代码目录与执行顺序

## 当前补充材料入口

1. `run_formal_sensitivity.py`：运行19个S2新增条件，每个条件21个α×50个共同种子。
2. `analyze_formal_sensitivity.py`：合并完整模型与无有效回应参照，生成曲线、临界点、配对效应、效应量、95%区间和Holm校正结果。
3. `write_s2_report.py`：从处理后CSV直接生成完整S2，避免手工抄数。
4. `build_figure_s1_decay.py`：生成公开新闻24小时注意力衰减补充图。
5. `build_figure_s2_sensitivity.py`：生成正式敏感性补充图。

## 冻结历史入口

- `formal_ablation_frozen/`：保留原相对目录和字节级未改动的四条件、No-trust及五条件合并分析代码。
- `external_validation_frozen/`：公开数据下载、分析和证据表代码的字节级副本。
- `figure_generation_frozen/`：公开数据验证 Fig. 6 的字节级冻结绘图脚本；其他既有定量图保留逐图源数据和可编辑矢量成品。

冻结代码用于证明既有结果如何产生，不应为了适配新目录而直接改写。当前S2代码使用发布包内的清晰相对路径，并在原始CSV和清单中记录运行签名、模型哈希、配置JSON、随机种子和环境。
