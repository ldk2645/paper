"""Combine the existing four-condition experiment with No trust feedback."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
OUT = HERE.parent
WORKSPACE = OUT.parent
BASE = WORKSPACE / "原始版本" / "formal_ablation_n50_nonspatial"
OLD_RAW = BASE / "raw" / "formal_replicates.csv"
NEW_RAW = OUT / "raw" / "no_trust_replicates.csv"
ANALYZER_PATH = BASE / "analyze_formal_ablation.py"
PROCESSED = OUT / "processed"
CONDITION_IDS = ("full", "no_emotion", "no_drift", "no_response", "no_trust")
ABLATIONS = ("no_emotion", "no_drift", "no_response", "no_trust")


def load_analyzer():
    spec = importlib.util.spec_from_file_location("formal_analyzer_5", ANALYZER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load formal analyzer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.CONDITIONS = ABLATIONS
    return module


analysis = load_analyzer()


def critical_points(frame: pd.DataFrame):
    rows: list[dict] = []
    report = {
        "metric": "mean_agenda_divergence",
        "bootstrap_method": "paired seed-block bootstrap over complete alpha curves",
        "bootstrap_samples": analysis.BOOTSTRAP_CRITICAL,
        "minimum_metric_range": 0.015,
        "conditions": {},
    }
    for order, condition_id in enumerate(CONDITION_IDS):
        subset = frame[frame["condition_id"] == condition_id]
        pivot = subset.pivot(index="seed", columns="alpha", values="mean_agenda_divergence").sort_index().sort_index(axis=1)
        alphas = pivot.columns.to_numpy(float)
        matrix = pivot.to_numpy(float)
        estimate, metric_range, maximum_gradient = analysis.detect_critical(alphas, matrix.mean(axis=0))
        rng = np.random.default_rng(analysis.ANALYSIS_SEED + order * 1000)
        draws = []
        for draw in range(analysis.BOOTSTRAP_CRITICAL):
            indices = rng.integers(0, len(matrix), size=len(matrix))
            candidate, _, _ = analysis.detect_critical(alphas, matrix[indices].mean(axis=0))
            draws.append(candidate)
            rows.append({"condition_id": condition_id, "bootstrap_draw": draw, "critical_alpha": candidate, "identified": candidate is not None})
        identified = np.asarray([value for value in draws if value is not None], float)
        low, high = (np.quantile(identified, [0.025, 0.975], method="nearest") if len(identified) else (np.nan, np.nan))
        report["conditions"][condition_id] = {
            "critical_alpha": estimate,
            "metric_range": metric_range,
            "maximum_internal_gradient": maximum_gradient,
            "identification_rate": len(identified) / analysis.BOOTSTRAP_CRITICAL,
            "bootstrap_ci_95": [float(low), float(high)],
        }
    report["primary_alpha"] = report["conditions"]["full"]["critical_alpha"]
    return report, pd.DataFrame(rows)


def main() -> int:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    old = pd.read_csv(OLD_RAW)
    old["trust_feedback_strength"] = 0.25
    new = pd.read_csv(NEW_RAW)
    common = sorted(set(old.columns).intersection(new.columns))
    combined = pd.concat([old[common], new[common]], ignore_index=True)
    combined["condition_order"] = combined["condition_id"].map({key: index for index, key in enumerate(CONDITION_IDS)})
    combined = combined.sort_values(["condition_order", "alpha", "seed"]).reset_index(drop=True)
    if len(combined) != 5250:
        raise RuntimeError(f"Expected 5,250 rows, found {len(combined):,}")
    combined.to_csv(OUT / "raw" / "formal_replicates_5conditions.csv", index=False, encoding="utf-8")

    summary = analysis.condition_summary(combined)
    critical_meta, critical_draws = critical_points(combined)
    primary_alpha = float(critical_meta["primary_alpha"])
    paired = analysis.paired_effects(combined, primary_alpha)
    auc = analysis.auc_effects(combined)

    summary.to_csv(PROCESSED / "condition_summary_5conditions.csv", index=False, encoding="utf-8-sig")
    paired.to_csv(PROCESSED / "paired_effects_5conditions.csv", index=False, encoding="utf-8-sig")
    auc.to_csv(PROCESSED / "auc_effects_5conditions.csv", index=False, encoding="utf-8-sig")
    critical_draws.to_csv(PROCESSED / "critical_bootstrap_5conditions.csv", index=False, encoding="utf-8-sig")
    (PROCESSED / "critical_points_5conditions.json").write_text(json.dumps(critical_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    no_trust_at_critical = paired[(paired["condition_id"] == "no_trust") & np.isclose(paired["alpha"], primary_alpha)]
    conclusion = {
        "rows": len(combined),
        "conditions": list(CONDITION_IDS),
        "replicates_per_cell": 50,
        "primary_alpha": primary_alpha,
        "full_critical_ci_95": critical_meta["conditions"]["full"]["bootstrap_ci_95"],
        "no_trust_critical": critical_meta["conditions"]["no_trust"],
        "no_trust_effects_at_primary_alpha": no_trust_at_critical.to_dict("records"),
    }
    (PROCESSED / "five_condition_results.json").write_text(json.dumps(conclusion, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "complete", "rows": len(combined), "paired_rows": len(paired), "auc_rows": len(auc), "primary_alpha": primary_alpha}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

