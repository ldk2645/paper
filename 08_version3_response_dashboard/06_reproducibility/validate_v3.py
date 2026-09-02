"""Validate the isolated Version 3 model, pilot, index demo and figure bundle."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image


HERE = Path(__file__).resolve().parent
V3_ROOT = HERE.parent
REPOSITORY_ROOT = V3_ROOT.parent
OUTPUT = HERE / "release_qa_v3.json"
EXPECTED_V1 = "AB78E6C64AFB6FD487E40A48FBBCD1B09A84EE3FBC9085530F8833DE3543D7EC"
EXPECTED_V2 = "83BCD501B5A22C59832CC5441FFDF1054361E46C75E1BEE39F70E8E8CA0FC8DF"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def add(
    checks: list[dict[str, str]], check_id: str, passed: bool, detail: str
) -> None:
    checks.append(
        {
            "check_id": check_id,
            "status": "PASS" if passed else "FAIL",
            "detail": detail,
        }
    )


def check_version_isolation(checks: list[dict[str, str]]) -> None:
    live_v1 = REPOSITORY_ROOT / "01_model_core" / "model.py"
    live_v2 = REPOSITORY_ROOT / "07_version2_uk_petition" / "01_model" / "model_v2.py"
    copy_v1 = V3_ROOT / "01_model" / "base_v1.py"
    copy_v2 = V3_ROOT / "01_model" / "base_v2.py"
    valid = (
        sha256(live_v1) == EXPECTED_V1
        and sha256(copy_v1) == EXPECTED_V1
        and live_v1.read_bytes() == copy_v1.read_bytes()
        and sha256(live_v2) == EXPECTED_V2
        and sha256(copy_v2) == EXPECTED_V2
        and live_v2.read_bytes() == copy_v2.read_bytes()
    )
    add(
        checks,
        "PARENT_SNAPSHOTS",
        valid,
        f"v1={sha256(copy_v1)}, v2={sha256(copy_v2)}",
    )


def check_identity_and_hashes(checks: list[dict[str, str]]) -> None:
    version = json.loads((V3_ROOT / "VERSION.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (V3_ROOT / "05_outputs" / "pilot" / "v3_pilot_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    model_hash = sha256(V3_ROOT / "01_model" / "model_v3.py")
    runner_hash = sha256(V3_ROOT / "02_experiment_code" / "run_v3_experiment.py")
    valid = (
        version["version"] == "3.0.0-response-dashboard-pilot"
        and version["pilot"]["model_sha256"] == model_hash
        and manifest["v3_model_sha256"] == model_hash
        and manifest["runner_sha256"] == runner_hash
        and manifest["v1_parent_sha256"] == EXPECTED_V1
        and manifest["v2_parent_sha256"] == EXPECTED_V2
        and version["formal_experiment"]["status"] == "not_run"
    )
    add(
        checks,
        "IDENTITY_AND_HASHES",
        valid,
        f"model={model_hash}, runner={runner_hash}",
    )


def check_pilot_panel(checks: list[dict[str, str]]) -> None:
    base = V3_ROOT / "05_outputs" / "pilot"
    summary = pd.read_csv(base / "v3_pilot_run_summaries.csv")
    steps = pd.read_csv(base / "v3_pilot_step_metrics.csv")
    events = pd.read_csv(base / "v3_pilot_event_log.csv")
    manifest = json.loads((base / "v3_pilot_manifest.json").read_text(encoding="utf-8"))
    key = [
        "delay_condition_id",
        "response_heat_condition_id",
        "alpha",
        "seed",
    ]
    cell_sizes = summary.groupby(
        ["delay_condition_id", "response_heat_condition_id", "alpha"]
    ).size()
    reduction_070 = summary[summary["response_heat_multiplier"].eq(0.70)][
        "realized_heat_reduction_fraction"
    ]
    reduction_100 = summary[summary["response_heat_multiplier"].eq(1.00)][
        "realized_heat_reduction_fraction"
    ]
    execution_days = {
        int(delay): sorted(int(value) for value in group["response_executed_step"].unique())
        for delay, group in summary.groupby("response_delay_days")
    }
    valid = (
        len(summary) == 120
        and len(steps) == 36_000
        and len(events) == 36_720
        and not summary.duplicated(key).any()
        and bool(cell_sizes.eq(10).all())
        and set(summary["alpha"]) == {0.4, 0.6, 0.8}
        and set(summary["seed"]) == set(range(73000, 73010))
        and set(summary["response_delay_days"]) == {11, 57}
        and set(summary["response_heat_multiplier"]) == {0.7, 1.0}
        and bool(summary["routine_government_posts_published"].eq(300).all())
        and bool(summary["response_government_posts_published"].eq(1).all())
        and bool(summary["responses_executed"].eq(1).all())
        and bool(np.allclose(reduction_070, 0.30))
        and bool(np.allclose(reduction_100, 0.0))
        and execution_days == {11: [25], 57: [71]}
        and manifest["completed_runs"] == 120
        and manifest["step_rows"] == 36_000
        and manifest["event_rows"] == 36_720
        and manifest["evidence_status"] == "exploratory_pilot_not_formal_evidence"
    )
    add(
        checks,
        "PILOT_FACTORIAL_PANEL",
        valid,
        (
            f"runs={len(summary)}, steps={len(steps)}, events={len(events)}, "
            f"cell_sizes={sorted(cell_sizes.unique())}"
        ),
    )

    routine_events = events[events["event_type"].eq(
        "routine_government_information_published"
    )]
    response_events = events[events["event_type"].eq("government_response_published")]
    event_valid = (
        bool(routine_events.groupby("run_id").size().eq(300).all())
        and bool(response_events.groupby("run_id").size().eq(1).all())
        and routine_events["run_id"].nunique() == 120
        and response_events["run_id"].nunique() == 120
    )
    add(
        checks,
        "DAILY_PUBLICATION_EVENT_AUDIT",
        event_valid,
        f"routine={len(routine_events)}, responses={len(response_events)}",
    )

    compare_columns = [
        "petition_heat",
        "mean_trust",
        "agenda_divergence",
        "routine_government_attention_share",
        "hotspot_demand_misalignment",
    ]
    pre = steps[
        steps["step"]
        < steps["response_delay_days"].map({11: 25, 57: 71})
    ]
    pivot = pre.pivot(
        index=["alpha", "seed", "delay_condition_id", "step"],
        columns="response_heat_multiplier",
        values=compare_columns,
    )
    pre_valid = all(
        np.allclose(pivot[(column, 0.7)], pivot[(column, 1.0)])
        for column in compare_columns
    )
    add(
        checks,
        "COMMON_SEED_PRE_RESPONSE",
        pre_valid,
        f"paired_pre_response_rows={len(pivot)}",
    )


def check_statistics(checks: list[dict[str, str]]) -> None:
    base = V3_ROOT / "05_outputs" / "pilot"
    paired = pd.read_csv(base / "v3_pilot_paired_effects.csv")
    interactions = pd.read_csv(base / "v3_pilot_timing_interactions.csv")
    statistics = pd.read_csv(base / "v3_pilot_statistics.csv")
    source = pd.read_csv(base / "v3_figure_source_data.csv")
    primary = statistics[
        statistics["metric_id"].eq("primary_log1p_post14_heat_auc")
        & statistics["contrast_type"].eq(
            "timing_interaction_cooling_early_minus_late"
        )
        & statistics["alpha_scope"].eq(
            "pooled_equal_weight_0.40_0.60_0.80"
        )
    ]
    if len(primary) != 1:
        valid = False
        detail = f"primary_rows={len(primary)}"
    else:
        row = primary.iloc[0]
        valid = (
            len(paired) == 420
            and len(interactions) == 210
            and len(statistics) == 98
            and len(source) == 111
            and np.isclose(row["estimate"], -0.004860, atol=1e-6)
            and np.isclose(row["bootstrap_ci_low"], -0.041354, atol=1e-6)
            and np.isclose(row["bootstrap_ci_high"], 0.030156, atol=1e-6)
            and np.isclose(row["exact_sign_flip_p"], 0.80078125)
            and row["bootstrap_ci_low"] < 0 < row["bootstrap_ci_high"]
            and statistics["evidence_status"].eq(
                "pilot_only_not_formal_evidence"
            ).all()
        )
        detail = (
            f"paired={len(paired)}, interactions={len(interactions)}, "
            f"stats={len(statistics)}, pooled={row['estimate']:.6f}, "
            f"p={row['exact_sign_flip_p']:.8f}"
        )
    add(checks, "PILOT_STATISTICS", valid, detail)


def check_external_demo(checks: list[dict[str, str]]) -> None:
    base = V3_ROOT / "05_outputs" / "external_index_demo"
    metadata = json.loads(
        (base / "hotspot_demand_index_metadata.json").read_text(encoding="utf-8")
    )
    paths = [
        base / "rolling_topic_distributions.csv",
        base / "hotspot_demand_index.csv",
        base / "topic_visibility_gap.csv",
    ]
    frames = [pd.read_csv(path) for path in paths]
    valid = (
        metadata["data_scope"] == "synthetic"
        and metadata["network_access"] == "none"
        and "not a real" in metadata["evidence_warning"]
        and all("data_scope" in frame.columns for frame in frames)
        and all(frame["data_scope"].eq("synthetic").all() for frame in frames)
        and len(frames[1]) == 1
        and frames[1]["alignment_hd"].between(0.0, 100.0).all()
        and frames[1]["blind_spot_tv"].between(0.0, 100.0).all()
    )
    add(
        checks,
        "EXTERNAL_INDEX_SYNTHETIC_ONLY",
        valid,
        f"scope={metadata['data_scope']}, rows={[len(frame) for frame in frames]}",
    )


def check_figure_bundle(checks: list[dict[str, str]]) -> None:
    base = V3_ROOT / "04_figures" / "Figure_V3_response_pilot"
    svg = base.with_suffix(".svg")
    pdf = base.with_suffix(".pdf")
    png = base.with_suffix(".png")
    tiff = base.with_suffix(".tiff")
    source = base.with_name(base.name + "_source_data.csv")
    files_ok = all(path.is_file() and path.stat().st_size > 0 for path in (svg, pdf, png, tiff, source))
    svg_text = svg.read_text(encoding="utf-8") if svg.exists() else ""
    png_info = Image.open(png) if png.exists() else None
    tiff_info = Image.open(tiff) if tiff.exists() else None
    source_rows = pd.read_csv(source) if source.exists() else pd.DataFrame()
    valid = (
        files_ok
        and pdf.read_bytes().startswith(b"%PDF-")
        and svg_text.count("<text") == 60
        and "font-family" in svg_text
        and png_info is not None
        and tiff_info is not None
        and png_info.size == (4322, 3236)
        and tiff_info.size == (4322, 3236)
        and len(source_rows) == 265
        and source_rows["evidence_status"].eq(
            "pilot_only_not_formal_evidence"
        ).all()
    )
    add(
        checks,
        "FIGURE_BUNDLE",
        valid,
        f"svg_text={svg_text.count('<text')}, source_rows={len(source_rows)}",
    )


def check_documents(checks: list[dict[str, str]]) -> None:
    required = [
        V3_ROOT / "README.md",
        V3_ROOT / "CHANGELOG_FROM_V2.md",
        V3_ROOT / "05_documents" / "MODEL_CARD_V3.md",
        V3_ROOT / "05_documents" / "EXTERNAL_INDEX_GUIDE.md",
        V3_ROOT / "04_figures" / "Figure_V3_response_pilot_caption.md",
        V3_ROOT / "04_figures" / "FIGURE_QA_V3.md",
    ]
    forbidden = ("TODO", "TBD", "提交前删除", "外部验证完成")
    hits: list[str] = []
    for path in V3_ROOT.rglob("*.md"):
        content = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in content:
                hits.append(f"{path.relative_to(V3_ROOT)}:{token}")
    valid = all(path.is_file() and path.stat().st_size > 0 for path in required) and not hits
    add(checks, "DOCUMENTATION", valid, f"required={len(required)}, hits={hits}")


def main() -> int:
    checks: list[dict[str, str]] = []
    functions = (
        check_version_isolation,
        check_identity_and_hashes,
        check_pilot_panel,
        check_statistics,
        check_external_demo,
        check_figure_bundle,
        check_documents,
    )
    for function in functions:
        try:
            function(checks)
        except Exception as error:
            add(
                checks,
                function.__name__.upper(),
                False,
                f"{type(error).__name__}: {error}",
            )
    failures = [row for row in checks if row["status"] == "FAIL"]
    payload = {
        "status": "PASS" if not failures else "FAIL",
        "model_version": "3.0.0-response-dashboard-pilot",
        "pilot_evidence_status": "exploratory_not_formal",
        "formal_experiment_status": "not_run",
        "external_index_status": "synthetic_demo_only_not_external_validation",
        "pass_count": len(checks) - len(failures),
        "fail_count": len(failures),
        "checks": checks,
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
