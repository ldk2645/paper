"""Combine registered 20+20 pilot waves without rerunning any model worlds.

Usage: python -B scripts/analyze_precision_pilot.py INITIAL EXPANSION --output NEW
Optional --validation-initial/--validation-expansion bind passed read-only
semantic validation reports to the exact input batches. Without both reports,
the output explicitly remains pending semantic validation.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from abm_jasss.research_world import canonical_hash, jsonable
from scripts.precision_statistics import build_precision_analysis, assess_precision_stability
from scripts.run_precision_pilot import analysis_spec, resolve_design
from scripts.validate_s1_outputs import read, require


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + "\n"


def _read_wave(directory, wave):
    directory = Path(directory)
    require(not directory.is_symlink(), "Symlinks are not permitted in an input batch")
    directory = directory.resolve(strict=True)
    require(directory.is_dir(), "Input batch must be a directory")
    paths = list(directory.rglob("*"))
    require(not any(path.is_symlink() for path in paths),
            "Symlinks are not permitted in an input batch")
    files = {path.relative_to(directory).as_posix(): path for path in paths if path.is_file()}
    inventory = read(directory / "artifact_hashes.json")
    require(isinstance(inventory, dict), "Input artifact inventory must be a mapping")
    require(set(inventory) == set(files) - {"artifact_hashes.json"},
            f"Input artifact file inventory mismatch: {wave}")
    # A validation report binds the inventory, but the current bytes must also
    # still match it, including raw artifacts not consumed by this analysis.
    for relative, digest in inventory.items():
        require(sha256(files[relative]) == digest, f"Input hash mismatch: {wave}/{relative}")
    checked = {"artifact_hashes.json": sha256(directory / "artifact_hashes.json")}

    def checked_path(relative):
        path = directory / relative
        require(relative in inventory, f"Unregistered input artifact: {relative}")
        digest = sha256(path)
        require(digest == inventory[relative], f"Input hash mismatch: {wave}/{relative}")
        checked[relative] = digest
        return path

    manifest = read(checked_path("manifest.json"))
    require(manifest["schema_version"] == "precision-batch-1"
            and manifest["stage"] == "precision_pilot" and manifest["formal_ready"] is False,
            "Only independent precision-pilot batches can be combined")
    require(manifest["wave"] == wave and manifest["status"] == "complete"
            and manifest["failed_groups"] == 0, f"Incomplete or wrong pilot wave: {wave}")
    spec = read(checked_path("configuration.json"))
    require(spec == manifest["specification"]
            and canonical_hash(spec) == manifest["specification_hash"], "Specification hash mismatch")
    require(manifest["source_hash"] == spec["expected_source_hash"]
            and canonical_hash(manifest["source_sha256"]) == manifest["source_hash"],
            "Registered engine source hash mismatch")
    live_engine = {path.name: sha256(path) for path in sorted((ROOT / "abm_jasss").glob("*.py"))}
    require(live_engine == manifest["source_sha256"], "Live engine differs from the pilot source")
    for name, digest in manifest["source_sha256"].items():
        require(sha256(checked_path(f"source_snapshot/abm_jasss/{name}")) == digest,
                f"Archived engine file mismatch: {name}")
    for name in ("precision_statistics.py", "run_precision_pilot.py"):
        archived = checked_path(f"source_snapshot/scripts/{name}")
        require(sha256(ROOT / "scripts" / name) == sha256(archived),
                f"Live analysis dependency differs from pilot snapshot: {name}")

    require(len(spec["initial_seeds"]) == len(spec["expansion_seeds"]) == 20,
            "Combined analysis requires registered 20+20 seed waves")
    jobs = resolve_design(spec, wave)
    require(read(checked_path("resolved_design.json")) == jsonable(jobs), "Resolved pilot design differs")
    require(manifest["expected_groups"] == manifest["completed_groups"] == len(jobs),
            "Incomplete expected mother-world groups")
    require(manifest["complete_records"] == 18 * len(jobs), "Incomplete physical world records")
    require(read(checked_path("failures.json")) == [], "Pilot records contain failures")
    records = read(checked_path("statistical_records.json"))
    require(isinstance(records, list) and len(records) == 19 * len(jobs),
            "Incomplete statistical arm registry")
    analysis = build_precision_analysis(records, analysis_spec(spec, spec[wave + "_seeds"]))
    require(all(group["shared_plan"]["operationally_complete"] for group in analysis["groups"]),
            "Missing or failed mother-world arms")
    require(read(checked_path("precision_analysis.json")) == analysis,
            "Stored single-wave precision analysis does not reconstruct")
    return {"directory": directory, "manifest": manifest, "specification": spec,
            "records": records, "analysis": analysis, "input_hashes": checked}


def _validation(path, wave):
    if path is None:
        return {"status": "not_provided", "passed": False}
    path = Path(path).resolve()
    report = read(path)
    manifest = wave["manifest"]
    require(report.get("status") == "passed" and report.get("read_only") is True
            and report.get("formal_ready") is False, "Semantic validation report did not pass")
    require(report.get("batch_id") == manifest["batch_id"], "Validation report belongs to another batch")
    require(report.get("source_hash") == manifest["source_hash"], "Validation source hash mismatch")
    require(report.get("manifest_hash") == wave["input_hashes"]["manifest.json"],
            "Validation report is not bound to this manifest")
    require(report.get("artifact_inventory_hash") == wave["input_hashes"]["artifact_hashes.json"],
            "Validation report is not bound to this artifact inventory; rerun semantic validation")
    return {"status": "passed", "passed": True, "path": str(path), "sha256": sha256(path),
            "batch_id": manifest["batch_id"], "source_hash": manifest["source_hash"],
            "manifest_hash": report["manifest_hash"],
            "artifact_inventory_hash": report["artifact_inventory_hash"]}


def _planning_rows(planning, stability):
    diagnostics = {(item["family"], item["alpha"], item["contrast"], item["metric"]): item
                   for item in stability["items"]}
    shared_alpha = {item["alpha"]: item for item in planning["shared_by_alpha"]}
    rows = []
    for group in planning["groups"]:
        for contrast, metrics in group["contrasts"].items():
            for metric, item in metrics.items():
                plan = item["precision_plan"]
                diagnostic = diagnostics[group["family"], group["alpha"], contrast, metric]
                rows.append({
                    "family": group["family"], "alpha": group["alpha"],
                    "contrast": contrast, "metric": metric,
                    "pilot_total": item["n_total"], "joint_valid": item["n_joint_valid"],
                    "single_sided_valid": item["n_single_sided_valid"],
                    "partially_valid": item["n_partially_valid"], "none_valid": item["n_none_valid"],
                    "sample_variance": item["sample_variance"], "sample_sd": item["sample_sd"],
                    "joint_support": item["joint_support"],
                    "wilson95_lower": item["joint_support_wilson95"][0],
                    "wilson95_upper": item["joint_support_wilson95"][1],
                    "target_half_width": plan["target_half_width"],
                    "required_valid": plan["required_valid"],
                    "required_total_uncapped": plan["required_total_uncapped"],
                    "fixed_total": plan["fixed_total"],
                    "precision_target_feasible": plan["precision_target_feasible"],
                    "budget_capped": plan["budget_capped"], "planning_status": plan["status"],
                    "family_shared_total": group["shared_plan"]["fixed_total"],
                    "alpha_shared_total": shared_alpha[group["alpha"]]["fixed_total"],
                    "variance_relative_change_20_to_40": diagnostic["variance_relative_change"],
                    "support_absolute_change_20_to_40": diagnostic["support_absolute_change"],
                    "joint_valid_at_least_minimum": diagnostic["sufficient_joint_valid"],
                    "planning_stable": diagnostic["stable"],
                })
    return rows


def _format_number(value):
    if value is None:
        return "不可规划"
    return str(value)


def _report(spec, planning, stability, validation, rows):
    validated = all(value["passed"] for value in validation.values())
    stable_count = sum(item["stable"] for item in stability["items"])
    feasible_count = sum(row["precision_target_feasible"] for row in rows)
    status = "两批已通过只读语义验收。" if validated else "尚未提供两批完整的语义验收报告；当前结果需完成验收后复核。"
    model = spec["model"]
    lines = [
        "# 独立精度 pilot 合并规划", "",
        f"两批各 20 个新种子，合计每个 α 40 个母世界；共 {len(rows)} 项主要对比×指标×α 规划。{status}",
        "`formal_ready=false`；这是正式运行前的方差与联合可测支持规划，尚未冻结正式实验。", "",
        f"N={model['n_agents']}、T={model['steps']}，末段评价窗={model['final_window']} tick，分叉 t*={spec['fork_tick']}；α={spec['alphas']}。",
        f"半宽目标 h={spec['precision']['target_half_width']}，最低联合可测数={spec['precision']['min_valid']}，每层母世界上限={spec['precision']['max_total']}。",
        "E2 使用四格的五项配对线性对比；E3 分开闭环政策与固定计划回放；E4 使用 B1–B4 对 B0。", "",
        "| α | 跨 family 未截断需求 | 共享固定样本量候选 | 精度预算可行 |",
        "|---|---:|---:|---|",
    ]
    for item in planning["shared_by_alpha"]:
        lines.append(f"| {item['alpha']} | {_format_number(item['required_total_uncapped'])} | "
                     f"{_format_number(item['fixed_total'])} | {'是' if item['precision_target_feasible'] else '否'} |")
    lines.extend(["", "| family | α | 未截断需求 | 共享样本量候选 | 状态 |",
                  "|---|---:|---:|---:|---|"])
    for group in planning["groups"]:
        plan = group["shared_plan"]
        lines.append(f"| {group['family']} | {group['alpha']} | {_format_number(plan['required_total_uncapped'])} | "
                     f"{_format_number(plan['fixed_total'])} | {plan['status']} |")
    lines.extend([
        "", f"逐项预算可行：{feasible_count}/{len(rows)}；前 20 与全部 40 的稳定性诊断通过：{stable_count}/{len(rows)}。",
        "稳定性只检查样本方差相对变化≤25%、联合支持率绝对变化≤0.10，以及全部 40 中至少 30 个联合可测母世界。",
        "追加至 40 在运行前固定，不由均值、效应方向、显著性或上述诊断决定；40 后停止 pilot。未通过诊断的项目须保留并在设计冻结时说明。", "",
        "独立单位始终是母世界。先在每世界按冻结窗口汇总，再构造配对差或四格交互；tick、个体和处理臂均不增加独立重复数。",
        "缺失保留在完整母世界名册中，使用各比较的联合可测比例及其 Wilson 95% 下界调整总样本量。主 3 仅适用于相应处理共同有响应的子群；主 1 若受覆盖门槛筛选，也具有条件解释。",
        "1.96×样本标准差及 Wilson 支持调整是点态精度规划近似，不保证有限样本实际覆盖，也不宣称多重对比同时覆盖。方差为零不保证未来差异恒为零；最低样本量约束仍保留。",
        "共享候选样本量取所有已登记主要对比的最大需求；任一无法规划项不能被静默剔除。超过上限时保留未截断需求并标记预算不足。", "",
        "规划只适用于本批相同 N/T、初始化分布、观察/评价窗口、覆盖规则、推断参数、供给尺度、分叉时点与处理定义。更改这些条件不能直接沿用本次 n。",
        "正式种子必须独立于开发及本 pilot；正式总 n 在运行前冻结，最低 30 只作结束后验收，不能持续抽样到够数。",
        "完整配对值、支持模式及逐项规划见 `planning.json`；稳定性见 `stability.json`；可筛选的逐项表见 `planning.csv`；输入与分析代码哈希见 `analysis_manifest.json`。", "",
    ])
    return "\n".join(lines)


def analyze(initial, expansion, output, *, validation_initial=None, validation_expansion=None):
    """Check registered analysis inputs and write only a new output directory."""
    output = Path(output).resolve()
    require(not output.exists(), "Output already exists; preserve immutable analyses")
    for directory in (initial, expansion):
        require(not output.is_relative_to(Path(directory).resolve()),
                "Analysis output must not be inside an immutable input batch")
    first = _read_wave(initial, "initial")
    second = _read_wave(expansion, "expansion")
    require(first["directory"] != second["directory"]
            and first["manifest"]["batch_id"] != second["manifest"]["batch_id"], "Pilot batches must be distinct")
    require(first["specification"] == second["specification"], "Pilot waves have different specifications")
    require(first["manifest"]["source_hash"] == second["manifest"]["source_hash"], "Pilot waves have different engine sources")
    spec = first["specification"]
    parents = spec["initial_seeds"] + spec["expansion_seeds"]
    require(len(set(parents)) == 40, "Pilot seed waves overlap")
    validation = {"initial": _validation(validation_initial, first),
                  "expansion": _validation(validation_expansion, second)}
    records = first["records"] + second["records"]
    planning = build_precision_analysis(records, analysis_spec(spec, parents))
    stability = assess_precision_stability(first["analysis"], planning, **spec["stability"])
    rows = _planning_rows(planning, stability)
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    manifest = {
        "schema_version": "precision-combined-analysis-1", "stage": "precision_pilot",
        "created_at": datetime.now(timezone.utc).isoformat(), "formal_ready": False,
        "source_hash": spec["expected_source_hash"], "specification_hash": canonical_hash(spec),
        "parents_per_alpha": 40, "planning_items": len(rows),
        "semantic_validation_complete": all(value["passed"] for value in validation.values()),
        "validation": validation, "input_batches": {
            wave: {"directory": str(item["directory"]), "batch_id": item["manifest"]["batch_id"],
                   "input_hashes": item["input_hashes"]}
            for wave, item in (("initial", first), ("expansion", second))},
        "analysis_source_sha256": {f"scripts/{name}": sha256(ROOT / "scripts" / name)
                                   for name in ("analyze_precision_pilot.py", "precision_statistics.py",
                                                "run_precision_pilot.py")},
        "analysis_scope": "Registered summaries and planning reconstruction; raw semantics require supplied validation reports.",
    }
    payloads = {"planning.json": _json_text(planning), "stability.json": _json_text(stability),
                "planning.csv": csv_buffer.getvalue(), "report.md": _report(spec, planning, stability, validation, rows),
                "analysis_manifest.json": _json_text(manifest)}
    output.mkdir(parents=True, exist_ok=False)
    for name, payload in payloads.items():
        with (output / name).open("x", encoding="utf-8", newline="") as stream:
            stream.write(payload)
    hashes = {name: sha256(output / name) for name in sorted(payloads)}
    with (output / "artifact_hashes.json").open("x", encoding="utf-8", newline="") as stream:
        stream.write(_json_text(hashes))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("initial", type=Path)
    parser.add_argument("expansion", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validation-initial", type=Path)
    parser.add_argument("--validation-expansion", type=Path)
    args = parser.parse_args()
    try:
        result = analyze(args.initial, args.expansion, args.output,
                         validation_initial=args.validation_initial,
                         validation_expansion=args.validation_expansion)
    except (ValueError, TypeError, KeyError, IndexError, OSError) as error:
        print(_json_text({"status": "failed", "error": str(error)}), end="")
        raise SystemExit(1)
    print(_json_text({"status": "complete", "output": str(args.output.resolve()),
                     "planning_items": result["planning_items"],
                     "semantic_validation_complete": result["semantic_validation_complete"],
                     "formal_ready": False}), end="")


if __name__ == "__main__":
    main()
