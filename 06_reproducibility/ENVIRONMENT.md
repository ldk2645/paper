# 复现环境与运行顺序

## 1. 本文件的范围

本说明区分两类环境：

1. **本次 S2 敏感性分析与补充图环境**：用于从冻结模型运行新增情景、分析结果、生成 S2 报告和补充图；
2. **历史正式消融环境**：用于解释仓库内已经发布的四条件与 `no_trust` 两阶段原始 CSV 是在什么软件版本下生成的。

顶层 `requirements.txt` 只锁定第一类环境。历史数据的环境信息来自其运行清单，不能用本次依赖锁文件反向改写。

## 2. 本次 S2 固定环境

本次新增流程以 CPython 3.11 为目标；正式运行清单记录的解释器为 Python 3.11.3。为减少数值库、统计函数和图形导出差异，顶层 `requirements.txt` 固定如下版本：

| 软件 | 固定版本 | 在本次流程中的用途 |
|---|---:|---|
| NumPy | 2.2.6 | 数值数组、随机数与汇总计算 |
| Pandas | 2.3.1 | 逐次运行 CSV、配对数据和结果表 |
| SciPy | 1.17.0 | 统计检验与分布函数 |
| Matplotlib | 3.10.6 | S1、S2 补充图及矢量/位图导出 |
| Pillow | 11.3.0 | Matplotlib 位图与 TIFF 输出支持 |

建议使用 64 位 CPython 3.11。Python 的补丁版本、操作系统、CPU/BLAS 实现和并行进程数仍可能影响运行时间，极少数浮点数末位也可能不同；正式比较应以统计量及其容差为准，而不是要求所有文本字节完全一致。

## 3. 历史正式消融的两阶段环境

历史四条件与后续 `no_trust` 增补并非在同一软件环境中生成。下表只列运行清单明确记录的项目；“未记录”不代表当时没有安装该软件。

| 阶段 | Python | NumPy | Pandas | 清单记录的平台 |
|---|---:|---:|---:|---|
| 历史四条件 | 3.12.13 | 2.3.5 | 3.0.1 | Windows 11 / 10.0.26200 |
| 历史 `no_trust` 增补 | 3.11.3 | 2.2.6 | 2.3.1 | Windows 10 / 10.0.26200 |
| 本次 S2 新增流程 | 3.11.3 | 2.2.6 | 2.3.1 | Windows 10 / 10.0.26200 |

SciPy、Matplotlib 和 Pillow 的历史版本未写入上述两份消融运行清单，因此不作推断。更完整的历史来源、文件哈希和阶段边界见 `06_reproducibility/FORMAL_ABLATION_PROVENANCE.md`。

`03_data/formal_ablation/raw/` 中的历史原始 CSV 是本仓库发布结果的一部分。它们应与清单和 SHA-256 记录一起用于审计。由于两个历史阶段的软件版本不同，即使使用相同种子，重新运行仍可能受到 Python、NumPy、Pandas 或底层数值实现差异的影响；不要仅因重跑文件与发布 CSV 未达到逐字节一致，就覆盖或删除已发布原始数据。若研究需要统一环境下的严格重跑，应在独立副本中完成全部条件，再与发布结果进行成组比较。

## 4. Windows PowerShell：建立本次 S2 环境

以下命令均从仓库根目录执行。`py -3.11` 需要本机已经安装 Python 3.11。

```powershell
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\requirements.txt
python -c "import sys, numpy, pandas, scipy, matplotlib, PIL; print(sys.version); print(numpy.__version__, pandas.__version__, scipy.__version__, matplotlib.__version__, PIL.__version__)"
```

最后一条命令应显示 Python 3.11，以及 `2.2.6 2.3.1 1.17.0 3.10.6 11.3.0`。如 `py` 启动器不可用，可将第一条创建环境的命令替换为本机 Python 3.11 可执行文件的绝对路径。

## 5. 运行敏感性实验

运行器从 `01_model_core/model.py` 载入冻结模型，并使用可续跑的原始结果文件。`--workers` 可按机器的内存和 CPU 核数调整；以下以 7 个进程为例。

```powershell
python .\02_experiment_code\run_formal_sensitivity.py --workers 7
```

主要输出：

- `03_data/sensitivity/raw/sensitivity_replicates.csv`
- `03_data/sensitivity/raw/sensitivity_manifest.json`

仓库已经包含发布版敏感性原始结果。若要检验从头运行，建议先复制整个仓库或建立独立工作目录，不要直接覆盖发布文件。

## 6. 分析并生成 S2 报告

敏感性分析还会读取 `03_data/formal_ablation/raw/formal_replicates_5conditions.csv` 中的基准与回应消融结果，因此必须保留该文件。

```powershell
python .\02_experiment_code\analyze_formal_sensitivity.py
python .\02_experiment_code\write_s2_report.py
```

分析表写入 `03_data/sensitivity/processed/`；完成后的 Markdown 报告写入 `05_documents/补充材料S2_敏感性分析.md`。

## 7. 生成补充图

S2 图读取敏感性处理结果；S1 衰减图读取外部验证处理数据。两者均会把源数据复制到对应的 `source_data` 目录，并导出投稿用的矢量和高分辨率位图格式。

```powershell
python .\02_experiment_code\build_figure_s2_sensitivity.py
python .\02_experiment_code\build_figure_s1_decay.py
```

两份图的默认输出均位于 `04_figures/supplementary/`，文件名用于区分 S1 与 S2；对应的绘图源数据分别写入 `03_data/external/source_data/` 和 `03_data/sensitivity/source_data/`。

如需改变输出位置，可使用两个绘图程序的 `--output-dir` 参数；S1 程序还支持 `--input`，S2 程序支持 `--processed-dir`。

## 8. 推荐的一次性执行顺序

建立并激活虚拟环境后，可按以下顺序完成全流程：

```powershell
python .\02_experiment_code\run_formal_sensitivity.py --workers 7
python .\02_experiment_code\analyze_formal_sensitivity.py
python .\02_experiment_code\write_s2_report.py
python .\02_experiment_code\build_figure_s2_sensitivity.py
python .\02_experiment_code\build_figure_s1_decay.py
```

复核时至少检查：运行清单中的模型哈希与场景数、原始 CSV 的主键唯一性和每个单元的重复数、处理表是否完整生成，以及 PDF/SVG/PNG/TIFF 是否均能打开。正式发布文件不应因一次试运行失败或软件环境不一致而被替换。
