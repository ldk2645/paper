# Version 3复现环境

在仓库根目录使用Python 3.11运行。依赖版本由根目录`requirements.txt`固定：NumPy 2.2.6、pandas 2.3.1、SciPy 1.17.0、matplotlib 3.10.6和Pillow 11.3.0。

推荐顺序：

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s 08_version3_response_dashboard/04_tests -v
python 08_version3_response_dashboard/02_experiment_code/run_v3_experiment.py --scope pilot --workers 4 --overwrite
python 08_version3_response_dashboard/02_experiment_code/analyze_v3_pilot.py --overwrite
python 08_version3_response_dashboard/02_experiment_code/build_v3_pilot_figure.py --overwrite
python 08_version3_response_dashboard/06_reproducibility/validate_v3.py
python 08_version3_response_dashboard/06_reproducibility/build_release_manifest_v3.py
```

最后两步不会执行10,500次正式设计。正式运行必须显式传入`--scope formal`，其成本和证据状态与pilot不同。

`v3_pilot_manifest.json`保存模型、父版本、运行器、时延数据及任务矩阵的哈希。`release_manifest_v3.csv`保存V3目录内发布文件的大小和SHA-256，并按惯例不自引用；Python缓存文件不会进入清单。
