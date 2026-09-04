"""Analyze the completed Version 2 formal delay experiment.

The unit of replication is the common random seed.  Delay conditions are
paired within seed and alpha.  The script writes descriptive statistics,
alpha-specific paired contrasts, seed-block pooled contrasts, and a Markdown
report.  It does not modify the model or the raw formal outputs.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


HERE = Path(__file__).resolve().parent
V2_ROOT = HERE.parent
FORMAL_DIR = V2_ROOT / "05_outputs" / "formal"
SUMMARY_PATH = FORMAL_DIR / "v2_run_summaries.csv"

REFERENCE = "case_typical_22"
CONDITION_LABELS = {
    "v1_reference_3": "3天理论参照",
    "conditional_p05_11": "11天条件样本P5",
    "case_typical_22": "22天案例/条件样本中位数",
    "conditional_p95_57": "57天条件样本P95",
    "conditional_empirical_resample": "经验时延重抽样",
}
OUTCOMES = {
    "mean_trust": "末100步平均政府信任",
    "mean_learning_cost": "末100步平均学习成本",
    "mean_agenda_divergence": "末100步平均议程偏离",
    "mean_agenda_share": "末100步平均议程占比",
    "mean_official_attention_share": "末100步平均官方注意力占比",
    "total_interactions": "全程互动总量",
    "petition_heat_auc_post_7_days": "回应后7天请愿热度AUC",
}


def _mean_ci(values: np.ndarray) -> tuple[float, float, float, float]:
    values = np.asarray(values, dtype=float)
    n = len(values)
    mean = float(np.mean(values))
    sd = float(np.std(values, ddof=1)) if n > 1 else math.nan
    if n <= 1 or not np.isfinite(sd):
        return mean, sd, math.nan, math.nan
    half_width = float(stats.t.ppf(0.975, n - 1) * sd / math.sqrt(n))
    return mean, sd, mean - half_width, mean + half_width


def _paired_statistics(differences: np.ndarray) -> dict[str, float | int]:
    differences = np.asarray(differences, dtype=float)
    n = len(differences)
    mean, sd, ci_low, ci_high = _mean_ci(differences)
    if np.allclose(differences, 0.0, rtol=0.0, atol=1e-15):
        t_p = 1.0
        wilcoxon_p = 1.0
        hedges_gz = 0.0
    else:
        t_p = float(stats.ttest_1samp(differences, 0.0).pvalue)
        wilcoxon_p = float(
            stats.wilcoxon(
                differences,
                zero_method="wilcox",
                alternative="two-sided",
            ).pvalue
        )
        if sd == 0.0:
            hedges_gz = math.copysign(math.inf, mean)
        else:
            correction = 1.0 - 3.0 / (4.0 * n - 5.0)
            hedges_gz = float(correction * mean / sd)
    return {
        "n_seed_blocks": n,
        "mean_difference": mean,
        "sd_difference": sd,
        "ci95_low": ci_low,
        "ci95_high": ci_high,
        "paired_t_p": t_p,
        "wilcoxon_p": wilcoxon_p,
        "hedges_gz": hedges_gz,
    }


def _holm(values: pd.Series) -> pd.Series:
    raw = values.to_numpy(dtype=float)
    order = np.argsort(raw)
    adjusted = np.empty_like(raw)
    running = 0.0
    m = len(raw)
    for rank, index in enumerate(order):
        candidate = (m - rank) * raw[index]
        running = max(running, candidate)
        adjusted[index] = min(1.0, running)
    return pd.Series(adjusted, index=values.index)


def _validate_panel(frame: pd.DataFrame) -> None:
    required = {"condition_id", "alpha", "seed", *OUTCOMES}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"formal summary is missing columns: {missing}")
    key = ["condition_id", "alpha", "seed"]
    cell_sizes = frame.groupby(["condition_id", "alpha"]).size()
    if (
        len(frame) != 5_250
        or frame["condition_id"].nunique() != 5
        or frame["alpha"].nunique() != 21
        or frame["seed"].nunique() != 50
        or frame.duplicated(key).any()
        or not cell_sizes.eq(50).all()
    ):
        raise ValueError("formal panel is not the declared 5 x 21 x 50 design")


def build_descriptive(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    for (condition, alpha), group in frame.groupby(["condition_id", "alpha"]):
        for outcome, label in OUTCOMES.items():
            mean, sd, ci_low, ci_high = _mean_ci(group[outcome].to_numpy())
            rows.append(
                {
                    "condition_id": condition,
                    "condition_label": CONDITION_LABELS[condition],
                    "alpha": float(alpha),
                    "outcome": outcome,
                    "outcome_label": label,
                    "n": len(group),
                    "mean": mean,
                    "sd": sd,
                    "ci95_low": ci_low,
                    "ci95_high": ci_high,
                }
            )
    return pd.DataFrame(rows).sort_values(["outcome", "condition_id", "alpha"])


def build_alpha_specific_contrasts(frame: pd.DataFrame) -> pd.DataFrame:
    reference = frame[frame["condition_id"].eq(REFERENCE)]
    rows: list[dict[str, float | int | str]] = []
    for condition in CONDITION_LABELS:
        if condition == REFERENCE:
            continue
        comparator = frame[frame["condition_id"].eq(condition)]
        for alpha in sorted(frame["alpha"].unique()):
            left = comparator[comparator["alpha"].eq(alpha)].set_index("seed")
            right = reference[reference["alpha"].eq(alpha)].set_index("seed")
            if not left.index.equals(right.index):
                raise ValueError("paired seed indices do not align")
            for outcome, label in OUTCOMES.items():
                differences = left[outcome].to_numpy() - right[outcome].to_numpy()
                reference_mean = float(right[outcome].mean())
                row = {
                    "condition_id": condition,
                    "condition_label": CONDITION_LABELS[condition],
                    "reference_condition_id": REFERENCE,
                    "alpha": float(alpha),
                    "outcome": outcome,
                    "outcome_label": label,
                    "reference_mean": reference_mean,
                    "percent_difference_vs_reference": (
                        float(np.mean(differences)) / reference_mean * 100.0
                        if reference_mean != 0.0
                        else math.nan
                    ),
                    **_paired_statistics(differences),
                }
                rows.append(row)
    result = pd.DataFrame(rows)
    result["paired_t_p_holm_21alpha"] = result.groupby(
        ["condition_id", "outcome"], group_keys=False
    )["paired_t_p"].apply(_holm)
    result["wilcoxon_p_holm_21alpha"] = result.groupby(
        ["condition_id", "outcome"], group_keys=False
    )["wilcoxon_p"].apply(_holm)
    return result.sort_values(["outcome", "condition_id", "alpha"])


def build_pooled_contrasts(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    reference = frame[frame["condition_id"].eq(REFERENCE)]
    for condition in CONDITION_LABELS:
        if condition == REFERENCE:
            continue
        comparator = frame[frame["condition_id"].eq(condition)]
        for outcome, label in OUTCOMES.items():
            left = comparator.pivot(index="seed", columns="alpha", values=outcome)
            right = reference.pivot(index="seed", columns="alpha", values=outcome)
            if not left.index.equals(right.index) or not left.columns.equals(right.columns):
                raise ValueError("seed-by-alpha blocks do not align")
            seed_block_differences = (left - right).mean(axis=1).to_numpy()
            reference_mean = float(right.to_numpy().mean())
            rows.append(
                {
                    "condition_id": condition,
                    "condition_label": CONDITION_LABELS[condition],
                    "reference_condition_id": REFERENCE,
                    "outcome": outcome,
                    "outcome_label": label,
                    "reference_mean": reference_mean,
                    "percent_difference_vs_reference": (
                        float(np.mean(seed_block_differences)) / reference_mean * 100.0
                        if reference_mean != 0.0
                        else math.nan
                    ),
                    **_paired_statistics(seed_block_differences),
                }
            )
    result = pd.DataFrame(rows)
    result["paired_t_p_holm_7outcomes"] = result.groupby(
        "condition_id", group_keys=False
    )["paired_t_p"].apply(_holm)
    result["wilcoxon_p_holm_7outcomes"] = result.groupby(
        "condition_id", group_keys=False
    )["wilcoxon_p"].apply(_holm)
    return result.sort_values(["outcome", "condition_id"])


def _fmt(value: float, digits: int = 5) -> str:
    if not np.isfinite(value):
        return "NA"
    return f"{value:.{digits}g}"


def write_report(
    frame: pd.DataFrame,
    descriptive: pd.DataFrame,
    alpha_specific: pd.DataFrame,
    pooled: pd.DataFrame,
) -> None:
    selected_alphas = {0.0, 0.25, 0.5, 0.75, 1.0}
    trust_curve = descriptive[
        descriptive["condition_id"].eq(REFERENCE)
        & descriptive["outcome"].eq("mean_trust")
        & descriptive["alpha"].isin(selected_alphas)
    ]
    primary = pooled[pooled["outcome"].eq("mean_trust")]
    significant_cells = int(
        (
            alpha_specific["paired_t_p_holm_21alpha"] < 0.05
        ).sum()
    )
    empirical = frame[
        frame["condition_id"].eq("conditional_empirical_resample")
    ].drop_duplicates("seed")

    lines = [
        "# Version 2正式实验结果",
        "",
        "## 实验设计与完成状态",
        "",
        "正式面板已完成5,250次运行：5种回应时延、21个alpha（0.00至1.00，"
        "步长0.05）和50个共同随机种子（73000—73049）。每次运行包含300名"
        "公众智能体和300个日步长；原始事件日志共31,500条制度事件。",
        "",
        "222条请愿时延样本以已经获得回应为条件，不能代表全部请愿。在正式实验的"
        f"经验重抽样组中，50个种子对应的抽样时延范围为"
        f"{int(empirical['response_delay_days'].min())}—"
        f"{int(empirical['response_delay_days'].max())}天；同一种子在全部alpha下"
        "固定使用同一抽样时延。",
        "",
        "## 识别边界",
        "",
        "五组条件均会发布一次政府回应，只改变回应时延；所有运行的回应热度乘数"
        "均为1.00，直接信任信号均为0.00。因此，本实验识别的是模型内部的回应"
        "时点差异，不是“回应相对于不回应”的效应，也不是现实因果效应或请愿"
        "获得回应的概率。",
        "",
        "## 主要指标：末100步平均政府信任",
        "",
        "合并比较先在每个种子内对21个alpha的配对差取平均，仍以随机种子作为"
        "重复单位。正值表示相应时延组的信任高于22天参照组。",
        "",
        "| 相对22天参照的时延条件 | 平均差 | 95%置信区间 | Hedges gz | "
        "Holm校正p值 |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in primary.itertuples(index=False):
        lines.append(
            f"| {row.condition_label} | {_fmt(row.mean_difference)} | "
            f"[{_fmt(row.ci95_low)}, {_fmt(row.ci95_high)}] | "
            f"{_fmt(row.hedges_gz)} | "
            f"{_fmt(row.paired_t_p_holm_7outcomes)} |"
        )

    lines.extend(
        [
            "",
        "## 22天参照组中不同alpha的信任水平",
        "",
        "| Alpha | 平均信任 | 95%置信区间 |",
            "|---:|---:|---:|",
        ]
    )
    for row in trust_curve.itertuples(index=False):
        lines.append(
            f"| {row.alpha:.2f} | {_fmt(row.mean)} | "
            f"[{_fmt(row.ci95_low)}, {_fmt(row.ci95_high)}] |"
        )

    lines.extend(
        [
            "",
            "## 多重比较与主要结论",
            "",
            f"在全部{len(alpha_specific)}个按alpha分层的时延比较中，"
            f"{significant_cells}个配对t检验在每个“时延×指标”的21次alpha检验内"
            "经过Holm校正后仍低于0.05。这63项全部来自回应后7天请愿热度AUC；"
            "其他六项较持久或全程指标均没有校正后显著单元。结果反映模型蒙特卡洛"
            "变异，不是现实总体抽样误差。",
            "",
            "回应后7天请愿热度AUC以各组自身的回应日对齐，可描述回应附近的局部"
            "模型轨迹，但比较同时包含日历时点变化与回应信息进入系统的影响，不能"
            "解释为独立的降温因果效应。主要信任指标的四项合并比较在七指标Holm"
            "校正后均不显著，说明本设定下没有稳健的长期信任时延效应证据。",
            "",
            "## 输出文件",
            "",
            "- `v2_run_summaries.csv`：每次正式运行一行。",
            "- `v2_event_log.csv`：每次运行六条制度事件。",
            "- `v2_run_manifest.json`：运行哈希、签名、环境及完成状态。",
            "- `v2_formal_descriptive.csv`：条件×alpha描述统计及95% t区间。",
            "- `v2_formal_paired_vs_typical22.csv`：按alpha的配对比较、配对t检验、"
            "Wilcoxon敏感性检验、Hedges gz及Holm校正。",
            "- `v2_formal_pooled_delay_effects.csv`：以种子为区组的合并时延比较。",
            "",
        ]
    )
    (FORMAL_DIR / "V2_FORMAL_RESULTS.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def main() -> int:
    frame = pd.read_csv(SUMMARY_PATH)
    _validate_panel(frame)
    descriptive = build_descriptive(frame)
    alpha_specific = build_alpha_specific_contrasts(frame)
    pooled = build_pooled_contrasts(frame)
    descriptive.to_csv(
        FORMAL_DIR / "v2_formal_descriptive.csv", index=False, encoding="utf-8-sig"
    )
    alpha_specific.to_csv(
        FORMAL_DIR / "v2_formal_paired_vs_typical22.csv",
        index=False,
        encoding="utf-8-sig",
    )
    pooled.to_csv(
        FORMAL_DIR / "v2_formal_pooled_delay_effects.csv",
        index=False,
        encoding="utf-8-sig",
    )
    write_report(frame, descriptive, alpha_specific, pooled)
    print(f"Analyzed {len(frame)} formal runs in {FORMAL_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
