"""Independent structural and statistical QA for the non-spatial ablation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image


HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
PROCESSED = HERE / "processed"
FIGURES = HERE / "figures"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    raw_path = RAW / "formal_replicates.csv"
    manifest_path = RAW / "formal_manifest.json"
    raw = pd.read_csv(raw_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = pd.read_csv(PROCESSED / "condition_summary.csv")
    effects = pd.read_csv(PROCESSED / "paired_effects.csv")
    auc = pd.read_csv(PROCESSED / "auc_effects.csv")
    critical = json.loads(
        (PROCESSED / "critical_points.json").read_text(encoding="utf-8")
    )
    critical_bootstrap = pd.read_csv(PROCESSED / "critical_bootstrap.csv")
    audit = json.loads(
        (PROCESSED / "original_version_audit.json").read_text(encoding="utf-8")
    )
    verification = json.loads(
        (PROCESSED / "unified_model_verification.json").read_text(encoding="utf-8")
    )

    check("manifest_complete", manifest.get("status") == "complete", str(manifest.get("status")))
    check("raw_row_count", len(raw) == 4200, f"rows={len(raw)}")
    check(
        "manifest_row_count",
        manifest.get("completed_rows") == 4200 and manifest.get("expected_rows") == 4200,
        f"completed={manifest.get('completed_rows')}, expected={manifest.get('expected_rows')}",
    )
    check(
        "primary_key_unique",
        not raw.duplicated(["condition_id", "alpha", "seed"]).any(),
        f"duplicates={int(raw.duplicated(['condition_id', 'alpha', 'seed']).sum())}",
    )
    expected_conditions = {"full", "no_emotion", "no_drift", "no_response"}
    check(
        "condition_set",
        set(raw["condition_id"]) == expected_conditions,
        str(sorted(raw["condition_id"].unique())),
    )
    expected_alphas = np.round(np.arange(0.0, 1.0001, 0.05), 2)
    observed_alphas = np.sort(raw["alpha"].unique())
    check(
        "alpha_grid",
        len(observed_alphas) == 21 and np.allclose(observed_alphas, expected_alphas),
        f"count={len(observed_alphas)}, min={observed_alphas.min()}, max={observed_alphas.max()}",
    )
    cell_sizes = raw.groupby(["condition_id", "alpha"]).size()
    check(
        "cell_count_and_n50",
        len(cell_sizes) == 84 and set(cell_sizes) == {50},
        f"cells={len(cell_sizes)}, sizes={sorted(cell_sizes.unique())}",
    )
    expected_seeds = set(range(73000, 73050))
    seed_sets_valid = all(
        set(group["seed"].astype(int)) == expected_seeds
        for _, group in raw.groupby(["condition_id", "alpha"])
    )
    check("common_seed_sets", seed_sets_valid, "expected seeds 73000-73049 in every cell")
    check(
        "run_signature_unique",
        raw["run_signature"].nunique() == 1
        and raw["run_signature"].iloc[0] == manifest["run_signature"],
        f"unique={raw['run_signature'].nunique()}",
    )
    check(
        "configuration_hash_unique",
        raw["configuration_sha256"].nunique() == 4200,
        f"unique={raw['configuration_sha256'].nunique()}",
    )
    numeric = raw.select_dtypes(include=[np.number]).to_numpy(dtype=float)
    check("raw_numeric_finite", bool(np.isfinite(numeric).all()), f"numeric_cells={numeric.size}")
    check(
        "simulation_scale",
        set(raw["population_size"]) == {300} and set(raw["steps"]) == {300},
        f"population={sorted(raw['population_size'].unique())}, steps={sorted(raw['steps'].unique())}",
    )
    spatial_terms = ("grid", "vision", "diffusion", "coordinate", "spatial")
    spatial_columns = [
        column for column in raw.columns if any(term in column.lower() for term in spatial_terms)
    ]
    baseline_keys = set(manifest["baseline_config"])
    spatial_manifest_keys = sorted(
        key for key in baseline_keys if any(term in key.lower() for term in spatial_terms)
    )
    check(
        "nonspatial_design",
        not spatial_columns and not spatial_manifest_keys
        and manifest.get("model_family") == "original_nonspatial_global_information_pool",
        f"raw={spatial_columns}, manifest={spatial_manifest_keys}",
    )
    no_emotion = raw[raw["condition_id"] == "no_emotion"]
    no_drift = raw[raw["condition_id"] == "no_drift"]
    no_response = raw[raw["condition_id"] == "no_response"]
    full = raw[raw["condition_id"] == "full"]
    check(
        "condition_switches",
        set(no_emotion["emotion_advantage_enabled"].astype(bool)) == {False}
        and set(full["emotion_advantage_enabled"].astype(bool)) == {True}
        and set(no_drift["preference_drift_rate"]) == {0.0}
        and set(no_response["response_strength"]) == {1.0},
        "emotion=False; drift_rate=0; response_strength=1",
    )
    check(
        "unified_model_verification",
        verification.get("status") == "PASS"
        and verification.get("full_model_exact_match") is True,
        json.dumps(verification, ensure_ascii=False),
    )
    check(
        "original_audit_complete",
        audit.get("audit_status") == "complete" and len(audit.get("findings", [])) >= 8,
        f"findings={len(audit.get('findings', []))}",
    )
    check("summary_shape", len(summary) == 336, f"rows={len(summary)}")
    check("paired_effect_shape", len(effects) == 252, f"rows={len(effects)}")
    check("auc_shape", len(auc) == 12, f"rows={len(auc)}")
    check(
        "critical_bootstrap_shape",
        len(critical_bootstrap) == 20000,
        f"rows={len(critical_bootstrap)}",
    )
    check(
        "critical_conditions_and_primary",
        set(critical["conditions"]) == expected_conditions
        and critical.get("primary_alpha") in set(expected_alphas),
        f"primary={critical.get('primary_alpha')}",
    )
    effect_ci_valid = (
        np.isfinite(effects[["bootstrap_ci_low", "bootstrap_ci_high"]]).all().all()
        and (effects["bootstrap_ci_low"] <= effects["bootstrap_ci_high"]).all()
    )
    auc_ci_valid = (
        np.isfinite(auc[["bootstrap_ci_low", "bootstrap_ci_high"]]).all().all()
        and (auc["bootstrap_ci_low"] <= auc["bootstrap_ci_high"]).all()
    )
    check("confidence_intervals_valid", bool(effect_ci_valid and auc_ci_valid), "effect and AUC CIs ordered")
    primary = effects[effects["is_primary_alpha"].astype(bool)]
    check(
        "primary_family_complete",
        len(primary) == 12
        and primary[
            [
                "holm_t_p_primary_global",
                "holm_wilcoxon_p_primary_global",
                "holm_signflip_p_primary_global",
            ]
        ].notna().all().all(),
        f"rows={len(primary)}",
    )
    p_columns = [
        "holm_t_p_global",
        "holm_wilcoxon_p_global",
        "holm_signflip_p_global",
    ]
    check(
        "auc_multiplicity_complete",
        auc[p_columns].notna().all().all()
        and ((auc[p_columns] >= 0) & (auc[p_columns] <= 1)).all().all(),
        "12 AUC comparisons with bounded Holm-adjusted p-values",
    )
    check(
        "raw_hash_linkage",
        critical.get("raw_sha256") == sha256(raw_path)
        and critical.get("manifest_sha256") == sha256(manifest_path),
        "analysis metadata matches raw and manifest files",
    )

    required_files = [
        HERE / "原始版本审计与非空间正式消融报告.md",
        FIGURES / "Fig_formal_ablation_nonspatial.png",
        FIGURES / "Fig_formal_ablation_nonspatial.pdf",
        FIGURES / "Fig_formal_ablation_nonspatial.svg",
    ]
    check(
        "required_outputs_present",
        all(path.exists() and path.stat().st_size > 0 for path in required_files),
        "; ".join(f"{path.name}:{path.stat().st_size if path.exists() else 0}" for path in required_files),
    )
    png_path = FIGURES / "Fig_formal_ablation_nonspatial.png"
    if png_path.exists():
        with Image.open(png_path) as image:
            width, height = image.size
        figure_ok = width >= 2400 and height >= 1600
        figure_detail = f"{width}x{height}"
    else:
        figure_ok = False
        figure_detail = "missing"
    check("figure_resolution", figure_ok, figure_detail)
    report_path = HERE / "原始版本审计与非空间正式消融报告.md"
    report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    check(
        "report_sections",
        all(
            heading in report_text
            for heading in (
                "## 二、原始版本审计",
                "## 四、临界点结果",
                "## 五、",
                "## 六、全α曲线AUC结果",
                "## 七、解释边界",
            )
        ),
        f"characters={len(report_text)}",
    )

    failed = [item for item in checks if not item["passed"]]
    file_hashes = {
        str(path.relative_to(HERE)).replace("\\", "/"): sha256(path)
        for path in HERE.rglob("*")
        if path.is_file()
        and path.name not in {"qa_report.json", "QA.md"}
        and "__pycache__" not in path.parts
    }
    payload = {
        "status": "PASS" if not failed else "FAIL",
        "check_count": len(checks),
        "failed_count": len(failed),
        "checks": checks,
        "file_sha256": file_hashes,
    }
    (HERE / "qa_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown = [
        "# 非空间正式消融 QA",
        "",
        f"结论：**{payload['status']}**",
        "",
        f"共执行 {len(checks)} 项检查，失败 {len(failed)} 项。",
        "",
        "|检查|结果|说明|",
        "|---|---|---|",
    ]
    for item in checks:
        detail = str(item["detail"]).replace("|", "\\|").replace("\n", " ")
        markdown.append(
            f"|`{item['name']}`|{'PASS' if item['passed'] else 'FAIL'}|{detail}|"
        )
    (HERE / "QA.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print(f"QA {payload['status']}: {len(checks)} checks, {len(failed)} failures")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

