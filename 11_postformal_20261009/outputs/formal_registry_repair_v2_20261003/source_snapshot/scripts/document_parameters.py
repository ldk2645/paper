"""Regenerate the current parameter register without modifying experiments."""
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from abm_jasss import __version__
from abm_jasss.model import Config


def main():
    defaults = asdict(Config())
    pilot = json.loads((ROOT / "configs/restored_core.json").read_text(encoding="utf-8"))["model"]
    lines = [f"# 参数与假设登记（{__version__}）", "",
             "所有数值均为尚未经验校准的开发假设。默认 Config 保留无反馈测量模型；恢复主模型须使用 configs/restored_core.json。实际运行以各批次 resolved_design.json 为准。", "",
             "试跑使用α=0、0.25、0.5、0.75、1，以及种子301—308。表中α默认值仅在没有批次覆盖时生效。末时窗不是已验证的稳态。", "",
             "| 参数 | 代码默认值 | 恢复主模型试跑值 |", "|---|---|---|"]
    for key, value in defaults.items():
        lines.append(f"| {key} | `{value}` | `{pilot.get(key, value)}` |")
    lines += ["", "## 解释与假设性质", "",
              "- population_weights为空时随机生成总体目标；恢复主模型采用对称目标[1,1,1,1]，每个种子的实际公众偏好仍以个体均值计算。政府agenda_topics及其目标份额独立指定，不代表公共福利。",
              "- supply_weights为空表示均匀话题供给；platform_panel_size=0表示全体观测。曝光等同消费、同一内容可重复被推荐、无网络结构均是结构假设。",
              "- 情绪优势与官方内容情绪均值是不同假设。no_emotion同时清除二者差异；no_topic_emotion只清除话题差异。漂移是可关闭的行为假设。",
              "- heat_retention控制全体热度衰减；response_heat_retention只在回应执行时调节目标话题普通内容的热度。α=0仍可能通过heat_floor产生热度影响内容存活的通道。",
              "- response_capacity限制每次监测新排期数量，同一话题在待执行期间不重复排期。government_delay增大同时影响排队占用，不能直接解释为纯延迟效应。",
              "- trust_update_rate控制状态变化，trust_feedback_strength控制信任对互动的作用；关闭后者不等于冻结信任。两种trust_rule均未校准。核心配置trust_response_gain=0，不给热度调节动作自动增加信任。",
              "- official_emotion_mean是Beta分布均值，不是原V1固定情绪强度。新版信任方程没有直接使用历史截面回归系数。",
              "- observation_delay>0时，首条观测送达前估计保持均匀先验；低阈值可能使其触发回应。当前核心试跑延迟为0；后续信息延迟实验须区分先验与已观测信号。",
              "- 阈值、初值、时序、寿命、内容供给、信任系数和策略强度均须作敏感性或替代结构检验。未发现或校准现实临界值。", "",
              "生成：python scripts/document_parameters.py。情景覆盖：scripts/run_core_suite.py。"]
    (ROOT / "parameters.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote parameters.md for {__version__}")


if __name__ == "__main__":
    main()
