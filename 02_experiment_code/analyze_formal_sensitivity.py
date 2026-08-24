"""Analyze the formal non-spatial sensitivity experiment.

The analysis keeps the 50 common random seeds paired across the 21 alpha
values.  It combines the newly generated sensitivity runs with the frozen
full-model and no-response runs from the formal five-condition experiment.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
NEW_RAW = PACKAGE / "03_data" / "sensitivity" / "raw" / "sensitivity_replicates.csv"
FORMAL_RAW = (
    PACKAGE
    / "03_data"
    / "formal_ablation"
    / "raw"
    / "formal_replicates_5conditions.csv"
)
OUT = PACKAGE / "03_data" / "sensitivity" / "processed"

ALPHAS = np.round(np.arange(0.0, 1.0001, 0.05), 2)
SEEDS = np.arange(73000, 73050)
METRICS = (
    "mean_agenda_divergence",
    "system_stability",
    "storm_time_share",
    "mean_trust",
)
CRITICAL_METRIC = "mean_agenda_divergence"
PRIMARY_ALPHA = 0.60
BOOTSTRAP_SAMPLES = 5000
ANALYSIS_SEED = 20260824


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def holm_adjust(values: pd.Series) -> pd.Series:
    array = values.to_numpy(float)
    result = np.full(len(array), np.nan)
    finite = np.flatnonzero(np.isfinite(array))
    order = finite[np.argsort(array[finite])]
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(order) - rank) * array[index])
        result[index] = min(1.0, running)
    return pd.Series(result, index=values.index)


def detect_critical(
    alphas: np.ndarray,
    values: np.ndarray,
    minimum_range: float = 0.015,
) -> tuple[float | None, float, float]:
    """Match the registered three-point smoothing/maximum-gradient rule."""
    if len(alphas) < 3 or not np.all(np.isfinite(values)):
        return None, float("nan"), float("nan")
    metric_range = float(np.ptp(values))
    if metric_range < minimum_range:
        return None, metric_range, float("nan")
    # Exact NumPy equivalent of pandas rolling(window=3, center=True,
    # min_periods=1): two-point means at the boundaries and three-point means
    # internally.  This path is used hundreds of thousands of times during
    # seed-block bootstrap and avoids changing the registered estimator.
    smoothed = np.empty_like(values, dtype=float)
    smoothed[0] = (values[0] + values[1]) / 2.0
    smoothed[-1] = (values[-2] + values[-1]) / 2.0
    smoothed[1:-1] = (values[:-2] + values[1:-1] + values[2:]) / 3.0
    gradients = np.gradient(smoothed, alphas)
    internal = np.arange(1, len(alphas) - 1)
    index = int(internal[np.argmax(gradients[internal])])
    maximum_gradient = float(gradients[index])
    if maximum_gradient <= 0:
        return None, metric_range, maximum_gradient
    return float(alphas[index]), metric_range, maximum_gradient


def validate_panel(frame: pd.DataFrame, label: str) -> None:
    keys = ["scenario_id", "alpha", "seed"]
    if frame.duplicated(keys).any():
        raise RuntimeError(f"{label} contains duplicate scenario-alpha-seed keys")
    expected = {(float(alpha), int(seed)) for alpha in ALPHAS for seed in SEEDS}
    for scenario_id, subset in frame.groupby("scenario_id", sort=False):
        observed = {
            (round(float(row.alpha), 2), int(row.seed))
            for row in subset.itertuples(index=False)
        }
        if observed != expected:
            missing = len(expected - observed)
            extra = len(observed - expected)
            raise RuntimeError(
                f"{label}/{scenario_id}: incomplete design; missing={missing}, extra={extra}"
            )
    if not np.isfinite(frame[list(METRICS)].to_numpy(float)).all():
        raise RuntimeError(f"{label} contains non-finite primary metrics")


def load_combined() -> pd.DataFrame:
    new = pd.read_csv(NEW_RAW)
    formal = pd.read_csv(FORMAL_RAW)
    formal = formal[formal["condition_id"].isin(["full", "no_response"])].copy()
    formal["scenario_id"] = formal["condition_id"].map(
        {"full": "baseline", "no_response": "strategy_no_response"}
    )
    formal["scenario_kind"] = formal["condition_id"].map(
        {"full": "baseline", "no_response": "response_strategy"}
    )
    formal["parameter"] = formal["condition_id"].map(
        {"full": "baseline", "no_response": "response_strategy"}
    )
    formal["value"] = formal["condition_id"].map(
        {"full": "registered", "no_response": "none"}
    )
    keep = ["scenario_id", "scenario_kind", "parameter", "value", "alpha", "seed", *METRICS]
    combined = pd.concat([formal[keep], new[keep]], ignore_index=True)
    validate_panel(combined, "combined sensitivity data")
    order = {"baseline": 0, "strategy_no_response": 1}
    for index, scenario_id in enumerate(new["scenario_id"].drop_duplicates(), start=2):
        order[str(scenario_id)] = index
    combined["scenario_order"] = combined["scenario_id"].map(order)
    return combined.sort_values(["scenario_order", "alpha", "seed"]).reset_index(drop=True)


def curve_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for keys, subset in frame.groupby(
        ["scenario_order", "scenario_id", "scenario_kind", "parameter", "value", "alpha"],
        sort=True,
        dropna=False,
    ):
        scenario_order, scenario_id, kind, parameter, value, alpha = keys
        for metric in METRICS:
            values = subset[metric].to_numpy(float)
            mean = float(values.mean())
            sd = float(values.std(ddof=1))
            sem = sd / np.sqrt(len(values))
            critical = float(stats.t.ppf(0.975, len(values) - 1))
            rows.append(
                {
                    "scenario_order": scenario_order,
                    "scenario_id": scenario_id,
                    "scenario_kind": kind,
                    "parameter": parameter,
                    "value": value,
                    "alpha": alpha,
                    "metric": metric,
                    "n_seeds": len(values),
                    "mean": mean,
                    "sd": sd,
                    "sem": sem,
                    "ci95_low": mean - critical * sem,
                    "ci95_high": mean + critical * sem,
                }
            )
    return pd.DataFrame(rows)


def critical_analysis(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    baseline = (
        frame[frame["scenario_id"] == "baseline"]
        .pivot(index="seed", columns="alpha", values=CRITICAL_METRIC)
        .reindex(index=SEEDS, columns=ALPHAS)
    )
    baseline_matrix = baseline.to_numpy(float)
    summary_rows: list[dict] = []
    draw_rows: list[dict] = []
    for position, (scenario_id, subset) in enumerate(frame.groupby("scenario_id", sort=False)):
        pivot = (
            subset.pivot(index="seed", columns="alpha", values=CRITICAL_METRIC)
            .reindex(index=SEEDS, columns=ALPHAS)
        )
        matrix = pivot.to_numpy(float)
        estimate, metric_range, maximum_gradient = detect_critical(ALPHAS, matrix.mean(axis=0))
        rng = np.random.default_rng(ANALYSIS_SEED + position * 1009)
        scenario_draws: list[float] = []
        delta_draws: list[float] = []
        for draw in range(BOOTSTRAP_SAMPLES):
            indices = rng.integers(0, len(SEEDS), size=len(SEEDS))
            candidate, _, _ = detect_critical(ALPHAS, matrix[indices].mean(axis=0))
            baseline_candidate, _, _ = detect_critical(
                ALPHAS, baseline_matrix[indices].mean(axis=0)
            )
            identified = candidate is not None
            paired_identified = identified and baseline_candidate is not None
            if identified:
                scenario_draws.append(float(candidate))
            if paired_identified:
                delta_draws.append(float(candidate - baseline_candidate))
            draw_rows.append(
                {
                    "scenario_id": scenario_id,
                    "bootstrap_draw": draw,
                    "critical_alpha": candidate,
                    "baseline_critical_alpha": baseline_candidate,
                    "critical_alpha_delta": (
                        candidate - baseline_candidate if paired_identified else np.nan
                    ),
                    "identified": identified,
                    "paired_identified": paired_identified,
                }
            )
        ci = (
            np.quantile(scenario_draws, [0.025, 0.975], method="nearest")
            if scenario_draws
            else (np.nan, np.nan)
        )
        delta_ci = (
            np.quantile(delta_draws, [0.025, 0.975], method="nearest")
            if delta_draws
            else (np.nan, np.nan)
        )
        metadata = subset.iloc[0]
        summary_rows.append(
            {
                "scenario_order": metadata["scenario_order"],
                "scenario_id": scenario_id,
                "scenario_kind": metadata["scenario_kind"],
                "parameter": metadata["parameter"],
                "value": metadata["value"],
                "critical_alpha": estimate,
                "critical_alpha_ci95_low": ci[0],
                "critical_alpha_ci95_high": ci[1],
                "critical_alpha_delta_vs_baseline": (
                    estimate - PRIMARY_ALPHA if estimate is not None else np.nan
                ),
                "critical_delta_ci95_low": delta_ci[0],
                "critical_delta_ci95_high": delta_ci[1],
                "metric_range": metric_range,
                "maximum_internal_gradient": maximum_gradient,
                "identification_rate": len(scenario_draws) / BOOTSTRAP_SAMPLES,
                "paired_identification_rate": len(delta_draws) / BOOTSTRAP_SAMPLES,
            }
        )
    return pd.DataFrame(summary_rows), pd.DataFrame(draw_rows)


def paired_statistics(
    baseline_values: np.ndarray,
    scenario_values: np.ndarray,
    rng: np.random.Generator,
) -> dict[str, float]:
    differences = np.asarray(scenario_values - baseline_values, float)
    n = len(differences)
    indices = rng.integers(0, n, size=(BOOTSTRAP_SAMPLES, n))
    bootstrap_means = differences[indices].mean(axis=1)
    low, high = np.quantile(bootstrap_means, [0.025, 0.975])
    sd = float(differences.std(ddof=1))
    dz = float(differences.mean() / sd) if sd > 0 else np.nan
    correction = 1.0 - 3.0 / (4.0 * n - 5.0)
    if np.all(differences == 0):
        statistic, p_value = np.nan, 1.0
    else:
        try:
            wilcoxon = stats.wilcoxon(differences, alternative="two-sided", method="auto")
            statistic = float(wilcoxon.statistic)
            p_value = float(wilcoxon.pvalue)
            if not np.isfinite(p_value):
                statistic, p_value = np.nan, 1.0
        except ValueError:
            statistic, p_value = np.nan, 1.0
    return {
        "n_pairs": n,
        "baseline_mean": float(baseline_values.mean()),
        "scenario_mean": float(scenario_values.mean()),
        "mean_paired_difference": float(differences.mean()),
        "difference_ci95_low": float(low),
        "difference_ci95_high": float(high),
        "hedges_gz": float(correction * dz) if np.isfinite(dz) else np.nan,
        "wilcoxon_statistic": statistic,
        "p_raw": p_value,
    }


def paired_endpoint_effects(frame: pd.DataFrame, mode: str) -> pd.DataFrame:
    rows: list[dict] = []
    baseline = frame[frame["scenario_id"] == "baseline"]
    scenarios = frame[frame["scenario_id"] != "baseline"]["scenario_id"].drop_duplicates()
    for position, scenario_id in enumerate(scenarios):
        subset = frame[frame["scenario_id"] == scenario_id]
        metadata = subset.iloc[0]
        for metric_index, metric in enumerate(METRICS):
            if mode == "critical_alpha":
                base_values = (
                    baseline[np.isclose(baseline["alpha"], PRIMARY_ALPHA)]
                    .set_index("seed")[metric]
                    .reindex(SEEDS)
                    .to_numpy(float)
                )
                scenario_values = (
                    subset[np.isclose(subset["alpha"], PRIMARY_ALPHA)]
                    .set_index("seed")[metric]
                    .reindex(SEEDS)
                    .to_numpy(float)
                )
            elif mode == "auc":
                base_pivot = baseline.pivot(index="seed", columns="alpha", values=metric).reindex(index=SEEDS, columns=ALPHAS)
                scenario_pivot = subset.pivot(index="seed", columns="alpha", values=metric).reindex(index=SEEDS, columns=ALPHAS)
                base_values = np.trapezoid(base_pivot.to_numpy(float), ALPHAS, axis=1)
                scenario_values = np.trapezoid(scenario_pivot.to_numpy(float), ALPHAS, axis=1)
            else:
                raise ValueError(mode)
            rng = np.random.default_rng(ANALYSIS_SEED + position * 1009 + metric_index * 37)
            row = {
                "scenario_order": metadata["scenario_order"],
                "scenario_id": scenario_id,
                "scenario_kind": metadata["scenario_kind"],
                "parameter": metadata["parameter"],
                "value": metadata["value"],
                "endpoint": mode,
                "alpha": PRIMARY_ALPHA if mode == "critical_alpha" else np.nan,
                "metric": metric,
            }
            row.update(paired_statistics(base_values, scenario_values, rng))
            rows.append(row)
    result = pd.DataFrame(rows)
    result["p_holm"] = holm_adjust(result["p_raw"])
    return result


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    combined = load_combined()
    summary = curve_summary(combined)
    critical, critical_draws = critical_analysis(combined)
    at_critical = paired_endpoint_effects(combined, "critical_alpha")
    auc = paired_endpoint_effects(combined, "auc")

    combined.to_csv(OUT / "sensitivity_combined_analysis_input.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUT / "sensitivity_curve_summary.csv", index=False, encoding="utf-8-sig")
    critical.to_csv(OUT / "sensitivity_critical_points.csv", index=False, encoding="utf-8-sig")
    critical_draws.to_csv(OUT / "sensitivity_critical_bootstrap.csv", index=False, encoding="utf-8-sig")
    at_critical.to_csv(OUT / "sensitivity_effects_at_alpha_060.csv", index=False, encoding="utf-8-sig")
    auc.to_csv(OUT / "sensitivity_auc_effects.csv", index=False, encoding="utf-8-sig")

    metadata = {
        "analysis_status": "formal_nonspatial_sensitivity_v1",
        "primary_metric": CRITICAL_METRIC,
        "critical_rule": "three-point centered rolling mean then largest positive internal numerical gradient; minimum observed range 0.015",
        "primary_alpha": PRIMARY_ALPHA,
        "alpha_values": ALPHAS.tolist(),
        "common_seeds": SEEDS.tolist(),
        "replicates_per_cell": len(SEEDS),
        "bootstrap_samples": BOOTSTRAP_SAMPLES,
        "paired_test": "two-sided Wilcoxon signed-rank; Holm correction across each endpoint table",
        "effect_size": "bias-corrected paired standardized mean difference (Hedges gz)",
        "new_raw_sha256": sha256(NEW_RAW),
        "formal_raw_sha256": sha256(FORMAL_RAW),
        "rows_new": int(pd.read_csv(NEW_RAW, usecols=["alpha"]).shape[0]),
        "rows_combined": len(combined),
        "scenario_count_including_baseline_and_no_response": int(combined["scenario_id"].nunique()),
    }
    (OUT / "sensitivity_analysis_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"status": "complete", **metadata}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
