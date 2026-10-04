"""Development diagnostics for the original governance question; not phase evidence."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from abm_jasss.cli import bootstrap_mean, write_csv


# Each override is explicit: no-response keeps routine publication;
# no-heat-control retains response scheduling and reply publication.
CASES = {
    "full": {},
    "no_emotion": {"emotion_advantage": 0.0, "official_emotion_mean": None},
    "no_topic_emotion": {"emotion_advantage": 0.0},
    "no_drift": {"drift_rate": 0.0},
    "no_response": {"response_enabled": False},
    "no_heat_control": {"response_heat_retention": 1.0},
    "no_trust_feedback": {"trust_feedback_strength": 0.0},
    "trust_alignment": {"trust_rule": "alignment"},
    "fast_response": {"government_delay": 1},
    "slow_response": {"government_delay": 10},
    "oracle_preferences": {},
    "softmax_ranking": {"ranking": "softmax"},
}
METRICS = ("mean_error", "agenda_attention_share", "agenda_gap", "agenda_shortfall", "attention_error",
           "preference_change", "storm_fraction", "trust_mean", "trust_spread", "responses_executed")


def read_rows(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def build_report(output):
    all_rows = []
    total, elapsed = 0, 0.0
    for name in CASES:
        all_rows.extend({"scenario": name, **r} for r in read_rows(output / name / "runs.csv"))
        meta = json.loads((output / name / "manifest.json").read_text())
        if meta["status"] != "complete":
            raise RuntimeError(f"Incomplete scenario: {name}")
        total += meta["successful_world_runs"]
        elapsed += meta["elapsed_seconds"]
    write_csv(output / "all_runs.csv", all_rows)
    lookup = {(r["scenario"], float(r["alpha"]), int(r["seed"])): r for r in all_rows}
    alphas = sorted({float(r["alpha"]) for r in all_rows})
    seeds = sorted({int(r["seed"]) for r in all_rows})
    rng = np.random.default_rng(90212)
    contrasts = []
    for case in list(CASES)[1:]:
        for alpha in alphas:
            for metric in METRICS:
                diff = [float(lookup[(case, alpha, s)][metric]) - float(lookup[("full", alpha, s)][metric]) for s in seeds]
                low, high = bootstrap_mean(diff, rng)
                contrasts.append({"scenario": case, "alpha": alpha, "metric": metric, "n_pairs": len(diff),
                                  "mean_difference": float(np.mean(diff)), "ci_low": low, "ci_high": high})
    write_csv(output / "paired_scenario_contrasts.csv", contrasts)
    lines = ["# 原创新主线恢复：开发试跑", "", "这是0.4.0合成模型的开发诊断，尚未检验相变、不可逆性或现实政策效果。", "",
             f"完成{total}个世界；各批次模型运行耗时合计{elapsed:.2f}秒，不含研究、测试及写作。每情景5个α、8个开发种子（301—308）；N=120、T=240、末80步汇总。", "",
             "恢复机制：情绪互动—算法放大—偏好漂移正反馈，阈值与延迟回应，以及信任—互动反馈。固定政府议程、公众潜在偏好、平台注意力分别记录。", "",
             "| 情景（α=0.75） | 政府议程曝光 | 注意力/偏好误差 | 偏好变化 | 信任均值 | 末窗超阈比例 | 回应执行数 |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for case in CASES:
        group = [lookup[(case, .75, s)] for s in seeds]
        values = [np.mean([float(r[k]) for r in group]) for k in
                  ("agenda_attention_share", "attention_error", "preference_change", "trust_mean", "storm_fraction", "responses_executed")]
        lines.append("| " + case + " | " + " | ".join(f"{v:.4f}" for v in values) + " |")
    lines.extend(["", "这里只展示预先在脚本指定的α=0.75切片作阅读入口，全部α和配对差异均已保存，不能将此切片当成临界点。",
                  "所有区间为种子层配对bootstrap的点态探索性区间（2000次重抽样，分析种子90212），没有多重比较校正。",
                  "no_emotion同时取消议题与来源的情绪分布差异，仍保留Beta情绪异质性及其互动作用；no_topic_emotion仅取消议题差异。这不是完整关闭情绪机制。",
                  "no_response关闭定向回应但保留日常发布；no_heat_control保留回应、发文，仅取消预设热度乘法。",
                  "no_trust_feedback只关闭信任到互动的反馈，信任状态仍更新；trust_alignment改用曝光与个体偏好匹配的规则，未沿用议程外曝光惩罚。",
                  "oracle_preferences只提供当期公众偏好，并不提供排序规则或控制平台的权力；它也没有与平台观察时延完全匹配，只是理想信息诊断，不是最优治理效果上界。",
                  "不同反馈世界可以出现不同公众偏好，所以误差改善不能直接解释为社会福利改善。",
                  "回应即时热度下降由参数规定；事件日志中的before/after只能核验动作，不能作为独立的治理有效性证据。",
                  "参考日常发布、回应触发、话题积压和事件删失日志解释后续传播结果。新模型没有学习成本方程，不是旧源码的数值复现。",
                  "", "尚待完成：两类透明度的独立操作化、行政/平台时标比、同状态下回应与算法架构干预、正反向扫描、长时段及规模检验、正式主实验。"])
    (output / "core_pilot_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "suite_manifest.json").write_text(json.dumps({"status": "complete", "world_runs": total,
        "cases": CASES, "analysis_seed": 90212, "analysis_type": "paired seed differences, pointwise percentile bootstrap",
        "scope": "development; no transition claim"}, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Use a new output directory")
    output.mkdir(parents=True, exist_ok=True)
    base = json.loads((ROOT / "configs/restored_core.json").read_text())
    for name, changes in CASES.items():
        spec = {**base, "model": {**base["model"], **changes},
                "arms": ["oracle" if name == "oracle_preferences" else "platform"]}
        config_path = output / f"{name}.json"
        config_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
        command = [sys.executable, "-m", "abm_jasss.cli", "--config", str(config_path),
                   "--output", str(output / name), "--workers", str(args.workers)]
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        (output / f"{name}.log").write_text(run.stdout + run.stderr, encoding="utf-8")
        if run.returncode:
            raise SystemExit(f"{name} failed; see its log")
        print(f"Completed {name}", flush=True)
    build_report(output)


if __name__ == "__main__":
    main()
