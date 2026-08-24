"""Validate the completed release package and write machine-readable QA."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUTPUT = HERE / "release_qa.json"
EXPECTED_MODEL_SHA256 = "AB78E6C64AFB6FD487E40A48FBBCD1B09A84EE3FBC9085530F8833DE3543D7EC"
ALPHAS = np.round(np.arange(0.0, 1.0001, 0.05), 2)
SEEDS = np.arange(73000, 73050)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load_model(path: Path):
    spec = importlib.util.spec_from_file_location("release_frozen_model", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load frozen model")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def add(checks: list[dict], check_id: str, passed: bool, detail: str) -> None:
    checks.append(
        {"check_id": check_id, "status": "PASS" if passed else "FAIL", "detail": detail}
    )


def check_required_files(checks: list[dict]) -> None:
    required = [
        "README.md",
        "requirements.txt",
        "01_model_core/model.py",
        "02_experiment_code/run_formal_sensitivity.py",
        "02_experiment_code/analyze_formal_sensitivity.py",
        "02_experiment_code/build_figure_s1_decay.py",
        "02_experiment_code/build_figure_s2_sensitivity.py",
        "05_documents/附录A_B_模型公式与指标.md",
        "05_documents/补充材料S1_外部验证细节.md",
        "05_documents/补充材料S2_敏感性分析.md",
        "05_documents/FIGURE_LEGENDS.md",
        "06_reproducibility/FORMAL_ABLATION_PROVENANCE.md",
        "06_reproducibility/ENVIRONMENT.md",
        "06_reproducibility/release_manifest.csv",
    ]
    missing = [name for name in required if not (ROOT / name).is_file()]
    add(checks, "REQUIRED_FILES", not missing, f"missing={missing}")


def check_model(checks: list[dict]) -> None:
    path = ROOT / "01_model_core" / "model.py"
    digest = sha256(path)
    add(checks, "MODEL_SHA256", digest == EXPECTED_MODEL_SHA256, digest)
    model = load_model(path)
    fields = set(model.SimulationConfig.__dataclass_fields__)
    forbidden = {
        "grid_size",
        "vision_radius",
        "diffusion_probability",
        "diffusion_radius",
        "spatial_coordinate",
    }
    overlap = sorted(fields & forbidden)
    add(checks, "MODEL_SCOPE", not overlap, f"forbidden configuration fields={overlap}")


def expected_panel(frame: pd.DataFrame, id_column: str, expected_ids: int, rows: int) -> tuple[bool, str]:
    duplicate_count = int(frame.duplicated([id_column, "alpha", "seed"]).sum())
    alpha_count = frame["alpha"].nunique()
    seed_count = frame["seed"].nunique()
    cell_counts = frame.groupby([id_column, "alpha"]).size()
    ok = (
        len(frame) == rows
        and frame[id_column].nunique() == expected_ids
        and alpha_count == len(ALPHAS)
        and seed_count == len(SEEDS)
        and duplicate_count == 0
        and bool((cell_counts == len(SEEDS)).all())
    )
    return (
        ok,
        f"rows={len(frame)}, ids={frame[id_column].nunique()}, alphas={alpha_count}, "
        f"seeds={seed_count}, duplicates={duplicate_count}, cell_range="
        f"[{cell_counts.min()},{cell_counts.max()}]",
    )


def check_formal_data(checks: list[dict]) -> None:
    path = ROOT / "03_data" / "formal_ablation" / "raw" / "formal_replicates_5conditions.csv"
    frame = pd.read_csv(path)
    ok, detail = expected_panel(frame, "condition_id", 5, 5250)
    add(checks, "FORMAL_FIVE_CONDITION_DESIGN", ok, detail)


def check_sensitivity_data(checks: list[dict]) -> None:
    raw_path = ROOT / "03_data" / "sensitivity" / "raw" / "sensitivity_replicates.csv"
    raw = pd.read_csv(raw_path)
    ok, detail = expected_panel(raw, "scenario_id", 19, 19950)
    add(checks, "SENSITIVITY_NEW_DESIGN", ok, detail)
    manifest = json.loads(
        (ROOT / "03_data" / "sensitivity" / "raw" / "sensitivity_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    manifest_ok = manifest.get("status") == "complete" and manifest.get("completed_rows") == 19950
    add(
        checks,
        "SENSITIVITY_MANIFEST",
        manifest_ok,
        f"status={manifest.get('status')}, completed_rows={manifest.get('completed_rows')}",
    )
    combined = pd.read_csv(
        ROOT
        / "03_data"
        / "sensitivity"
        / "processed"
        / "sensitivity_combined_analysis_input.csv"
    )
    ok_combined, detail_combined = expected_panel(combined, "scenario_id", 21, 22050)
    add(checks, "SENSITIVITY_COMBINED_DESIGN", ok_combined, detail_combined)
    critical = pd.read_csv(
        ROOT / "03_data" / "sensitivity" / "processed" / "sensitivity_critical_points.csv"
    )
    add(
        checks,
        "SENSITIVITY_CRITICAL_ROWS",
        len(critical) == 21 and critical["scenario_id"].nunique() == 21,
        f"rows={len(critical)}, unique={critical['scenario_id'].nunique()}",
    )


def check_external_data(checks: list[dict]) -> None:
    expected = {
        "news_sentiment_regression_cluster.csv": 17,
        "macro_spearman.csv": 15,
        "macro_regression_hc3.csv": 60,
        "macro_leave_one_out.csv": 15,
        "macro_country_panel.csv": 90,
        "facebook_public_affairs_decay_curve.csv": 72,
        "facebook_public_affairs_article_decay.csv": 27244,
    }
    details = []
    ok = True
    base = ROOT / "03_data" / "external" / "processed"
    for filename, expected_rows in expected.items():
        rows = len(pd.read_csv(base / filename))
        details.append(f"{filename}={rows}")
        ok &= rows == expected_rows
    add(checks, "EXTERNAL_TABLE_ROWS", ok, "; ".join(details))


def check_figures(checks: list[dict]) -> None:
    main = [
        "Fig2_phase_transition",
        "Fig3_critical_point",
        "Fig4_formal_ablation",
        "Fig5_representative_trajectories",
        "Fig6_public_data_validation",
    ]
    supplementary = [
        "FigS_storm_dynamics",
        "FigS_trust_polarization",
        "FigS1_attention_decay",
        "FigS2_formal_sensitivity",
    ]
    missing = []
    dpi_issues = []
    for folder, stems in (("main", main), ("supplementary", supplementary)):
        for stem in stems:
            base = ROOT / "04_figures" / folder / stem
            for suffix in (".svg", ".pdf", ".png", ".tiff"):
                path = base.with_suffix(suffix)
                if not path.is_file() or path.stat().st_size == 0:
                    missing.append(path.relative_to(ROOT).as_posix())
            for suffix in (".png", ".tiff"):
                path = base.with_suffix(suffix)
                if path.is_file():
                    with Image.open(path) as image:
                        dpi = image.info.get("dpi", (0, 0))
                        if min(dpi) < 590:
                            dpi_issues.append(f"{path.name}:{dpi}")
    add(checks, "FIGURE_EXPORT_BUNDLE", not missing, f"missing={missing}")
    add(checks, "FIGURE_RASTER_DPI", not dpi_issues, f"issues={dpi_issues}")


def check_documents(checks: list[dict]) -> None:
    forbidden = ("【运行结果】", "提交前删除", "TODO", "TBD")
    hits = []
    for path in (ROOT / "05_documents").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                hits.append(f"{path.name}:{token}")
    add(checks, "DOCUMENT_PLACEHOLDERS", not hits, f"hits={hits}")


def main() -> int:
    checks: list[dict] = []
    for function in (
        check_required_files,
        check_model,
        check_formal_data,
        check_sensitivity_data,
        check_external_data,
        check_figures,
        check_documents,
    ):
        try:
            function(checks)
        except Exception as error:  # keep a complete QA report
            add(checks, function.__name__.upper(), False, f"{type(error).__name__}: {error}")
    failures = [item for item in checks if item["status"] == "FAIL"]
    payload = {
        "status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "pass_count": len(checks) - len(failures),
        "fail_count": len(failures),
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
