# E2–E4 阶段发布说明（2026-10-04）

这是反向黑箱 ABM 的 **0.5.1-dev 已验收阶段成果**，不是论文已完成或可直接投稿的声明。当前目录对应本机 `ABM_JASSS` 的精选发布；旧版本在仓库原目录保留。先读本说明，再读项目的历史研究计划。

## 当前可以引用什么

- [执行验收](../formal_execution_acceptance_20261004.md)：1184 个区组、21312 个物理终点、1000 个独立种子，0 失败；279 项冻结前测试证据保留。
- [完整中文报告及六幅图](../outputs/formal_e2_e4_repaired_v2_20261004_report/report_zh.md)：102 项主分析均可推断，实际点态区间半宽均不超过 0.02；一次全 102 项 Holm 校正后 45 项拒绝，另有 532 行描述性辅助结果。
- [英文 Methods](../manuscript_work_20261004/methods_en.md) / [英文 Results](../manuscript_work_20261004/results_en.md)；[中文方法](../manuscript_methods_formal_20261004.md) / [中文结果](../manuscript_results_formal_20261004.md)。
- [当前交接](../project_handoff_20261004.md)与[证据对应表](../manuscript_work_20261004/results_evidence_map.md)：E5/E6、规模与时长稳健性、替代结构、经验材料和完整英文论文仍待完成。
- [论文形成过程报告总目录](../../paper_reports_20261004/README.md)：按七阶段整理的必要报告、正式表图和来源校验清单。

统计结论仅适用于登记模型、固定时窗和各对比共同有效支持。不能把本批结果解释为现实福利改善、跨 α 显著差异、相变、不可逆性或信任预警。3 项 pilot 预算风险和 61 项方差不稳定标记继续保留；它们不代表正式结果仍有精度不足。

## 发布范围与原始数据边界

[来源清单](source_selection.json)记录每份复制文件的源相对路径、字节数和 SHA256；[发布清单](package_manifest.json)覆盖本次全部交付文件（清单自身除外）。模型、冻结合同、登记包和历史证据按原字节复制。

**本仓库没有包含完整原始仿真档案。** 下列目录只包含根层 manifest、配置、记录表和原始清单，缺少逐世界 raw、轨迹、snapshot、derived 与组级目录：

- `outputs/formal_e2_e4_20261003/`（原失败批）；`outputs/formal_e2_e4_repaired_v2_20261004/`（成功恢复批）。
- `outputs/precision_pilot_20261002_initial/`、`outputs/precision_pilot_20261002_expansion/`。
- `outputs/research_s0_20260928_serial/`、`outputs/research_s0_20260928_parallel/`。
- `outputs/research_s1_20260929_serial/`、`outputs/research_s1_20260929_parallel/`。

这些目录中的 `artifact_hashes.json` 是完整原档案的索引；不能在本次部分副本上运行全量验收并预期通过。已归档验收报告记录本机完整批次实际执行过的检查，不是对 GitHub 部分副本的重新认证。完整原数据及两次中断恢复的文件继续保留在作者本机；当前没有公开数据下载地址或 DOI。投稿前仍需确定可访问的全量归档方案。

三个正式冻结登记包、正式 analysis/report、小型开发验收、pilot 规划和正式执行证据均完整保留。历史 0.3/0.4 说明与开发报告只供溯源；部分旧报告中的本机原稿、开发轨迹链接不在此次交付范围。[未随包提供的链接清单](unbundled_links.json)列出这些引用。

原始失败状态、浮点边界修复和恢复历史见[事件记录](../formal_execution_incident_20261003.md)。不存在根据结果追加样本或改写失败历史的操作。

## 检查交付与冻结设计

以下命令均在 `10_abm_jasss/` 执行。模拟环境为 Python 3.12.14、NumPy 2.3.5；安装到单独环境即可，勿用作图环境替换模拟环境。

```powershell
py -3.12 -m venv .venv-sim
.\.venv-sim\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-sim\Scripts\python.exe -B publication/verify_package.py
.\.venv-sim\Scripts\python.exe -B scripts/run_formal_study.py plan outputs/formal_registry_repair_v2_20261003
```

`verify_package.py` 只检查本次交付文件；`plan` 只检查冻结设计，两者都不运行仿真。完整仿真复现需要新建输出目录、大量磁盘空间及执行时间；入口为 `scripts/run_formal_study.py run`，参数与验收顺序见[正式协议](../formal_execution_protocol_20261003.md)。历史恢复启动脚本中含作者机器路径，只作为执行证据保存，不应直接在另一台机器启动。

如确需从头生成完整批次，以下示例使用原冻结种子和样本量，不给现有结果追加样本。每步成功后再执行下一步；示例路径须尚不存在。校验结果用 Python 显式保存为 UTF-8，避免 Windows PowerShell 5 的默认重定向编码导致 JSON 无法读取。

```powershell
.\.venv-sim\Scripts\python.exe -B scripts/run_formal_study.py run outputs/formal_registry_repair_v2_20261003 --output outputs/reproduction_batch --workers 3
.\.venv-sim\Scripts\python.exe -B -c "import pathlib,subprocess,sys; p=pathlib.Path('outputs/reproduction_validation.json'); assert not p.exists(); r=subprocess.run([sys.executable,'-B','scripts/run_formal_study.py','validate','outputs/reproduction_batch','--workers','3'],check=True,capture_output=True,text=True,encoding='utf-8'); p.write_text(r.stdout,encoding='utf-8')"
.\.venv-sim\Scripts\python.exe -B scripts/run_formal_study.py analyze outputs/reproduction_batch --output outputs/reproduction_analysis --validation outputs/reproduction_validation.json
```

成功后可把下一节绘图命令的分析输入换成 `outputs/reproduction_analysis`，使用另一全新报告目录。现有 Git 副本中的原始批目录不能充当这个从头生成的完整批次。

## 从已验收分析重建图表

正式生成器保留在 `outputs/formal_reporting_tools_20261003/report_formal_results.py`，与冻结模型分开。原生成记录采用 Python 3.12.14、Matplotlib 3.11.2、NumPy 2.5.3、Pillow 12.3.0；声明见[独立作图依赖](requirements-reporting.txt)，实际版本与字体哈希见 [reporting_manifest](../outputs/formal_e2_e4_repaired_v2_20261004_report/reporting_manifest.json)。不发布 vendor 安装目录或 Windows 字体文件。

```powershell
py -3.12 -m venv .venv-report
.\.venv-report\Scripts\python.exe -m pip install -r publication/requirements-reporting.txt
.\.venv-report\Scripts\python.exe -B outputs/formal_reporting_tools_20261003/report_formal_results.py outputs/formal_e2_e4_repaired_v2_20261004_analysis outputs/formal_registry_repair_v2_20261003 --output outputs/recreated_report
```

目标目录必须不存在。现有绘图代码要求 Windows 已安装微软雅黑、黑体或宋体之一；原图使用微软雅黑。更换字体/运行环境可能改变图件字节，已经保存的正式图表及其哈希保持不变。这里的依赖根据实际产物记录声明，本次未从网络重新安装或认证新环境。

## 本次上传前检查

当前没有需要修复的 E2–E4 模型或统计错误。本次仅补齐交付范围、图表环境和文件核验说明。已验收的冻结代码和研究合同未改，原有 279 项测试未重复运行；检查结果见[上传核验](upload_verification.json)。这份阶段发布不替代剩余论文研究和正式投稿前审查。
