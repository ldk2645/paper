"""Build auditable development documentation from the saved version-0.3 outputs."""
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def read_csv(path):
    with path.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def main():
    suite = ROOT / 'outputs/diagnostics_v030_20260924'
    cases = ['baseline', 'no_emotion_advantage', 'reversed_emotion_advantage',
             'softmax_ranking', 'matched_panel', 'longer_cold_start',
             'biased_noisy_survey', 'preference_drift']
    names = ['基线', '无情绪优势', '反向情绪优势', '概率排序', '等人数平台面板',
             '保护期延长至5轮', '有偏且带噪声调查', '偏好漂移']
    directories = [suite / case for case in cases] + [ROOT / 'outputs/feedback_v030_20260924']
    total = 0
    elapsed = 0
    for directory in directories:
        manifest = json.loads((directory / 'manifest.json').read_text())
        assert manifest['status'] == 'complete' and manifest['failed_world_runs'] == 0
        assert manifest['model_version'] == '0.3.0'
        for name, expected in manifest['source_sha256'].items():
            assert hashlib.sha256((directory / 'source_snapshot/abm_jasss' / name).read_bytes()).hexdigest() == expected
        assert len(list((directory / 'trajectories').glob('*.csv'))) == manifest['successful_world_runs']
        total += manifest['successful_world_runs']
        elapsed += manifest['elapsed_seconds']
    lines = ['# 0.3.0 开发试验与验证记录', '', '日期：2026-09-24。以下全为合成仿真结果，不是经验数据或确认性主实验。', '',
             f'已核验 {total} 个世界全部成功，源码快照哈希与轨迹数量均匹配。9 个批次 manifest 中的耗时合计 {elapsed:.2f} 秒（双进程，本机；不含环境准备、汇总作图和研究分析时间，不是整个项目成本）。', '',
             '结构诊断：8个情景 × 5个α × 8个种子 = 320个无反馈世界；每个世界同时评价4个估计器。N=120，T=240，末80步平均；种子101—108。反馈检查：N=40，T=100，末30步，3个α × 3个种子 × 4种策略 = 36个世界，只检查路径可运行，不能据此证明治理效应。', '',
             '## 结构诊断', '', '表内是跨种子的平均总变差误差，越小越好。均匀基准为直接猜各议题等比例。这里展示α端点，全部5个水平和点态区间保存在各情景 aggregate.csv；配对区间在 paired_contrasts.csv。', '',
             '| 情景 | 平台 α=0 | 平台 α=1 | 调查 α=1 | 融合 α=1 | 均匀基准 α=1 |',
             '|---|---:|---:|---:|---:|---:|']
    for case, label in zip(cases, names):
        aggregate = read_csv(suite / case / 'aggregate.csv')
        lookup = {(float(r['alpha']), r['arm']): float(r['mean_error']) for r in aggregate}
        runs = read_csv(suite / case / 'runs.csv')
        uniform = statistics.mean(float(r['uniform_prior_error']) for r in runs if float(r['alpha']) == 1 and r['arm'] == 'platform')
        values = [lookup[(0, 'platform')], lookup[(1, 'platform')], lookup[(1, 'survey')], lookup[(1, 'fused')], uniform]
        lines.append('| ' + label + ' | ' + ' | '.join(f'{v:.4f}' for v in values) + ' |')
    lines += ['', '## 解释与下一步', '',
              '1. 当前基线中高热度权重对应较大误差，但取消情绪优势后仍存在误差，因而不能把情绪优势称为必要原因。需进一步分离冷启动、内容供给和有限注意力的作用。',
              '2. 固定一半权重融合会把有偏平台信号重新带入调查估计。融合不保证优于只用调查，下一步应加入历史样本校准的估计器，避免只与机械照抄活动份额比较。',
              '3. 均匀先验也是有竞争力的简单基准；正式比较必须保留。总体偏好在种子间变化，当前区间混合人口异质性和过程随机性；若要分别估计，应增加嵌套种子设计。',
              '4. 调查每轮重抽、平台面板固定，而且平台信号含历史窗口。等人数不是所有信息条件完全相同，不能据此直接宣称测量方式的纯因果效应。',
              '5. 偏好漂移同时改变推断目标；需联合报告相对初始和当期偏好的误差，不能把当前误差下降等同治理改善。',
              '6. 仅8个开发种子、短时窗和5个α，不支持相变阈值、不可逆性或精确现实政策建议。仍需规模/时长、供给密度、观察延迟、调查误差分别变化和替代消费规则检验。', '',
              '## 验证范围', '',
              '18项 unittest 已通过，覆盖归一化和手算更新、不同种子、无反馈测量隔离、全样本调查、延迟、内容保护期、排序和平分、源代码哈希、串行/并行一致及失败保存。测试通过说明已检查的实现性质成立，不证明模型是现实的正确描述。', '',
              '正式实验候选配置：configs/main_candidate.json。尚未执行或冻结；550个共享世界、2200条估计器汇总。先补竞争性估计器及必要设计检验，再冻结参数、分析规则与未使用种子。', '',
              '结果来源：outputs/diagnostics_v030_20260924/*/{manifest.json,runs.csv,aggregate.csv,paired_contrasts.csv}；反馈来源 outputs/feedback_v030_20260924。生成脚本：scripts/document_results.py。早期0.1版本结果不参与此报告。']
    (ROOT / 'diagnostic_report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    # This historical report must not replace the current model's parameter
    # register or formal design with the superseded measurement-only design.
    print(f'Validated {total} historical worlds; wrote diagnostic_report.md only')


if __name__ == '__main__':
    main()
