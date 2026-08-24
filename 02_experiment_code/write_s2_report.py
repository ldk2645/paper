"""Generate the completed Supplementary Material S2 from formal outputs."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
PROCESSED = PACKAGE / "03_data" / "sensitivity" / "processed"
OUTPUT = PACKAGE / "05_documents" / "补充材料S2_敏感性分析.md"


PARAMETER_ROWS = (
    ("heat_decay_090", "热度保留率 λ", "0.90", "0.95"),
    ("heat_decay_085", "热度保留率 λ", "0.85", "0.95"),
    ("response_delay_5", "回应延迟 δ（步）", "5", "3"),
    ("response_delay_8", "回应延迟 δ（步）", "8", "3"),
    ("drift_rate_005", "偏好漂移速率 γ", "0.05", "0.03"),
    ("drift_rate_001", "偏好漂移速率 γ", "0.01", "0.03"),
    ("trust_update_012", "信任更新速率 τT", "0.12", "0.06"),
    ("trust_update_003", "信任更新速率 τT", "0.03", "0.06"),
    ("trust_feedback_050", "信任反馈强度 s", "0.50", "0.25"),
    ("trust_feedback_010", "信任反馈强度 s", "0.10", "0.25"),
    ("response_threshold_030", "回应阈值 θ", "0.30", "0.15"),
    ("response_threshold_010", "回应阈值 θ", "0.10", "0.15"),
    ("response_retention_090", "回应后热度保留率 ρ", "0.90", "0.70"),
    ("response_retention_050", "回应后热度保留率 ρ", "0.50", "0.70"),
)

ORDER_ROWS = (
    (
        "order_new_information_after_recommendation",
        "本步新信息在推荐与公众行动后生成",
        "只改变新信息首次进入推荐池的时点；下一步起可被推荐",
    ),
    (
        "order_government_action_at_end",
        "政府发布及到期回应移至每步末尾",
        "本步末执行的回应效果在下一步公众状态更新时进入系统",
    ),
    (
        "order_decay_before_recommendation",
        "热度衰减与清理提前至推荐前",
        "每步仍只衰减一次",
    ),
)

STRATEGY_ROWS = (
    ("baseline", "Hard（正式默认）", "超过阈值即排期；ρ=0.70"),
    ("strategy_selective", "Selective", "只对政府议程内议题排期"),
    ("strategy_wait", "Wait", "同一议题连续超过阈值3步后排期"),
    ("strategy_no_response", "无有效回应（消融参照）", "保留监测与计数，但ρ=1.00，热度不下降"),
)

METRIC_LABELS = {
    "mean_agenda_divergence": "议程偏离",
    "system_stability": "偏离度方差",
    "storm_time_share": "风暴时间占比",
    "mean_trust": "政府信任",
}


def critical_cell(row: pd.Series) -> str:
    if pd.isna(row["critical_alpha"]):
        return "未识别"
    return (
        f"{row['critical_alpha']:.2f} "
        f"[{row['critical_alpha_ci95_low']:.2f}, {row['critical_alpha_ci95_high']:.2f}]"
    )


def delta_cell(row: pd.Series) -> str:
    if pd.isna(row["critical_alpha_delta_vs_baseline"]):
        return "—"
    return (
        f"{row['critical_alpha_delta_vs_baseline']:+.2f} "
        f"[{row['critical_delta_ci95_low']:+.2f}, {row['critical_delta_ci95_high']:+.2f}]"
    )


def effect_cell(row: pd.Series) -> str:
    metric = row["metric"]
    if metric == "system_stability":
        return (
            f"{row['scenario_mean']:.2e}; Δ={row['mean_paired_difference']:+.2e} "
            f"[{row['difference_ci95_low']:+.2e}, {row['difference_ci95_high']:+.2e}]"
        )
    if metric == "mean_trust":
        return (
            f"{row['scenario_mean']:.3f}; Δ={row['mean_paired_difference']:+.4f} "
            f"[{row['difference_ci95_low']:+.4f}, {row['difference_ci95_high']:+.4f}]"
        )
    return (
        f"{row['scenario_mean']:.3f}; Δ={row['mean_paired_difference']:+.3f} "
        f"[{row['difference_ci95_low']:+.3f}, {row['difference_ci95_high']:+.3f}]"
    )


def baseline_cell(summary: pd.DataFrame, metric: str) -> str:
    row = summary[
        (summary["scenario_id"] == "baseline")
        & np.isclose(summary["alpha"], 0.60)
        & (summary["metric"] == metric)
    ].iloc[0]
    if metric == "system_stability":
        return f"{row['mean']:.2e} [{row['ci95_low']:.2e}, {row['ci95_high']:.2e}]"
    return f"{row['mean']:.3f} [{row['ci95_low']:.3f}, {row['ci95_high']:.3f}]"


def result_sentence(group: pd.DataFrame, label: str) -> str:
    identified = group[group["critical_alpha"].notna()]
    strong = group[group["identification_rate"] >= 0.95]
    if identified.empty:
        return f"{label}均未满足预设临界点识别条件。"
    low = identified["critical_alpha"].min()
    high = identified["critical_alpha"].max()
    shifted = group[
        (group["critical_delta_ci95_low"] > 0)
        | (group["critical_delta_ci95_high"] < 0)
    ]
    return (
        f"{label}中 {len(identified)}/{len(group)} 个点估计识别到临界点，"
        f"{len(strong)}/{len(group)} 个设定的 Bootstrap 识别率至少为95%；"
        f"点估计范围为 {low:.2f}–{high:.2f}。按共同种子配对 Bootstrap，"
        f"{len(shifted)}/{len(group)} 个设定的临界点位移95%区间不含0。"
    )


def main() -> int:
    critical = pd.read_csv(PROCESSED / "sensitivity_critical_points.csv")
    summary = pd.read_csv(PROCESSED / "sensitivity_curve_summary.csv")
    effects = pd.read_csv(PROCESSED / "sensitivity_effects_at_alpha_060.csv")
    auc = pd.read_csv(PROCESSED / "sensitivity_auc_effects.csv")
    by_id = critical.set_index("scenario_id")

    parameter_subset = critical[
        critical["scenario_id"].isin([row[0] for row in PARAMETER_ROWS])
    ]
    order_subset = critical[
        critical["scenario_id"].isin([row[0] for row in ORDER_ROWS])
    ]
    strategy_subset = critical[
        critical["scenario_id"].isin([row[0] for row in STRATEGY_ROWS])
    ]

    lines: list[str] = [
        "# 补充材料 S2：正式敏感性分析",
        "",
        "本材料检验参数取值、单步执行顺序和政府回应规则是否改变正式模型的主要结论。除已经完成的完整模型与无有效回应条件外，全部敏感性条件都使用同一份冻结核心模型，通过配置覆盖或运行器内的顺序子类实现；核心 `model.py` 没有改动。结果是模型内部稳健性证据，不是现实世界参数的置信区间。",
        "",
        "## S2.1 设计与统计口径",
        "",
        "每个条件均扫描 α=0.00, 0.05, …, 1.00 共21个水平，并在每个水平使用共同随机种子73000–73049重复50次；单次运行含300名公众和300步，主要汇总窗口为末100步。14个参数扰动、2个替代回应策略和3种执行顺序共新增19,950次模拟；再合并完整模型与无有效回应条件各1,050次，共22,050行分析输入。",
        "",
        "临界点以平均议程偏离曲线为对象：先做三点居中移动平均，再在内部 α 网格中取最大正梯度；曲线范围不足0.015或最大内部梯度不为正时不识别临界点。95%区间来自5,000次以种子整条 α 曲线为单位的区组 Bootstrap。相对于完整模型的临界点位移使用同一抽样索引进行配对 Bootstrap。α=0.60和跨 α 曲线面积（AUC）的结果均以共同种子配对；输出平均差、5,000次配对 Bootstrap 95%区间、Hedges gz、双侧 Wilcoxon 符号秩检验及各端点表内 Holm 校正 P 值。",
        "",
        "完整模型的临界点为 " + critical_cell(by_id.loc["baseline"]) + "。由于 α 网格间隔为0.05，点估计和区间只能落在该离散网格上。",
        "",
        "## S2.2 参数扰动",
        "",
        "表 S2-1 中 ρ 表示回应后仍保留的热度比例，因此ρ=0.90是较弱压制，ρ=0.50是较强压制；不能把ρ直接解释为‘压制强度’。",
        "",
        "| 扰动参数 | 扰动值 | 默认值 | αc [95%区间] | 相对完整模型位移 [95%区间] | Bootstrap识别率 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for scenario_id, label, value, default in PARAMETER_ROWS:
        row = by_id.loc[scenario_id]
        lines.append(
            f"| {label} | {value} | {default} | {critical_cell(row)} | "
            f"{delta_cell(row)} | {row['identification_rate']:.1%} |"
        )
    lines.extend(
        [
            "",
            result_sentence(parameter_subset, "14个参数扰动"),
            "完整的21点均值曲线、t区间、α=0.60配对效应和AUC配对效应分别见 `sensitivity_curve_summary.csv`、`sensitivity_effects_at_alpha_060.csv` 和 `sensitivity_auc_effects.csv`。因此正文不得只根据临界点范围概括所有结果；同一临界位置仍可能伴随崩塌深度、风暴占比或信任水平的变化。",
            "",
            "## S2.3 执行顺序敏感性",
            "",
            "正式顺序为：期初政府发布/执行到期回应→生成自发信息→平台推荐→公众消费、互动与偏好漂移→计算议程及风暴→政府监测并排期→更新学习成本与信任→记录→衰减清理。三个替代顺序每次只移动一个环节，其他参数和随机种子保持不变。",
            "",
            "| 替代顺序 | 实现边界 | αc [95%区间] | 位移 [95%区间] | 识别率 |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for scenario_id, label, note in ORDER_ROWS:
        row = by_id.loc[scenario_id]
        lines.append(
            f"| {label} | {note} | {critical_cell(row)} | {delta_cell(row)} | "
            f"{row['identification_rate']:.1%} |"
        )
    lines.extend(["", result_sentence(order_subset, "3种替代执行顺序"), ""])
    lines.extend(
        [
            "在α=0.60处，各顺序条件的绝对均值及相对完整模型的配对差如下；方括号是配对差的95% Bootstrap区间。`偏离度方差`越大表示波动越强，而不是系统更稳定。",
            "",
            "| 替代顺序 | 议程偏离 | 偏离度方差 | 风暴时间占比 | 政府信任 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for scenario_id, label, _ in ORDER_ROWS:
        cells = []
        for metric in METRIC_LABELS:
            row = effects[
                (effects["scenario_id"] == scenario_id)
                & (effects["metric"] == metric)
            ].iloc[0]
            cells.append(effect_cell(row))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    lines.extend(
        [
            "",
            "## S2.4 政府回应策略",
            "",
            "冻结代码内置 `hard`、`selective` 和 `wait` 三种回应策略。原模板中的‘自适应压制强度’没有对应的冻结实现；为了遵守不修改核心代码的要求，本次不编造自适应结果，而是正式比较三种已有策略，并将先前正式 `No response` 消融作为无有效回应参照。",
            "",
            "| 策略 | 操作 | αc [95%区间] | 位移 [95%区间] | 识别率 |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for scenario_id, label, note in STRATEGY_ROWS:
        row = by_id.loc[scenario_id]
        lines.append(
            f"| {label} | {note} | {critical_cell(row)} | {delta_cell(row)} | "
            f"{row['identification_rate']:.1%} |"
        )
    lines.extend(["", result_sentence(strategy_subset, "三种内置策略与无有效回应参照"), ""])
    lines.extend(
        [
            "α=0.60处的绝对均值与配对差如下。完整模型一行报告均值的95% t区间；其余行报告‘绝对均值；相对完整模型的配对差 [95% Bootstrap区间]’。",
            "",
            "| 策略 | 议程偏离 | 偏离度方差 | 风暴时间占比 | 政府信任 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for scenario_id, label, _ in STRATEGY_ROWS:
        if scenario_id == "baseline":
            cells = [baseline_cell(summary, metric) for metric in METRIC_LABELS]
        else:
            cells = []
            for metric in METRIC_LABELS:
                row = effects[
                    (effects["scenario_id"] == scenario_id)
                    & (effects["metric"] == metric)
                ].iloc[0]
                cells.append(effect_cell(row))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    effect_lookup = effects.set_index(["scenario_id", "metric"])
    selective_agenda = effect_lookup.loc[("strategy_selective", "mean_agenda_divergence")]
    selective_trust = effect_lookup.loc[("strategy_selective", "mean_trust")]
    wait_agenda = effect_lookup.loc[("strategy_wait", "mean_agenda_divergence")]
    wait_trust = effect_lookup.loc[("strategy_wait", "mean_trust")]
    no_response_agenda = effect_lookup.loc[("strategy_no_response", "mean_agenda_divergence")]
    no_response_trust = effect_lookup.loc[("strategy_no_response", "mean_trust")]
    decay_order_agenda = effect_lookup.loc[("order_decay_before_recommendation", "mean_agenda_divergence")]
    threshold_row = by_id.loc["response_threshold_030"]

    significant_at_alpha = effects[effects["p_holm"] < 0.05]
    significant_auc = auc[auc["p_holm"] < 0.05]
    lines.extend(
        [
            "",
            "## S2.5 结果解读与边界",
            "",
            f"参数层面，14个扰动的αc点估计落在0.55–0.65；只有将回应阈值由0.15提高到0.30时，临界点移至{threshold_row['critical_alpha']:.2f}，其配对位移区间为[{threshold_row['critical_delta_ci95_low']:+.2f}, {threshold_row['critical_delta_ci95_high']:+.2f}]。执行顺序层面，三个点估计为0.55–0.60，配对临界点位移区间均包含0；但把衰减提前到推荐前，在α=0.60处使议程偏离平均变化{decay_order_agenda['mean_paired_difference']:+.3f}，Bootstrap区间[{decay_order_agenda['difference_ci95_low']:+.3f}, {decay_order_agenda['difference_ci95_high']:+.3f}]，其Holm校正Wilcoxon P={decay_order_agenda['p_holm']:.3f}，应视为未通过多重校正的敏感性信号。",
            "",
            f"回应规则没有移动αc点估计，但明显改变α=0.60处的结果水平：Selective的议程偏离增加{selective_agenda['mean_paired_difference']:+.3f}、信任变化{selective_trust['mean_paired_difference']:+.4f}；Wait的议程偏离变化{wait_agenda['mean_paired_difference']:+.3f}、信任变化{wait_trust['mean_paired_difference']:+.4f}；无有效回应的议程偏离变化{no_response_agenda['mean_paired_difference']:+.3f}、信任变化{no_response_trust['mean_paired_difference']:+.4f}。这六项比较的Holm校正P均小于0.05。无有效回应降低了本指标定义下的平均议程偏离，却同时降低政府信任，因此原模板中的‘必然加深崩塌’不成立。",
            "",
            f"在全部非基准条件×4项指标中，α=0.60处共有 {len(significant_at_alpha)}/{len(effects)} 项比较的 Holm 校正 P<0.05；AUC比较共有 {len(significant_auc)}/{len(auc)} 项达到该阈值。显著性不能代替效应量和区间，完整数值以随附CSV为准。",
            "",
            "1. 临界点是否识别、临界位置、跃迁后水平和信任结果是不同问题。即使αc不移动，也不能据此声称政府回应或其他机制‘没有作用’。",
            "2. `No response`只令回应后的热度保留率为1.00；监测、排期和执行计数仍存在。其结果必须逐指标读取，不能预先写成‘崩塌必然加深’。",
            "3. 三种执行顺序是确定性的结构替代检验，不是对步骤做随机排列。顺序子类位于敏感性运行器中，冻结核心模型保持不变。",
            "4. λ=0.95与公开新闻20分钟衰减曲线的比较只是形状参照；模型时间步没有被校准为20分钟。",
            "5. 所有结论只适用于本研究的300人、300步、当前分布与阈值组合。公开数据验证约束了机制方向或数量级的合理性，但没有把这些过程参数估计成现实世界常数。",
            "",
            "## S2.6 复现文件",
            "",
            "- 原始新增运行：`03_data/sensitivity/raw/sensitivity_replicates.csv`；",
            "- 运行清单：`03_data/sensitivity/raw/sensitivity_manifest.json`；",
            "- 合并分析输入：`03_data/sensitivity/processed/sensitivity_combined_analysis_input.csv`；",
            "- 21点曲线汇总：`sensitivity_curve_summary.csv`；",
            "- 临界点与Bootstrap：`sensitivity_critical_points.csv`、`sensitivity_critical_bootstrap.csv`；",
            "- α=0.60配对结果：`sensitivity_effects_at_alpha_060.csv`；",
            "- AUC配对结果：`sensitivity_auc_effects.csv`；",
            "- 冻结核心模型：`01_model_core/model.py`；",
            "- 运行与分析代码：`02_experiment_code/run_formal_sensitivity.py`、`analyze_formal_sensitivity.py`。",
            "",
            "本材料中的表格由 `02_experiment_code/write_s2_report.py` 直接从处理后CSV生成，避免手工转录。",
        ]
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
