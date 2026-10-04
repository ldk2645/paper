"""Read-only presentation of an accepted frozen formal analysis; no model runs/tests.

All numerical estimates and tests are copied from the accepted analysis. The
only aggregation here counts registered results or describes support/precision.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys

sys.dont_write_bytecode = True
TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[1]
if (TOOLS / "vendor").is_dir():
    sys.path.insert(0, str(TOOLS / "vendor"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MPLCONFIGDIR", str(TOOLS / "matplotlib_cache"))

ORDER = {
    "E2": ["pref_given_rule0", "pref_given_rule1", "rule_given_pref0", "rule_given_pref1", "interaction"],
    "E3_closed": ["delay0", "delay1", "delay10", "capacity2", "observation2"],
    "E3_replay": ["delay1", "delay3", "delay10"],
    "E4": ["B1", "B2", "B3", "B4"],
}
METRICS = {
    "platform_representation_gap": "主1：平台表征差距",
    "perception_error": "主2：政府感知误差",
    "targeting_error_trigger": "主3：触发目标错配",
}
FAMILIES = {"E2": "信息四格", "E3_closed": "闭环动态", "E3_replay": "固定计划回放", "E4": "母状态分叉"}
E2_LABELS = dict(zip(ORDER["E2"], ["I10−I00", "I11−I01", "I01−I00", "I11−I10", "I11−I10−I01+I00"]))
STATUSES = {"estimated": "可推断", "insufficient_joint_support": "联合有效不足30",
            "degenerate_sample_variance": "样本方差数值退化", "numerically_unestimable": "数值不可推断",
            "operationally_incomplete": "运行不完整"}
COPY_FIELDS = ("n_total", "n_joint_valid", "n_single_sided_valid", "n_partially_valid", "n_none_valid",
    "mean", "sample_sd", "standard_error", "degrees_of_freedom", "confidence_half_width",
    "p_value_two_sided", "p_value_holm", "p_value_numerical_floor", "reject_holm_0_05",
    "observed_target_half_width_met")
AUXILIARY_LABELS = {
    "has_response": "回应发生率", "execution_count": "执行次数", "execution_coverage": "执行覆盖率",
    "scheduled_count": "新排期数", "pending_count": "期末待执行数", "waiting_time": "已执行动作等待时间",
    "response_completion_L": "固定L完成率", "exposure_gap": "曝光差距",
    "targeting_error_execution": "执行目标错配", "final_preference_shift": "最终偏好变化",
    "final_trust_mean": "最终平均信任", "max_pending": "最大待执行数",
    "platform_signal_coverage": "源信号覆盖率", "perception_data_coverage": "有效感知覆盖率",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2)
        stream.write("\n")


def check_inventory(directory):
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), "Invalid artifact directory")
    paths = list(directory.rglob("*"))
    require(not any(p.is_symlink() for p in paths), "Symlink artifacts are forbidden")
    inventory_hash = digest(directory / "artifact_hashes.json")
    inventory = read(directory / "artifact_hashes.json")
    files = {p.relative_to(directory).as_posix(): p for p in paths if p.is_file()}
    require(set(files) - {"artifact_hashes.json"} == set(inventory), "Artifact inventory mismatch")
    for name, expected in inventory.items():
        require(digest(files[name]) == expected, "Artifact hash mismatch: " + name)
    require(digest(directory / "artifact_hashes.json") == inventory_hash, "Inventory changed while reading")
    return inventory_hash


def write_inventory(directory):
    write_json(directory / "artifact_hashes.json", {p.relative_to(directory).as_posix(): digest(p)
        for p in sorted(directory.rglob("*")) if p.is_file()})


def key(row):
    return row["family"], float(row["alpha"]), row["contrast"], row["metric"]


def expected_keys():
    return [(family, alpha, contrast, metric) for family, contrasts in ORDER.items()
            for alpha in (.25, .75) for contrast in contrasts for metric in METRICS]


def label(family, contrast):
    if family == "E2":
        return E2_LABELS[contrast]
    return contrast + "−" + {"E3_closed": "baseline", "E3_replay": "delay0", "E4": "B0"}[family]


def csv_read(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def csv_write(path, rows):
    with Path(path).open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def primary_rows(inference):
    rows = []
    for group in inference["groups"]:
        require(group["operationally_complete"] is True and not group["missing_records"]
                and not group["failed_records"], "Incomplete inference group")
        for contrast, metrics in group["contrasts"].items():
            for metric, item in metrics.items():
                interval = item["confidence_interval"]
                require(item["additional_sampling"] is False, "Unregistered additional sampling")
                row = {"family": group["family"], "alpha": group["alpha"], "contrast": contrast,
                       "metric": metric, "status": item["status"], **{k: item[k] for k in COPY_FIELDS},
                       "ci_lower": interval[0] if interval else None,
                       "ci_upper": interval[1] if interval else None}
                require(row["n_total"] == row["n_joint_valid"] + row["n_partially_valid"] + row["n_none_valid"],
                        "Invalid support accounting")
                require(0 <= row["n_single_sided_valid"] <= row["n_partially_valid"], "Invalid single-sided count")
                require(item["estimand"] == "mean_paired_contrast_conditional_on_joint_support", "Unexpected estimand")
                half = row["confidence_half_width"]
                require(row["observed_target_half_width_met"] is (half <= .02 if half is not None else None),
                        "Precision indicator mismatch")
                require(row["status"] in STATUSES and row["status"] != "operationally_incomplete", "Invalid analysis status")
                rows.append(row)
    indexed = {key(row): row for row in rows}
    require(len(rows) == len(indexed) == 102 and set(indexed) == set(expected_keys()), "Expected all 102 comparisons")
    return [indexed[k] for k in expected_keys()]


def _csv_scalar(value):
    return "" if value is None else str(value)


def load_accepted(analysis, registry):
    # The existing registry validator is read-only and checks the frozen source,
    # protocol, seed audit and pilot evidence as well as artifact hashes.
    from scripts.formal_registry import validate_registry
    analysis, registry = Path(analysis).resolve(strict=True), Path(registry).resolve(strict=True)
    input_hash = check_inventory(analysis)
    gate = validate_registry(registry)
    manifest = read(analysis / "analysis_manifest.json")
    require(manifest.get("schema_version") == "formal-analysis-1" and manifest.get("stage") == "formal_analysis"
            and manifest.get("formal_ready") is True and manifest.get("semantic_validation_complete") is True
            and manifest.get("additional_sampling") is False and manifest.get("comparison_count") == 102,
            "Only semantically accepted, complete formal analyses can be reported")
    for field in ("registry_hash", "source_hash", "specification_hash"):
        require(manifest.get(field) == gate[field], "Analysis/registry binding mismatch: " + field)
    for field in ("manifest_hash", "artifact_inventory_hash", "validation_report_hash"):
        require(isinstance(manifest.get(field), str) and len(manifest[field]) == 64
                and all(c in "0123456789abcdef" for c in manifest[field]), "Missing accepted-batch binding")
    configuration = read(registry / "configuration.json")
    inference = read(analysis / "inference.json")
    require(inference.get("schema") == "formal-inference-1" and inference.get("operationally_complete") is True
            and inference.get("comparison_count") == 102 and inference.get("additional_sampling") is False
            and inference.get("inference") == configuration["inference"], "Invalid frozen inference policy")
    require(inference["parent_ids_by_alpha"] == {a: [str(s) for s in configuration["seeds"][:n]]
                for a, n in configuration["sample_sizes"].items()}, "Inference parent registry differs")
    rows = primary_rows(inference)
    raw_csv = csv_read(analysis / "primary.csv")
    require(len(raw_csv) == 102 and len({key(row) for row in raw_csv}) == 102, "Duplicate/missing CSV comparison")
    csv_index = {key(row): row for row in raw_csv}
    for row in rows:
        require(row["n_total"] == configuration["sample_sizes"][str(row["alpha"])] , "Sample count differs from registry")
        require(csv_index.get(key(row)) == {k: _csv_scalar(v) for k, v in row.items()}, "CSV/inference mismatch")
    planning_dir = registry / "evidence/project" / configuration["evidence"]["pilot_planning"]
    stability = read(planning_dir / "stability.json")["items"]
    stable_index = {key(row): row for row in stability}
    require(len(stability) == len(stable_index) == 102 and set(stable_index) == set(expected_keys()), "Missing pilot stability items")
    limited = gate["manifest"]["pilot_check"]["budget_limited_items"]
    limited_index = {key(row): row for row in limited}
    require(len(limited_index) == 3 and sum(item["variance_stable"] is False for item in stability) == 61,
            "Registered pilot limitations differ")
    for row in rows:
        item = stable_index[key(row)]
        row.update(pilot_budget_limited=key(row) in limited_index,
                   pilot_required_total_uncapped=limited_index.get(key(row), {}).get("required_total_uncapped"),
                   pilot_variance_unstable=item["variance_stable"] is False)
    auxiliary = csv_read(analysis / "auxiliary.csv")
    require(auxiliary and all(row["scope"] == "descriptive_equal_weight_mother_world_means" for row in auxiliary),
            "Unexpected auxiliary scope")
    require(check_inventory(analysis) == input_hash, "Analysis changed while reading")
    return rows, auxiliary, {"analysis": str(analysis), "registry": str(registry),
        "analysis_manifest_hash": digest(analysis / "analysis_manifest.json"),
        "analysis_inventory_hash": input_hash, "registry_hash": gate["registry_hash"],
        "registry_inventory_hash": gate["artifact_inventory_hash"],
        "source_hash": gate["source_hash"], "specification_hash": gate["specification_hash"],
        "batch_manifest_hash": manifest["manifest_hash"], "batch_inventory_hash": manifest["artifact_inventory_hash"],
        "validation_report_hash": manifest["validation_report_hash"],
        "batch_id": manifest["batch_id"], "semantic_validation_complete": True,
        "sample_sizes": configuration["sample_sizes"], "independent_seeds": len(configuration["seeds"])}


def fmt(value, digits=4):
    if value is None or value == "":
        return "—"
    return f"{float(value):.{digits}g}" if abs(float(value)) < .001 and float(value) else f"{float(value):.{digits}f}"


def yes(value):
    return "是" if value is True else "否" if value is False else "不可判定"


def summary(rows, auxiliary, provenance, synthetic=False):
    by_stratum = []
    for family in ORDER:
        for alpha in (.25, .75):
            for metric in METRICS:
                subset = [row for row in rows if row["family"] == family and row["alpha"] == alpha and row["metric"] == metric]
                by_stratum.append({"family": family, "alpha": alpha, "metric": metric,
                    "comparisons": len(subset), "estimated": sum(row["status"] == "estimated" for row in subset),
                    "holm_rejections": sum(row["reject_holm_0_05"] for row in subset),
                    "target_met": sum(row["observed_target_half_width_met"] is True for row in subset),
                    "target_not_met": sum(row["observed_target_half_width_met"] is False for row in subset),
                    "target_unavailable": sum(row["observed_target_half_width_met"] is None for row in subset),
                    "minimum_n_joint_valid": min(row["n_joint_valid"] for row in subset),
                    "maximum_n_joint_valid": max(row["n_joint_valid"] for row in subset),
                    "n_total_per_comparison": subset[0]["n_total"]})
    return {"schema": "formal-reporting-summary-1", "synthetic_fixture_only": synthetic,
        "additional_sampling": False, "additional_tests": False, "comparison_count": len(rows),
        "estimated": sum(row["status"] == "estimated" for row in rows),
        "holm_rejections": sum(row["reject_holm_0_05"] for row in rows),
        "target_met": sum(row["observed_target_half_width_met"] is True for row in rows),
        "target_not_met": sum(row["observed_target_half_width_met"] is False for row in rows),
        "target_unavailable": sum(row["observed_target_half_width_met"] is None for row in rows),
        "pilot_budget_limited_count": sum(row["pilot_budget_limited"] for row in rows),
        "pilot_variance_unstable_count": sum(row["pilot_variance_unstable"] for row in rows),
        "by_family_alpha_metric": by_stratum,
        "support_and_precision_by_comparison": [{k: row[k] for k in ("family", "alpha", "contrast", "metric",
            "n_total", "n_joint_valid", "n_single_sided_valid", "n_partially_valid", "n_none_valid",
            "confidence_half_width", "observed_target_half_width_met", "status", "reject_holm_0_05",
            "pilot_budget_limited", "pilot_required_total_uncapped", "pilot_variance_unstable")} for row in rows],
        "auxiliary_response_and_coverage": [row for row in auxiliary if row["metric"] in
            ("has_response", "platform_signal_coverage", "perception_data_coverage", "execution_coverage")],
        "provenance": provenance}


def render_plots(rows, output, synthetic=False):
    import matplotlib
    import numpy
    import PIL
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    fonts = [Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/simhei.ttf"), Path("C:/Windows/Fonts/simsun.ttc")]
    font = next((path for path in fonts if path.is_file()), None)
    require(font is not None, "A Chinese font is required for complete chart labels")
    font_manager.fontManager.addfont(str(font))
    font_name = font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams.update({"font.family": font_name, "axes.unicode_minus": False, "font.size": 10,
                         "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "path"})
    artifacts = []
    for metric_index, metric in enumerate(METRICS, 1):
        bounds = [float(row[k]) for row in rows if row["metric"] == metric
                  for k in ("mean", "ci_lower", "ci_upper") if row[k] is not None] + [0.]
        minimum, maximum = min(bounds), max(bounds)
        span = max(maximum - minimum, .01)
        limits = (minimum - span * .10, maximum + span * .10)
        for alpha in (.25, .75):
            selected = [row for row in rows if row["metric"] == metric and row["alpha"] == alpha]
            fig = plt.figure(figsize=(15.8, 10.3))
            grid = fig.add_gridspec(1, 3, left=.035, right=.98, top=.87, bottom=.23,
                                   width_ratios=(3.3, 5., 5.1), wspace=.02)
            labels_ax, forest_ax, numbers_ax = [fig.add_subplot(grid[0, i]) for i in range(3)]
            for axis in (labels_ax, forest_ax, numbers_ax):
                axis.set_ylim(-.8, 17.0)
                axis.invert_yaxis()
            for axis in (labels_ax, numbers_ax):
                axis.set_xlim(0, 1)
                axis.axis("off")
            forest_ax.set_xlim(*limits)
            forest_ax.set_yticks([])
            forest_ax.axvline(0, color="#999999", lw=.9, zorder=0)
            forest_ax.grid(axis="x", color="#dddddd", lw=.6)
            forest_ax.spines[["left", "right", "top"]].set_visible(False)
            forest_ax.set_xlabel("联合可测母世界的配对差均值（点态95% CI）", labelpad=10)
            labels_ax.text(0, -.65, "家族 / 登记对比", weight="bold")
            numbers_ax.text(.01, -.65, "均值 [点态95% CI]", weight="bold", fontsize=9)
            numbers_ax.text(.57, -.65, "联合/总数", weight="bold", fontsize=9)
            numbers_ax.text(.80, -.65, "Holm", weight="bold", fontsize=9)
            numbers_ax.text(.94, -.65, "h≤.02", weight="bold", fontsize=9, ha="center")
            for i, row in enumerate(selected):
                if i in (5, 10, 13):
                    for axis in (labels_ax, forest_ax, numbers_ax):
                        axis.axhline(i - .5, color="#bdbdbd", lw=.8)
                marks = ("†" if row["pilot_budget_limited"] else "") + ("‡" if row["pilot_variance_unstable"] else "")
                labels_ax.text(0, i, f"{row['family']}  {label(row['family'], row['contrast'])}{marks}", va="center", fontsize=9)
                rejected = row["reject_holm_0_05"]
                color = "#126782" if rejected else "#555555"
                if row["ci_lower"] is not None:
                    forest_ax.errorbar(row["mean"], i, xerr=[[row["mean"] - row["ci_lower"]], [row["ci_upper"] - row["mean"]]],
                        fmt="o", color=color, markerfacecolor=color if rejected else "white",
                        markeredgewidth=1.2, markersize=5.5, capsize=3, elinewidth=1.2)
                elif row["mean"] is not None:
                    forest_ax.plot(row["mean"], i, marker="x", color="#777777", markersize=6)
                else:
                    forest_ax.text((limits[0] + limits[1]) / 2, i, "均值不可用", va="center", ha="center", fontsize=8)
                interval = f"[{fmt(row['ci_lower'])}, {fmt(row['ci_upper'])}]" if row["ci_lower"] is not None else "[CI不可用]"
                numbers_ax.text(.01, i, f"{fmt(row['mean'])} {interval}", va="center", fontsize=8.5)
                numbers_ax.text(.64, i, f"{row['n_joint_valid']}/{row['n_total']}", va="center", ha="center", fontsize=8.5)
                numbers_ax.text(.82, i, "拒绝" if rejected else "不拒绝", va="center", ha="center", fontsize=8.5)
                numbers_ax.text(.94, i, yes(row["observed_target_half_width_met"]), va="center", ha="center", fontsize=8.5)
            prefix = "合成夹具｜非正式结果\n" if synthetic else ""
            fig.suptitle(f"{prefix}{METRICS[metric]}  ·  α={alpha}  ·  全部17个登记对比", y=.96, fontsize=16)
            fig.text(.035, .135, "● Holm校正后拒绝（全102项）；○ 不拒绝；× 仅描述均值、无可用区间。点态区间不具有同时覆盖含义。", fontsize=10)
            fig.text(.035, .104, "† pilot预算不足项；‡ pilot方差不稳定项。所有标记保留，正式精度按当前半宽描述，不补样。", fontsize=10)
            fig.text(.035, .073, "估计条件为每项对比的共同可测支持；回应/覆盖可能随处理变化。E3回放是固定供体计划的时间机制诊断。", fontsize=10)
            fig.text(.035, .042, "两层α采用同一指标轴范围；E3闭环baseline行政延迟为3。不新增跨α检验，不将条件差值外推为总体政策效果。", fontsize=9)
            stem = f"forest_alpha_{str(alpha).replace('.', '_')}_primary_{metric_index}"
            for extension in ("pdf", "svg", "png"):
                filename = stem + "." + extension
                fig.savefig(output / filename, dpi=220 if extension == "png" else 300,
                            metadata={"Title": "Synthetic fixture only" if synthetic else "Frozen formal conditional contrasts"} if extension == "pdf" else None)
                artifacts.append(filename)
            plt.close(fig)
    return artifacts, {"library": "matplotlib", "version": matplotlib.__version__, "numpy": numpy.__version__,
        "pillow": PIL.__version__, "python": platform.python_version(), "font": str(font),
        "font_sha256": digest(font), "font_family": font_name}


def render(rows, auxiliary, provenance, output, *, synthetic=False):
    output = Path(output).resolve()
    require(not output.exists(), "Output exists; preserve immutable reports")
    output.mkdir(parents=True, exist_ok=False)
    value = summary(rows, auxiliary, provenance, synthetic)
    translated = []
    for row in rows:
        translated.append({"家族": row["family"], "家族说明": FAMILIES[row["family"]], "α": row["alpha"],
            "登记对比": row["contrast"], "对比说明": label(row["family"], row["contrast"]),
            "主指标": METRICS[row["metric"]], "推断状态": STATUSES[row["status"]],
            "n_total": row["n_total"], "n_joint_valid": row["n_joint_valid"],
            "n_single_sided_valid": row["n_single_sided_valid"], "n_partially_valid": row["n_partially_valid"],
            "n_none_valid": row["n_none_valid"], "均值": row["mean"], "样本SD": row["sample_sd"],
            "标准误": row["standard_error"], "自由度": row["degrees_of_freedom"],
            "点态95%CI下限": row["ci_lower"], "点态95%CI上限": row["ci_upper"],
            "点态CI半宽": row["confidence_half_width"], "半宽≤0.02": yes(row["observed_target_half_width_met"]),
            "原始双侧p": row["p_value_two_sided"], "Holm_p": row["p_value_holm"],
            "p数值下限标记": yes(row["p_value_numerical_floor"]), "Holm拒绝0.05": yes(row["reject_holm_0_05"]),
            "pilot预算不足": yes(row["pilot_budget_limited"]), "pilot未截断需求": row["pilot_required_total_uncapped"],
            "pilot方差不稳定": yes(row["pilot_variance_unstable"]), "仅合成夹具": synthetic})
    csv_write(output / "primary_zh.csv", translated)
    csv_write(output / "auxiliary_zh.csv", [{"家族": r["family"], "α": r["alpha"], "臂": r["arm"],
        "指标": AUXILIARY_LABELS.get(r["metric"], r["metric"]), "metric": r["metric"], "n_total": r["n_total"],
        "n_valid": r["n_valid"], "母世界等权均值": r["mean"], "范围": "描述性，不新增检验", "仅合成夹具": synthetic} for r in auxiliary])
    figures, renderer = render_plots(rows, output, synthetic)
    write_json(output / "summary.json", value)
    lines = ["# " + ("合成夹具报告（不是正式结果）" if synthetic else "E2–E4正式结果：登记对比、精度与支持"), "",
        f"全部102项登记对比均保留；{value['estimated']}项可推断，{value['holm_rejections']}项在全102项Holm校正后拒绝。",
        f"实际点态95%区间半宽≤0.02：{value['target_met']}项；超过目标：{value['target_not_met']}项；区间不可用：{value['target_unavailable']}项。", "",
        "低α固定184、高α固定1000个母世界；两层嵌套复用seed，共1000个独立seed。不同对比的共同可测支持可能不同。",
        "估计对象为每项各臂共同可测时的母世界配对差均值；主1覆盖筛选与主3回应筛选可随处理改变，不能将所有差值外推为总体平均政策效果。E3回放只描述固定合法供体计划下的时间机制。",
        "三个主指标均为TV距离。主1要求末窗有效源信号覆盖≥0.8；主2排除无数据、仅先验的tick；主3按末窗已执行(trigger, execution)cohort等权汇总，无动作保留None。",
        "E2交互为I11−I10−I01+I00，负值表示低于加性预测，不能统一解释为改善。E3闭环baseline延迟3；回放baseline延迟0，固定供体触发/目标/动作参数，仍允许后续偏好和信号变化，二者不构成直接/间接效应分解。E4 B2仅将分叉后的新计划延迟改为1，旧pending保持；B4仅将排名α改为0，不等于完整heat-off。",
        "区间为点态95% t区间，不是同时区间；原始双侧p与一次全102项Holm校正值原样保留。边际t推断为近似，Holm不修复其近似误差。不新增检验，不补样。", "",
        "保留3项pilot预算不足与61项20→40方差不稳定标记。以下三个未截断需求不因正式实际半宽而改写：", "",
        "|α|家族/对比|指标|pilot需求|固定上限|", "|---|---|---|---:|---:|"]
    for row in rows:
        if row["pilot_budget_limited"]:
            lines.append(f"|{row['alpha']}|{row['family']} / {label(row['family'], row['contrast'])}|{METRICS[row['metric']]}|{row['pilot_required_total_uncapped']}|1000|")
    lines.extend(["", "完整数值见 [102项中文主表](primary_zh.csv)，逐臂回应发生率、源信号/感知覆盖和全部辅助描述见 [辅助表](auxiliary_zh.csv)。辅助表保留总数与有效数，不把无回应错配填零。",
        "共同可测、部分可测和全不可测三类相加为总数；单侧可测是部分可测的子集（四格交互尤其如此），不能重复相加。", "",
        "|家族|α|对比|指标|均值 [点态95% CI]|联合/总数|单侧/部分/全无|Holm拒绝|h≤.02|pilot预算/方差|",
        "|---|---:|---|---|---|---:|---:|---|---|---|"])
    for row in rows:
        interval = f"[{fmt(row['ci_lower'])}, {fmt(row['ci_upper'])}]" if row["ci_lower"] is not None else STATUSES[row["status"]]
        lines.append(f"|{row['family']}|{row['alpha']}|{label(row['family'], row['contrast'])}|{METRICS[row['metric']]}|{fmt(row['mean'])} {interval}|{row['n_joint_valid']}/{row['n_total']}|{row['n_single_sided_valid']}/{row['n_partially_valid']}/{row['n_none_valid']}|{yes(row['reject_holm_0_05'])}|{yes(row['observed_target_half_width_met'])}|{yes(row['pilot_budget_limited'])}/{yes(row['pilot_variance_unstable'])}|")
    lines.extend(["", "六幅图分别覆盖两层α与三个主指标，每幅保留17个对比。相同指标两层使用同一轴范围。PDF/SVG为矢量，PNG为220dpi。", ""])
    for filename in figures:
        if filename.endswith(".pdf"):
            lines.append(f"- [{filename}]({filename})")
    lines.extend(["", "有限合成参考、离散推断网格、来源窗末目录近似、种群/供给尺度限制仍适用；不自动支持经验外推。", "",
        "输入分析、冻结登记和生成器哈希见 reporting_manifest.json；所有报告产物由 artifact_hashes.json 绑定。"])
    (output / "report_zh.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {"schema": "formal-reporting-1", "created_at": datetime.now(timezone.utc).isoformat(),
        "synthetic_fixture_only": synthetic, "additional_sampling": False, "additional_tests": False,
        "comparison_count": 102, "generator_sha256": digest(__file__), "provenance": provenance,
        "renderer": renderer, "figures": figures, "summary": {k: value[k] for k in ("estimated", "holm_rejections",
            "target_met", "target_not_met", "target_unavailable", "pilot_budget_limited_count", "pilot_variance_unstable_count")}}
    write_json(output / "reporting_manifest.json", manifest)
    write_inventory(output)
    check_inventory(output)
    return manifest


def generate(analysis, registry, output):
    output = Path(output).resolve()
    for source in (analysis, registry):
        require(not output.is_relative_to(Path(source).resolve()), "Output cannot be inside immutable input")
    require(not output.exists(), "Output exists; preserve immutable reports")
    rows, auxiliary, provenance = load_accepted(analysis, registry)
    return render(rows, auxiliary, provenance, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", type=Path)
    parser.add_argument("registry", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = generate(args.analysis, args.registry, args.output)
    except (ValueError, KeyError, OSError, ImportError, TypeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps({"status": "passed", "output": str(args.output.resolve()), "summary": manifest["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
