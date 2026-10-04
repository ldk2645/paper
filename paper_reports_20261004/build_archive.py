"""Build a byte-preserving, selected report archive; never alter source files."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(r"D:\UserData\Desktop\ZLS\ABM_JASSS")
ARCHIVE = Path(__file__).resolve().parent
COPIES = ARCHIVE / "sources" / "ABM_JASSS"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, content: str) -> None:
    with path.open("x", encoding="utf-8", newline="") as stream:
        stream.write(content)


def json_new(name: str, value: object) -> None:
    write_new(ARCHIVE / name, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    if COPIES.exists():
        raise SystemExit("Archive source-copy directory already exists; refusing overwrite.")
    catalog: dict[str, dict] = {}
    stages = [
        ("00", "当前状态与阅读入口"),
        ("01", "研究计划与创新"),
        ("02", "模型与开发验收"),
        ("03", "独立精度 pilot"),
        ("04", "正式冻结"),
        ("05", "数值修复与恢复"),
        ("06", "正式结果与验收"),
        ("07", "论文写作"),
        ("08", "历史开发附录"),
    ]

    def add(rel: str, stage: str, purpose: str, role: str = "report") -> None:
        rel = Path(rel).as_posix()
        path = ROOT / rel
        if not path.is_file():
            raise FileNotFoundError(path)
        if rel in catalog:
            raise ValueError(f"Duplicate selection: {rel}")
        catalog[rel] = dict(stage=stage, purpose=purpose, role=role)

    def package(rel: str, stage: str, purpose: str) -> None:
        folder = ROOT / rel
        if not folder.is_dir():
            raise FileNotFoundError(folder)
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                add(path.relative_to(ROOT).as_posix(), stage, purpose, "complete_small_package")

    for rel in ["README.md", "project_handoff_20261004.md"]:
        add(rel, "00", "当前正式阶段状态和接续入口；其中历史段落按其日期解释")
    for rel in ["research_plan.md", "innovation_preservation.md", "formal_experiment_protocol.md", "technical_checklist_response_20260927.md"]:
        add(rel, "01", "保留原核心创新、研究设计演变、实验范围和技术落实依据")
    for rel in ["research_engine.md", "ODD_research.md", "signal_and_outcome_contract.md", "revision_validation_20260926.md", "s0_validation_20260928.md", "s1_validation_20260929.md"]:
        add(rel, "02", "现行模型、测量合同、核心恢复与 S0/S1 开发验收")
    for rel in ["outputs/research_s0_acceptance_20260928", "outputs/research_s1_acceptance_20260929"]:
        package(rel, "02", "开发阶段测试、串并行比较与验收的完整小型证据包")
    for rel in ["precision_pilot_protocol_20260930.md", "precision_pilot_validation_20261002.md"]:
        add(rel, "03", "独立 pilot 运行前协议、固定预算和实测验收")
    for rel in ["outputs/precision_pilot_20261002_planning", "outputs/precision_pilot_20261002_acceptance"]:
        package(rel, "03", "独立精度规划及验收；保留 3 项预算风险和 61 项方差不稳定标记")
    for rel in ["formal_execution_protocol_20261003.md", "formal_freeze_validation_20261003.md"]:
        add(rel, "04", "正式固定样本、种子、估计对象、102 项检验和冻结时状态")
    package("outputs/formal_freeze_acceptance_20261003", "04", "原正式冻结验收与测试证据")
    light_names = ["manifest.json", "configuration.json", "inference_spec.json", "seed_registry.json", "seed_audit.json", "artifact_hashes.json"]
    for folder in ["formal_registry_20261003", "formal_registry_repair_v2_20261003"]:
        for name in light_names:
            add(f"outputs/{folder}/{name}", "04", "冻结溯源关键文件；此归档仅保存选集，未包含完整冻结包", "partial_registry_copy")
    for name in ["numeric_repair_policy.json", "repair_context.json"]:
        add(f"outputs/formal_registry_repair_v2_20261003/{name}", "05", "修复 v2 数值边界政策与修复上下文", "partial_registry_copy")
    for rel in ["formal_numeric_repair_protocol_20261003.md", "formal_numeric_repair_resume_protocol_20261003.md", "formal_execution_incident_20261003.md"]:
        add(rel, "05", "保留原失败事实、1 ULP 数值修复边界、中断及恢复过程")
    package("outputs/formal_repair_v2_freeze_acceptance_20261003", "05", "修复 v2 冻结前 279 项测试与登记检查的完整证据包")
    for folder in ["formal_repair_interruption_20261003", "formal_repair_v2_interruption_20261004"]:
        add(f"outputs/{folder}/observation.json", "05", "保留恢复中断的独立观察记录", "evidence")
    for name in ["manifest.json", "failures.json"]:
        add(f"outputs/formal_e2_e4_20261003/{name}", "05", "原始批次失败状态和失败名册；未改写为成功", "partial_batch_copy")
    add("formal_execution_acceptance_20261004.md", "06", "当前 E2–E4 正式批次完成、统计输出、来源与独立复核的总验收")
    for rel in ["outputs/formal_e2_e4_repaired_v2_20261004_analysis", "outputs/formal_e2_e4_repaired_v2_20261004_report", "outputs/formal_repair_v2_retry_execution_20261004", "outputs/formal_release_review_20261004"]:
        package(rel, "06", "已通过正式分析、完整表图、全流程验收或独立复核的小型完整包")
    for name in ["manifest.json", "configuration.json", "failures.json", "recovery_provenance.json"]:
        add(f"outputs/formal_e2_e4_repaired_v2_20261004/{name}", "06", "成功批次标识、配置、零失败和恢复来源；不包含完整原始数据", "partial_batch_copy")
    for name in ["task_result.json", "disable_result.json"]:
        add(f"outputs/formal_repair_v2_task_20261004/{name}", "06", "后台执行成功结束并自禁用的机器记录", "evidence")
    for rel in ["paper_outline_jasss.md", "manuscript_core_revision.md", "manuscript_methods_formal_20261004.md", "manuscript_results_formal_20261004.md", "manuscript_work_20261004/methods_en.md", "manuscript_work_20261004/results_en.md", "manuscript_work_20261004/results_evidence_map.md", "manuscript_work_20261004/methods_evidence_audit.md", "empirical_motivation_protocol.md"]:
        add(rel, "07", "论文结构、中英方法及结果工作稿、证据映射和经验动机边界")
    for rel in ["diagnostic_report.md", "outputs/core_restoration_v040_20260926/core_pilot_report.md", "outputs/response_alignment_v040_20260926/report.md"]:
        add(rel, "08", "历史开发证据；模型版本和测量定义不同，不能合并为正式样本", "historical_report")

    copied = []
    for rel, metadata in catalog.items():
        original = ROOT / rel
        target = COPIES / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        source_hash_before = digest(original)
        shutil.copyfile(original, target)
        target_hash = digest(target)
        source_hash_after = digest(original)
        if source_hash_before != target_hash or source_hash_after != target_hash:
            raise RuntimeError(f"Source changed during copy or byte mismatch: {rel}")
        copied.append(dict(source_relative_path=f"ABM_JASSS/{rel}", archive_relative_path=target.relative_to(ARCHIVE).as_posix(), bytes=target.stat().st_size, sha256=target_hash, **metadata))
    copied.sort(key=lambda row: (row["stage"], row["source_relative_path"]))

    # Markdown link audit is independent: report bytes are deliberately untouched.
    link_records = []
    pattern = re.compile(r"!?\[[^\]\n]*\]\((<[^>]+>|[^\n]+?)\)")
    definition = re.compile(r"^\s*\[[^\]]+\]:\s*(<[^>]+>|\S+)", re.MULTILINE)
    for item in copied:
        if not item["source_relative_path"].lower().endswith(".md"):
            continue
        archive_file = ARCHIVE / item["archive_relative_path"]
        original = ROOT.parent / item["source_relative_path"]
        body = archive_file.read_text(encoding="utf-8")
        for match in list(pattern.finditer(body)) + list(definition.finditer(body)):
            raw = match.group(1).strip()
            target = raw[1:raw.find(">")].strip() if raw.startswith("<") else re.split(r'\s+[\"\']', raw, maxsplit=1)[0]
            line = body.count("\n", 0, match.start()) + 1
            decoded = unquote(target)
            entry = dict(document=item["archive_relative_path"], line=line, target=target)
            if decoded.startswith("#"):
                entry["status"] = "in_document_anchor_not_validated"
            elif re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", decoded) and not re.match(r"^[A-Za-z]:[\\/]", decoded):
                entry["status"] = "external_link_not_checked"
            else:
                local = decoded.split("#", 1)[0].split("?", 1)[0]
                destination = Path(local)
                is_absolute = destination.is_absolute()
                resolved_archive = destination if is_absolute else archive_file.parent / destination
                resolved_source = destination if is_absolute else original.parent / destination
                resolved_archive = resolved_archive.resolve()
                resolved_source = resolved_source.resolve()
                entry["archive_target"] = str(resolved_archive)
                entry["original_target"] = str(resolved_source)
                entry["original_target_exists"] = resolved_source.exists()
                entry["archive_target_exists"] = resolved_archive.exists()
                try:
                    resolved_archive.relative_to(COPIES)
                    contained = True
                except ValueError:
                    contained = False
                entry["archive_contained"] = contained
                if contained and resolved_archive.exists():
                    entry["status"] = "available_in_archive"
                elif is_absolute:
                    entry["status"] = "absolute_reference_outside_archive"
                elif resolved_source.exists():
                    entry["status"] = "source_exists_not_copied"
                else:
                    entry["status"] = "source_target_missing"
            link_records.append(entry)
    status_counts = dict(Counter(item["status"] for item in link_records))
    missing = [row for row in link_records if row["status"] in {"source_exists_not_copied", "source_target_missing", "absolute_reference_outside_archive"}]
    json_new("link_audit.json", dict(scope="Markdown inline and reference-definition links; code-block text may also contain illustrative Markdown links; anchors and external URLs are not validated", source_root=str(ROOT), archive_root=str(ARCHIVE), checked_at_utc=datetime.now(timezone.utc).isoformat(), status_counts=status_counts, unresolved_or_external_local_links=missing, links=link_records))

    now = datetime.now(timezone.utc).isoformat()
    total_bytes = sum(row["bytes"] for row in copied)
    json_new("manifest.json", dict(archive_type="selected_research_report_archive_not_full_replication_package", created_at_utc=now, source_root=str(ROOT), source_files_preserved=True, source_copy_byte_verification="passed", copied_file_count=len(copied), copied_bytes=total_bytes, frozen_registry_copies="selected_files_only; original inventories are provenance indexes, not assertions that all listed source files are included here", raw_data="not included; no raw-data artifact_hashes.json copied", files=copied))
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=["stage", "source_relative_path", "archive_relative_path", "purpose", "role", "bytes", "sha256"], lineterminator="\n")
    writer.writeheader()
    writer.writerows(copied)
    write_new(ARCHIVE / "manifest.csv", "\ufeff" + csv_buffer.getvalue())

    readme = [
        "# 论文形成过程：必要报告归档（2026-10-04）\n",
        "本文件夹汇集论文形成过程中的核心报告、关键验收证据和已完成的正式结果。**E2–E4 正式批次已完成；这不是论文全部完成或已达到投稿条件的声明。**\n",
        "截至本归档所依据的正式验收，1,184 个 α×seed 区组、21,312 个物理终点和 1,000 个独立 seed 已全部通过，失败区组为 0；102 项主分析、532 项辅助结果及 6 幅森林图已经生成。102 项主分析的实际点态 95% 区间半宽均不超过 0.02，45 项通过一次全 102 项 Holm 校正。正式完成时间为 2026-10-04 05:52:11（北京时间）。\n",
        "**仍需另行完成：** E5 动态转变／机制恢复与结构稳健性、E6 信任预警、经验动机配对材料，以及完整英文论文。这里的英文 Methods、Results 是工作稿，不能据此称整篇英文论文完成。试点的 3 项预算风险和 61 项方差不稳定标记仍保留；它们与正式结果的实际精度达标是两个不同阶段的事实。\n",
        "原文件全部保留原处：`D:/UserData/Desktop/ZLS/ABM_JASSS/`。本归档的 `sources/ABM_JASSS/` 按原相对路径复制文件，复制内容逐字节核对 SHA256；未重写报告，也未移动或删改原始资料。历史报告按各自日期和模型版本解释，旧报告中的“尚未运行”等表述不代表当前状态。\n",
        "## 从这里阅读\n",
        "- [正式执行验收](sources/ABM_JASSS/formal_execution_acceptance_20261004.md)：本批次的完成范围、统计口径和复核依据。\n- [最新接续记录](sources/ABM_JASSS/project_handoff_20261004.md)：当前状态与历史恢复路径。\n- [完整中文结果报告](sources/ABM_JASSS/outputs/formal_e2_e4_repaired_v2_20261004_report/report_zh.md)：完整主结果和全部表图入口。\n- [英文方法](sources/ABM_JASSS/manuscript_work_20261004/methods_en.md)与[英文结果](sources/ABM_JASSS/manuscript_work_20261004/results_en.md)：当前论文工作稿。\n",
        "## 归档范围与复现边界\n",
        "此处是报告阅读与核对包，**不是全量复现包**。未复制海量 raw、母状态和动态快照、逐区组输出，也未复制约 34 MB 的正式原始文件哈希清单。完整数据和源码仍在原项目中。源码、模型配置或协议的文中链接可能因此指向未收录的文件；请看独立的 [链接审计](link_audit.json)，不要以报告中的链接存在推断所有文件均已归档。\n",
        "原冻结包和修复 v2 冻结包仅收录 manifest、配置、推断规范、种子及哈希索引等关键文件，**都是不完整副本**；其 `artifact_hashes.json` 是原包的溯源索引，不是本归档已包含所有条目的声明。S0/S1、pilot、原冻结、修复冻结、最终执行、分析、图表及发布复核的小型证据目录按目录整体复制；原始成功／失败批次仅选取标识、失败名册与恢复来源。\n",
        f"共收录 **{len(copied)} 个源文件，{total_bytes:,} 字节（{total_bytes / 1024 / 1024:.2f} MiB）**。逐文件来源、用途、大小与 SHA256 见 [manifest.csv](manifest.csv) 和 [manifest.json](manifest.json)。复制及原文件复核见 [archive_verification.json](archive_verification.json)。\n",
        f"Markdown 链接审计共记录 {len(link_records)} 处链接；{status_counts.get('available_in_archive', 0)} 处本地链接可在归档内找到，{len(missing)} 处本地引用未被归档完整覆盖。逐条列出归档目标、原始目标及原目标是否存在；外部网址和文内锚点不作可达性验证。保留原报告字节优先，不通过改写报告或复制 raw 补齐链接。\n",
        "## 按阶段索引\n",
    ]
    for code, label in stages:
        readme.append(f"### {code} {label}\n")
        rows = [row for row in copied if row["stage"] == code]
        report_rows = [row for row in rows if row["role"] in {"report", "historical_report"}]
        for row in report_rows:
            rel = row["source_relative_path"].removeprefix("ABM_JASSS/")
            readme.append(f"- [{rel}]({row['archive_relative_path']})：{row['purpose']}。\n")
        packages = sorted({str(Path(row["archive_relative_path"]).parent).replace("\\", "/") for row in rows if row["role"] == "complete_small_package"})
        for folder in packages:
            members = [row for row in rows if row["role"] == "complete_small_package" and str(Path(row["archive_relative_path"]).parent).replace("\\", "/") == folder]
            preferred = next((row for name in ["report_zh.md", "report.md", "acceptance.json", "verification.json"] for row in members if Path(row["archive_relative_path"]).name == name), members[0])
            readme.append(f"- [{folder.removeprefix('sources/ABM_JASSS/')}/]({preferred['archive_relative_path']})：完整小型包，{len(members)} 个文件；{preferred['purpose']}。\n")
        selected = [row for row in rows if row["role"] not in {"report", "historical_report", "complete_small_package"}]
        for row in selected:
            rel = row["source_relative_path"].removeprefix("ABM_JASSS/")
            readme.append(f"- [{rel}]({row['archive_relative_path']})：{row['purpose']}。\n")
        readme.append("\n")
    write_new(ARCHIVE / "README.md", "\n".join(readme))

    verification = []
    for row in copied:
        original = ROOT.parent / row["source_relative_path"]
        target = ARCHIVE / row["archive_relative_path"]
        match = digest(original) == row["sha256"] == digest(target)
        verification.append(dict(source_relative_path=row["source_relative_path"], source_and_copy_match=match))
    if not all(row["source_and_copy_match"] for row in verification):
        raise RuntimeError("Final source-and-copy verification failed")
    json_new("archive_verification.json", dict(status="passed", verified_at_utc=datetime.now(timezone.utc).isoformat(), source_copy_count=len(copied), source_copy_bytes=total_bytes, all_source_and_copy_sha256_match=True, original_files_modified=False, source_copy_files=verification, metadata_sha256={name: digest(ARCHIVE / name) for name in ["README.md", "manifest.csv", "manifest.json", "link_audit.json", "build_archive.py"]}))
    print(json.dumps(dict(status="passed", source_copy_count=len(copied), source_copy_bytes=total_bytes, archive=str(ARCHIVE), link_status_counts=status_counts), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
