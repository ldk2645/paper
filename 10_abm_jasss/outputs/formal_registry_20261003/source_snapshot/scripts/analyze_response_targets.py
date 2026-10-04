"""Add time-matched response-target diagnostics to existing saved simulations."""
import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from abm_jasss.cli import bootstrap_mean, write_csv
from abm_jasss.response_diagnostics import response_target_diagnostics

MEASURES = ("attention_error_final_window", "sensing_error_final_window",
            "response_target_mismatch_at_trigger", "response_target_mismatch_at_execution",
            "signed_mismatch_change", "preference_drift_between_trigger_and_execution",
            "response_execution_step_fraction", "response_actions_final_window")


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analyze(source, output):
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use an empty/new analysis output directory")
    output.mkdir(parents=True, exist_ok=True)
    suite = json.loads((source / "suite_manifest.json").read_text(encoding="utf-8"))
    if suite["status"] != "complete":
        raise ValueError("Source suite is not complete")
    metadata = {"status": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
                "source_suite": str(source.resolve()), "source_suite_sha256": digest(source / "suite_manifest.json"),
                "source_files_sha256": {}, "analysis_seed": 90301, "bootstrap_draws": 2000,
                "analysis_unit": "seed/world; no event pooling across worlds",
                "window": "final_window, selected by execution time; trigger time may precede window",
                "scope": "descriptive response-topic mismatch; not welfare or identified delay effect"}
    (output / "manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    all_cohorts, all_pending, summaries = [], [], []
    for scenario in suite["cases"]:
        folder = source / scenario
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if manifest["status"] != "complete" or manifest["failed_world_runs"]:
            raise ValueError(f"Incomplete source: {scenario}")
        design_path = folder / "resolved_design.json"
        for path in (folder / "manifest.json", design_path):
            metadata["source_files_sha256"][str(path.relative_to(source))] = digest(path)
        for job in json.loads(design_path.read_text(encoding="utf-8")):
            run_id, config = job["run_id"], job["model"]
            series_path = folder / "trajectories" / f"{run_id}.csv"
            events_path = folder / "events" / f"{run_id}.json"
            for path in (series_path, events_path):
                metadata["source_files_sha256"][str(path.relative_to(source))] = digest(path)
            rows = read_csv(series_path)
            saved = json.loads(events_path.read_text(encoding="utf-8"))
            result = response_target_diagnostics(rows, saved["events"], config, saved["pending_responses"])
            identity = dict(scenario=scenario, run_id=run_id, seed=job["seed"], alpha=config["alpha"], arm=config["active_arm"])
            cohorts = result["executed_cohorts"]
            all_cohorts.extend({**identity, **row} for row in cohorts)
            all_pending.extend({**identity, **row} for row in result["pending_cohorts"])
            cutoff = config["steps"] - config["final_window"]
            tail = rows[cutoff:]
            selected = [row for row in cohorts if row["due_step"] >= cutoff]
            executions = [e for e in saved["events"] if e["kind"] == "response_executed" and e["step"] >= cutoff]
            summary = {**identity, "final_window": config["final_window"],
                       "attention_error_final_window": float(np.mean([float(r["attention_error"]) for r in tail])),
                       "sensing_error_final_window": float(np.mean([float(r[f'error_{config["active_arm"]}']) for r in tail])),
                       "response_cohorts_final_window": len(selected), "response_actions_final_window": len(executions),
                       "response_execution_step_fraction": len({e["step"] for e in executions}) / config["final_window"],
                       "response_actions_total": sum(e["kind"] == "response_executed" for e in saved["events"]),
                       "pending_actions_at_end": len(saved["pending_responses"])}
            for metric in MEASURES[2:6]:
                summary[metric] = float(np.mean([row[metric] for row in selected])) if selected else None
            summaries.append(summary)
        print(f"Analyzed {scenario}", flush=True)
    if len(summaries) != suite["world_runs"]:
        raise ValueError("World count differs from suite")
    write_csv(output / "response_cohorts.csv", all_cohorts)
    write_csv(output / "pending_cohorts.csv", all_pending)
    write_csv(output / "runs.csv", summaries)
    groups = defaultdict(list)
    for row in summaries:
        groups[(row["scenario"], row["alpha"], row["arm"])].append(row)
    rng, aggregates = np.random.default_rng(90301), []
    for (scenario, alpha, arm), group in sorted(groups.items()):
        group = sorted(group, key=lambda row: row["seed"])
        for metric in MEASURES:
            values = [row[metric] for row in group if row[metric] is not None]
            low, high = bootstrap_mean(values, rng) if values else (None, None)
            aggregates.append(dict(scenario=scenario, alpha=alpha, arm=arm, metric=metric,
                                   n_worlds=len(group), n_measured_worlds=len(values),
                                   mean=float(np.mean(values)) if values else None, ci_low=low, ci_high=high))
    write_csv(output / "aggregate.csv", aggregates)
    lines = ["# 行文框架对应的三层结果：开发诊断", "",
             "基于原480世界的已存轨迹与事件后处理，未重跑或更改模型。以下不是正式机制因果分解。", "",
             "第一层是末时窗TV(P,A)，第二层是实际驱动政府的估计器TV(P,P_hat)。第三层为已执行回应的话题组成与触发/执行时偏好的TV距离，不是资源、福利或热度抑制幅度。", "",
             "回应按相同触发与执行时刻分组，组内话题按动作数归一化；每个世界先对末时窗内执行的组求均值，再在种子间汇总。当前试跑capacity=1，故每组只有一个动作，其错配等于1−该话题偏好。", "",
             "| 情景（α=0.75，仅作阅读入口） | 注意力差异 | 感知误差 | 回应触发错配 | 回应执行错配 | 末窗执行数 | 有回应的世界数 |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    lookup = {(row["scenario"], row["alpha"], row["metric"]): row for row in aggregates}
    for scenario in suite["cases"]:
        values = [lookup[(scenario, .75, name)]["mean"] for name in
                  ("attention_error_final_window", "sensing_error_final_window", "response_target_mismatch_at_trigger",
                   "response_target_mismatch_at_execution", "response_actions_final_window")]
        count = lookup[(scenario, .75, "response_target_mismatch_at_execution")]["n_measured_worlds"]
        lines.append("| " + scenario + " | " + " | ".join("NA" if v is None else f"{v:.4f}" for v in values) + f" | {count} |")
    lines += ["", "NA表示没有已执行回应，不能填为零或均匀分布。回应指标以发生行动为条件，必须与动作数、执行步覆盖、期末积压一起解释。",
              "执行错配减触发错配可以为负，只反映该轨迹中目标相对偏好变化；不是行政延迟的已识别因果效应。三层距离不能相加为总误差。",
              "感知误差为零的oracle是定义上的理想信息，不保证回应策略最优；不同政策世界的偏好已经内生变化。",
              "aggregate.csv包含全部α及种子bootstrap点态区间，保留每个指标的可测世界数。每格8个开发种子，无多重比较校正。",
              "零行政延迟、排序知识处理与同状态架构干预仍未实现；本次后处理不改变这些实验的完成状态。"]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    snapshot = output / "analysis_source"
    snapshot.mkdir()
    for path in (Path(__file__).resolve(), ROOT / "abm_jasss/response_diagnostics.py", ROOT / "abm_jasss/cli.py"):
        shutil.copyfile(path, snapshot / path.name)
    metadata.update(status="complete", world_runs=len(summaries), executed_cohorts=len(all_cohorts),
                    pending_cohorts=len(all_pending), finished_utc=datetime.now(timezone.utc).isoformat(),
                    analysis_source_sha256={p.name: digest(p) for p in snapshot.iterdir()})
    (output / "manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.source, args.output)
    print(f"Completed {result['world_runs']} worlds and {result['executed_cohorts']} executed cohorts")
