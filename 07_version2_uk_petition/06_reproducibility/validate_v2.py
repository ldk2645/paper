"""Validate Version 2 isolation, data, mechanics and smoke outputs."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
V2_ROOT = HERE.parent
REPOSITORY_ROOT = V2_ROOT.parent
MODEL_DIR = V2_ROOT / "01_model"
OUTPUT = HERE / "release_qa_v2.json"
EXPECTED_V1_SHA256 = (
    "AB78E6C64AFB6FD487E40A48FBBCD1B09A84EE3FBC9085530F8833DE3543D7EC"
)
if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

from model_v2 import MODEL_VERSION, UKPetitionConfig, UKPetitionSimulation  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def add(checks: list[dict[str, str]], check_id: str, passed: bool, detail: str) -> None:
    checks.append(
        {
            "check_id": check_id,
            "status": "PASS" if passed else "FAIL",
            "detail": detail,
        }
    )


def check_version_isolation(checks: list[dict[str, str]]) -> None:
    live = REPOSITORY_ROOT / "01_model_core" / "model.py"
    snapshot = MODEL_DIR / "base_v1.py"
    live_hash = sha256(live)
    snapshot_hash = sha256(snapshot)
    add(
        checks,
        "V1_FROZEN_UNCHANGED",
        live_hash == EXPECTED_V1_SHA256,
        f"sha256={live_hash}",
    )
    add(
        checks,
        "V1_SNAPSHOT_BYTE_IDENTICAL",
        live.read_bytes() == snapshot.read_bytes() and snapshot_hash == live_hash,
        f"live={live_hash}, snapshot={snapshot_hash}",
    )


def check_case_data(checks: list[dict[str, str]]) -> None:
    path = V2_ROOT / "03_data" / "uk_petition_response_delays_222.csv"
    frame = pd.read_csv(path)
    metadata = json.loads(
        (V2_ROOT / "03_data" / "source_metadata.json").read_text(encoding="utf-8")
    )
    delays = frame["response_delay_days"]
    row = frame.loc[frame["petition_id"].eq(700024)]
    valid = (
        list(frame.columns) == ["petition_id", "response_delay_days"]
        and len(frame) == 222
        and frame["petition_id"].nunique() == 222
        and bool(np.isfinite(delays).all())
        and bool((delays > 0).all())
        and len(row) == 1
        and metadata["analysis_filter"]["rows_after_filter"] == 222
        and metadata["version2_minimal_table"]["sha256"] == sha256(path)
        and np.isclose(float(delays.median()), 21.64607628472222)
        and np.isclose(float(row.iloc[0]["response_delay_days"]), 21.793180185185185)
    )
    add(
        checks,
        "CASE_DELAY_DATA",
        valid,
        (
            f"rows={len(frame)}, petitions={frame['petition_id'].nunique()}, "
            f"median={delays.median():.6f}, sha256={sha256(path)}"
        ),
    )


def check_default_timeline(checks: list[dict[str, str]]) -> None:
    config = UKPetitionConfig.case_700024(seed=73000)
    result = UKPetitionSimulation(config).run()
    summary = result.summary
    timeline = (
        summary["response_threshold_step"],
        summary["response_executed_step"],
        summary["debate_threshold_step"],
        summary["petition_close_step"],
    )
    valid = (
        timeline == (14, 36, 177, 182)
        and summary["realized_response_delay_days"] == 22
        and summary["responses_scheduled"] == 1
        and summary["responses_executed"] == 1
        and summary["response_disposition"] == "no_policy_change"
        and summary["response_heat_multiplier"] == 1.0
        and summary["direct_response_trust_signal"] == 0.0
        and len(result.events) == 6
    )
    add(
        checks,
        "DEFAULT_CASE_TIMELINE",
        valid,
        f"timeline={timeline}, events={len(result.events)}",
    )
    petition_id = result.events["petition_id"].astype(str).unique().tolist()
    add(
        checks,
        "ONE_PETITION_ONE_RESPONSE",
        result.events["event_type"].eq("government_response_scheduled").sum() == 1
        and result.events["event_type"].eq("government_response_published").sum() == 1,
        f"petition_ids={petition_id}",
    )


def check_parameter_file(checks: list[dict[str, str]]) -> None:
    path = V2_ROOT / "03_data" / "case_700024_parameters.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    clock = payload["model_clock"]
    defaults = payload["model_defaults"]
    valid = (
        clock["response_threshold_step"] == 14
        and clock["response_delay_days_default"] == 22
        and clock["government_response_step_default"] == 36
        and defaults["response_heat_multiplier"] == 1.0
        and defaults["direct_response_trust_signal"] == 0.0
    )
    add(checks, "CASE_PARAMETER_FILE", valid, f"model_version={MODEL_VERSION}")


def check_smoke_outputs(checks: list[dict[str, str]]) -> None:
    base = V2_ROOT / "05_outputs" / "smoke"
    summary = pd.read_csv(base / "v2_run_summaries.csv")
    events = pd.read_csv(base / "v2_event_log.csv")
    manifest = json.loads((base / "v2_run_manifest.json").read_text(encoding="utf-8"))
    key = ["condition_id", "alpha", "seed"]
    fixed = {
        "v1_reference_3": 3,
        "conditional_p05_11": 11,
        "case_typical_22": 22,
        "conditional_p95_57": 57,
    }
    fixed_ok = all(
        summary.loc[summary["condition_id"].eq(name), "response_delay_days"].eq(delay).all()
        for name, delay in fixed.items()
    )
    empirical = summary[
        summary["condition_id"].eq("conditional_empirical_resample")
    ]
    hash_columns_match = (
        summary["v1_parent_sha256"].eq(manifest["v1_parent_sha256"]).all()
        and summary["v2_model_sha256"].eq(manifest["v2_model_sha256"]).all()
        and summary["runner_sha256"].eq(manifest["runner_sha256"]).all()
        and summary["delay_data_sha256"].eq(manifest["delay_data_sha256"]).all()
        and summary["run_signature"].eq(manifest["run_signature"]).all()
    )
    valid = (
        len(summary) == 15
        and summary["condition_id"].nunique() == 5
        and summary["alpha"].nunique() == 3
        and summary["seed"].nunique() == 1
        and not summary.duplicated(key).any()
        and fixed_ok
        and bool((empirical.groupby("seed")["response_delay_days"].nunique() == 1).all())
        and bool(summary["responses_scheduled"].eq(1).all())
        and bool(summary["responses_executed"].eq(1).all())
        and len(events) == 90
        and manifest["evidence_status"] == "smoke_only_not_formal_evidence"
        and manifest["completed_rows"] == 15
        and hash_columns_match
    )
    add(
        checks,
        "SMOKE_DESIGN",
        valid,
        f"runs={len(summary)}, events={len(events)}, duplicates={summary.duplicated(key).sum()}",
    )


def check_formal_outputs(checks: list[dict[str, str]]) -> str:
    base = V2_ROOT / "05_outputs" / "formal"
    summary_path = base / "v2_run_summaries.csv"
    events_path = base / "v2_event_log.csv"
    manifest_path = base / "v2_run_manifest.json"
    version = json.loads((V2_ROOT / "VERSION.json").read_text(encoding="utf-8"))
    declared = version["formal_experiment_status"]
    if not summary_path.exists() and not events_path.exists() and not manifest_path.exists():
        valid = declared == "not_run"
        add(
            checks,
            "FORMAL_OUTPUT_STATUS",
            valid,
            f"actual=not_run, VERSION.json={declared}",
        )
        return "not_run"

    if not (summary_path.is_file() and events_path.is_file() and manifest_path.is_file()):
        add(
            checks,
            "FORMAL_OUTPUT_STATUS",
            False,
            "formal output set is incomplete",
        )
        return "incomplete"

    summary = pd.read_csv(summary_path)
    events = pd.read_csv(events_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    key = ["condition_id", "alpha", "seed"]
    fixed = {
        "v1_reference_3": 3,
        "conditional_p05_11": 11,
        "case_typical_22": 22,
        "conditional_p95_57": 57,
    }
    fixed_ok = all(
        summary.loc[summary["condition_id"].eq(name), "response_delay_days"].eq(delay).all()
        for name, delay in fixed.items()
    )
    empirical = summary[
        summary["condition_id"].eq("conditional_empirical_resample")
    ]
    cell_sizes = summary.groupby(["condition_id", "alpha"]).size()
    hash_columns_match = (
        summary["v1_parent_sha256"].eq(manifest["v1_parent_sha256"]).all()
        and summary["v2_model_sha256"].eq(manifest["v2_model_sha256"]).all()
        and summary["runner_sha256"].eq(manifest["runner_sha256"]).all()
        and summary["delay_data_sha256"].eq(manifest["delay_data_sha256"]).all()
        and summary["run_signature"].eq(manifest["run_signature"]).all()
    )
    valid = (
        len(summary) == 5_250
        and summary["condition_id"].nunique() == 5
        and summary["alpha"].nunique() == 21
        and summary["seed"].nunique() == 50
        and not summary.duplicated(key).any()
        and bool(cell_sizes.eq(50).all())
        and fixed_ok
        and bool((empirical.groupby("seed")["response_delay_days"].nunique() == 1).all())
        and bool(summary["responses_scheduled"].eq(1).all())
        and bool(summary["responses_executed"].eq(1).all())
        and len(events) == 31_500
        and manifest["status"] == "complete"
        and manifest["scope"] == "formal"
        and manifest["evidence_status"] == "formal_design"
        and manifest["completed_rows"] == 5_250
        and manifest["event_rows"] == 31_500
        and hash_columns_match
        and declared == "complete"
    )
    add(
        checks,
        "FORMAL_OUTPUT_STATUS",
        valid,
        (
            f"actual=present, runs={len(summary)}, events={len(events)}, "
            f"duplicates={summary.duplicated(key).sum()}, VERSION.json={declared}"
        ),
    )
    return "complete" if valid else "invalid"


def check_documents(checks: list[dict[str, str]]) -> None:
    forbidden = ("TODO", "TBD", "【运行结果】", "提交前删除")
    hits = []
    for path in V2_ROOT.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                hits.append(f"{path.relative_to(V2_ROOT).as_posix()}:{token}")
    add(checks, "DOCUMENT_PLACEHOLDERS", not hits, f"hits={hits}")


def check_formal_analysis(checks: list[dict[str, str]]) -> None:
    base = V2_ROOT / "05_outputs" / "formal"
    descriptive_path = base / "v2_formal_descriptive.csv"
    paired_path = base / "v2_formal_paired_vs_typical22.csv"
    pooled_path = base / "v2_formal_pooled_delay_effects.csv"
    report_path = base / "V2_FORMAL_RESULTS.md"
    required = (descriptive_path, paired_path, pooled_path, report_path)
    if not all(path.is_file() for path in required):
        add(checks, "FORMAL_ANALYSIS", False, "formal analysis output set is incomplete")
        return

    descriptive = pd.read_csv(descriptive_path)
    paired = pd.read_csv(paired_path)
    pooled = pd.read_csv(pooled_path)
    report = report_path.read_text(encoding="utf-8")
    significant = paired[paired["paired_t_p_holm_21alpha"].lt(0.05)]
    valid = (
        len(descriptive) == 5 * 21 * 7
        and len(paired) == 4 * 21 * 7
        and len(pooled) == 4 * 7
        and not descriptive.duplicated(["condition_id", "alpha", "outcome"]).any()
        and not paired.duplicated(["condition_id", "alpha", "outcome"]).any()
        and not pooled.duplicated(["condition_id", "outcome"]).any()
        and paired["n_seed_blocks"].eq(50).all()
        and pooled["n_seed_blocks"].eq(50).all()
        and len(significant) == 63
        and significant["outcome"].eq("petition_heat_auc_post_7_days").all()
        and len(pooled[pooled["outcome"].eq("mean_trust")]) == 4
        and "不是“回应相对于不回应”的效应" in report
    )
    add(
        checks,
        "FORMAL_ANALYSIS",
        valid,
        (
            f"descriptive={len(descriptive)}, paired={len(paired)}, "
            f"pooled={len(pooled)}, corrected_significant={len(significant)}"
        ),
    )


def main() -> int:
    checks: list[dict[str, str]] = []
    for function in (
        check_version_isolation,
        check_case_data,
        check_default_timeline,
        check_parameter_file,
        check_smoke_outputs,
    ):
        try:
            function(checks)
        except Exception as error:
            add(
                checks,
                function.__name__.upper(),
                False,
                f"{type(error).__name__}: {error}",
            )
    try:
        formal_status = check_formal_outputs(checks)
    except Exception as error:
        formal_status = "invalid"
        add(
            checks,
            "CHECK_FORMAL_OUTPUTS",
            False,
            f"{type(error).__name__}: {error}",
        )
    try:
        check_documents(checks)
    except Exception as error:
        add(
            checks,
            "CHECK_DOCUMENTS",
            False,
            f"{type(error).__name__}: {error}",
        )
    try:
        check_formal_analysis(checks)
    except Exception as error:
        add(
            checks,
            "CHECK_FORMAL_ANALYSIS",
            False,
            f"{type(error).__name__}: {error}",
        )
    failures = [item for item in checks if item["status"] == "FAIL"]
    payload = {
        "status": "PASS" if not failures else "FAIL",
        "model_version": MODEL_VERSION,
        "formal_experiment_status": formal_status,
        "smoke_outputs_are_formal_evidence": False,
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
