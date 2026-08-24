"""Statistical analysis for the formal four-condition non-spatial ablation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


HERE = Path(__file__).resolve().parent
RAW_PATH = HERE / "raw" / "formal_replicates.csv"
MANIFEST_PATH = HERE / "raw" / "formal_manifest.json"
PROCESSED = HERE / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)

CONDITIONS = ("no_emotion", "no_drift", "no_response")
PRIMARY_METRICS = (
    "mean_agenda_divergence",
    "system_stability",
    "storm_time_share",
    "mean_trust",
)
METRIC_LABELS = {
    "mean_agenda_divergence": "Agenda divergence",
    "system_stability": "Agenda-divergence variance",
    "storm_time_share": "Storm time share",
    "mean_trust": "Government trust",
}
BOOTSTRAP_CRITICAL = 5000
BOOTSTRAP_EFFECT = 10000
SIGNFLIP_SAMPLES = 99999
ANALYSIS_SEED = 20260810


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def holm_adjust(values: pd.Series) -> pd.Series:
    array = values.to_numpy(dtype=float)
    result = np.full(len(array), np.nan, dtype=float)
    finite = np.flatnonzero(np.isfinite(array))
    if not len(finite):
        return pd.Series(result, index=values.index)
    order = finite[np.argsort(array[finite])]
    running = 0.0
    m = len(order)
    for rank, index in enumerate(order):
        running = max(running, (m - rank) * array[index])
        result[index] = min(1.0, running)
    return pd.Series(result, index=values.index)


def detect_critical(
    alphas: np.ndarray,
    values: np.ndarray,
    minimum_range: float = 0.015,
) -> tuple[float | None, float, float]:
    if len(alphas) < 3 or not np.all(np.isfinite(values)):
        return None, float("nan"), float("nan")
    metric_range = float(np.ptp(values))
    if metric_range < minimum_range:
        return None, metric_range, float("nan")
    smoothed = (
        pd.Series(values)
        .rolling(window=3, center=True, min_periods=1)
        .mean()
        .to_numpy(dtype=float)
    )
    gradients = np.gradient(smoothed, alphas)
    internal = np.arange(1, len(alphas) - 1)
    index = int(internal[np.argmax(gradients[internal])])
    maximum_gradient = float(gradients[index])
    if maximum_gradient <= 0.0:
        return None, metric_range, maximum_gradient
    return float(alphas[index]), metric_range, maximum_gradient


def bootstrap_mean_effect(
    differences: np.ndarray,
    *,
    samples: int,
    rng: np.random.Generator,
) -> tuple[float, float, float, float, int]:
    n = len(differences)
    indices = rng.integers(0, n, size=(samples, n))
    draws = differences[indices]
    means = draws.mean(axis=1)
    standard_deviations = draws.std(axis=1, ddof=1)
    effects = np.divide(
        means,
        standard_deviations,
        out=np.full_like(means, np.nan),
        where=standard_deviations > 0,
    )
    correction = 1.0 - 3.0 / (4.0 * n - 5.0)
    hedges_draws = correction * effects
    valid = np.isfinite(hedges_draws)
    low, high = np.quantile(means, [0.025, 0.975])
    if valid.any():
        effect_low, effect_high = np.quantile(
            hedges_draws[valid], [0.025, 0.975]
        )
    else:
        effect_low = effect_high = float("nan")
    return (
        float(low),
        float(high),
        float(effect_low),
        float(effect_high),
        int(valid.sum()),
    )


def signflip_pvalue(
    differences: np.ndarray,
    *,
    samples: int,
    rng: np.random.Generator,
) -> tuple[float, float]:
    observed = abs(float(np.mean(differences)))
    n = len(differences)
    exceedances = 0
    remaining = samples
    while remaining:
        batch = min(5000, remaining)
        signs = rng.choice(np.asarray([-1.0, 1.0]), size=(batch, n))
        simulated = np.abs((signs @ differences) / n)
        exceedances += int(np.count_nonzero(simulated >= observed - 1e-15))
        remaining -= batch
    p_value = (exceedances + 1.0) / (samples + 1.0)
    mc_se = np.sqrt(p_value * (1.0 - p_value) / (samples + 1.0))
    return float(p_value), float(mc_se)


def paired_statistics(
    differences: np.ndarray,
    *,
    baseline_mean: float,
    ablation_mean: float,
    bootstrap_seed: int,
    include_signflip: bool,
) -> dict[str, Any]:
    values = np.asarray(differences, dtype=float)
    n = len(values)
    mean = float(values.mean())
    sd = float(values.std(ddof=1))
    se = sd / np.sqrt(n) if sd > 0 else 0.0
    if sd > 0:
        t_statistic = mean / se
        t_p = float(2.0 * stats.t.sf(abs(t_statistic), df=n - 1))
        t_critical = float(stats.t.ppf(0.975, df=n - 1))
        t_low, t_high = mean - t_critical * se, mean + t_critical * se
        cohen_dz = mean / sd
    else:
        t_statistic = 0.0 if mean == 0 else np.sign(mean) * np.inf
        t_p = 1.0 if mean == 0 else 0.0
        t_low = t_high = mean
        cohen_dz = 0.0 if mean == 0 else np.sign(mean) * np.inf

    nonzero = values[values != 0]
    if len(nonzero):
        wilcoxon = stats.wilcoxon(
            nonzero,
            zero_method="wilcox",
            alternative="two-sided",
            method="auto",
        )
        wilcoxon_statistic = float(wilcoxon.statistic)
        wilcoxon_p = float(wilcoxon.pvalue)
        ranks = stats.rankdata(np.abs(nonzero))
        denominator = float(ranks.sum())
        rank_biserial = float(
            (ranks[nonzero > 0].sum() - ranks[nonzero < 0].sum())
            / denominator
        )
    else:
        wilcoxon_statistic = 0.0
        wilcoxon_p = 1.0
        rank_biserial = 0.0

    rng = np.random.default_rng(bootstrap_seed)
    (
        bootstrap_low,
        bootstrap_high,
        hedges_low,
        hedges_high,
        valid_effect_draws,
    ) = bootstrap_mean_effect(values, samples=BOOTSTRAP_EFFECT, rng=rng)
    correction = 1.0 - 3.0 / (4.0 * n - 5.0)
    hedges_gz = float(correction * cohen_dz)
    if include_signflip:
        signflip_p, signflip_mc_se = signflip_pvalue(
            values,
            samples=SIGNFLIP_SAMPLES,
            rng=np.random.default_rng(bootstrap_seed + 991),
        )
    else:
        signflip_p = signflip_mc_se = float("nan")

    return {
        "n_pairs": n,
        "baseline_mean": float(baseline_mean),
        "ablation_mean": float(ablation_mean),
        "mean_difference": mean,
        "median_difference": float(np.median(values)),
        "difference_sd": sd,
        "difference_se": se,
        "t_ci_low": float(t_low),
        "t_ci_high": float(t_high),
        "bootstrap_ci_low": bootstrap_low,
        "bootstrap_ci_high": bootstrap_high,
        "t_statistic": float(t_statistic),
        "t_df": n - 1,
        "t_p_raw": t_p,
        "wilcoxon_statistic": wilcoxon_statistic,
        "wilcoxon_p_raw": wilcoxon_p,
        "signflip_p_raw": signflip_p,
        "signflip_mc_se": signflip_mc_se,
        "cohen_dz": float(cohen_dz),
        "hedges_gz": hedges_gz,
        "hedges_gz_ci_low": hedges_low,
        "hedges_gz_ci_high": hedges_high,
        "hedges_gz_valid_bootstrap_draws": valid_effect_draws,
        "rank_biserial": rank_biserial,
        "zero_variance": bool(sd == 0),
    }


def critical_points(frame: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "metric": "mean_agenda_divergence",
        "bootstrap_method": "paired seed-block bootstrap over complete alpha curves",
        "bootstrap_samples": BOOTSTRAP_CRITICAL,
        "minimum_metric_range": 0.015,
        "conditions": {},
    }
    for condition_order, condition_id in enumerate(
        ("full", "no_emotion", "no_drift", "no_response")
    ):
        subset = frame[frame["condition_id"] == condition_id]
        pivot = subset.pivot(
            index="seed", columns="alpha", values="mean_agenda_divergence"
        ).sort_index(axis=0).sort_index(axis=1)
        alphas = pivot.columns.to_numpy(dtype=float)
        matrix = pivot.to_numpy(dtype=float)
        estimate, metric_range, maximum_gradient = detect_critical(
            alphas, matrix.mean(axis=0)
        )
        rng = np.random.default_rng(ANALYSIS_SEED + 1000 * condition_order)
        draws: list[float | None] = []
        for draw in range(BOOTSTRAP_CRITICAL):
            indices = rng.integers(0, len(matrix), size=len(matrix))
            candidate, _, _ = detect_critical(
                alphas, matrix[indices].mean(axis=0)
            )
            draws.append(candidate)
            rows.append(
                {
                    "condition_id": condition_id,
                    "bootstrap_draw": draw,
                    "critical_alpha": candidate,
                    "identified": candidate is not None,
                }
            )
        identified = np.asarray(
            [value for value in draws if value is not None], dtype=float
        )
        if len(identified):
            low, high = np.quantile(
                identified, [0.025, 0.975], method="nearest"
            )
        else:
            low = high = float("nan")
        counts = (
            pd.Series(identified)
            .value_counts()
            .sort_index()
            .rename_axis("alpha")
            .to_dict()
        )
        report["conditions"][condition_id] = {
            "critical_alpha": estimate,
            "metric_range": metric_range,
            "maximum_internal_gradient": maximum_gradient,
            "identification_rate": len(identified) / BOOTSTRAP_CRITICAL,
            "bootstrap_ci_95": [float(low), float(high)],
            "candidate_counts": {f"{key:.2f}": int(value) for key, value in counts.items()},
        }
    report["primary_alpha"] = report["conditions"]["full"]["critical_alpha"]
    return report, pd.DataFrame(rows)


def condition_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    grouped = frame.groupby(
        ["condition_order", "condition_id", "condition_label", "alpha"],
        sort=True,
    )
    for keys, group in grouped:
        condition_order, condition_id, condition_label, alpha = keys
        for metric in PRIMARY_METRICS:
            values = group[metric].to_numpy(dtype=float)
            n = len(values)
            sd = float(values.std(ddof=1))
            se = sd / np.sqrt(n)
            critical = float(stats.t.ppf(0.975, n - 1))
            mean = float(values.mean())
            rows.append(
                {
                    "condition_order": condition_order,
                    "condition_id": condition_id,
                    "condition_label": condition_label,
                    "alpha": float(alpha),
                    "metric": metric,
                    "metric_label": METRIC_LABELS[metric],
                    "n": n,
                    "mean": mean,
                    "sd": sd,
                    "se": se,
                    "mean_t_ci_low": mean - critical * se,
                    "mean_t_ci_high": mean + critical * se,
                }
            )
    return pd.DataFrame(rows)


def paired_effects(frame: pd.DataFrame, primary_alpha: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for condition_order, condition_id in enumerate(CONDITIONS, start=1):
        for alpha_index, alpha in enumerate(sorted(frame["alpha"].unique())):
            full = frame[
                (frame["condition_id"] == "full") & (frame["alpha"] == alpha)
            ].set_index("seed")
            ablation = frame[
                (frame["condition_id"] == condition_id)
                & (frame["alpha"] == alpha)
            ].set_index("seed")
            if not full.index.equals(ablation.index):
                raise RuntimeError(f"seed pairing failed for {condition_id}, alpha={alpha}")
            for metric_index, metric in enumerate(PRIMARY_METRICS):
                differences = (
                    ablation[metric].to_numpy(dtype=float)
                    - full[metric].to_numpy(dtype=float)
                )
                is_primary = bool(np.isclose(alpha, primary_alpha))
                statistics = paired_statistics(
                    differences,
                    baseline_mean=float(full[metric].mean()),
                    ablation_mean=float(ablation[metric].mean()),
                    bootstrap_seed=(
                        ANALYSIS_SEED
                        + condition_order * 100000
                        + alpha_index * 1000
                        + metric_index * 10
                    ),
                    include_signflip=is_primary,
                )
                rows.append(
                    {
                        "condition_order": condition_order,
                        "condition_id": condition_id,
                        "condition_label": str(ablation["condition_label"].iloc[0]),
                        "removed_mechanism": str(
                            ablation["removed_mechanism"].iloc[0]
                        ),
                        "alpha": float(alpha),
                        "metric": metric,
                        "metric_label": METRIC_LABELS[metric],
                        "is_primary_alpha": is_primary,
                        "difference_direction": "ablation_minus_full",
                        "bootstrap_samples": BOOTSTRAP_EFFECT,
                        "bootstrap_unit": "paired seed",
                        "signflip_samples": SIGNFLIP_SAMPLES if is_primary else 0,
                        **statistics,
                    }
                )
    result = pd.DataFrame(rows)
    result["holm_t_p_within_metric_all_alpha"] = np.nan
    result["holm_wilcoxon_p_within_metric_all_alpha"] = np.nan
    for metric, group in result.groupby("metric"):
        result.loc[group.index, "holm_t_p_within_metric_all_alpha"] = holm_adjust(
            group["t_p_raw"]
        )
        result.loc[
            group.index, "holm_wilcoxon_p_within_metric_all_alpha"
        ] = holm_adjust(group["wilcoxon_p_raw"])
    result["holm_t_p_primary_global"] = np.nan
    result["holm_wilcoxon_p_primary_global"] = np.nan
    result["holm_signflip_p_primary_global"] = np.nan
    primary = result[result["is_primary_alpha"]]
    result.loc[primary.index, "holm_t_p_primary_global"] = holm_adjust(
        primary["t_p_raw"]
    )
    result.loc[
        primary.index, "holm_wilcoxon_p_primary_global"
    ] = holm_adjust(primary["wilcoxon_p_raw"])
    result.loc[
        primary.index, "holm_signflip_p_primary_global"
    ] = holm_adjust(primary["signflip_p_raw"])
    return result


def auc_effects(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for condition_order, condition_id in enumerate(CONDITIONS, start=1):
        for metric_index, metric in enumerate(PRIMARY_METRICS):
            full_auc: dict[int, float] = {}
            ablation_auc: dict[int, float] = {}
            for seed, group in frame[frame["condition_id"] == "full"].groupby("seed"):
                ordered = group.sort_values("alpha")
                full_auc[int(seed)] = float(
                    np.trapezoid(
                        ordered[metric].to_numpy(dtype=float),
                        ordered["alpha"].to_numpy(dtype=float),
                    )
                )
            for seed, group in frame[frame["condition_id"] == condition_id].groupby(
                "seed"
            ):
                ordered = group.sort_values("alpha")
                ablation_auc[int(seed)] = float(
                    np.trapezoid(
                        ordered[metric].to_numpy(dtype=float),
                        ordered["alpha"].to_numpy(dtype=float),
                    )
                )
            seed_order = sorted(full_auc)
            baseline = np.asarray([full_auc[seed] for seed in seed_order])
            ablation = np.asarray([ablation_auc[seed] for seed in seed_order])
            statistics = paired_statistics(
                ablation - baseline,
                baseline_mean=float(baseline.mean()),
                ablation_mean=float(ablation.mean()),
                bootstrap_seed=ANALYSIS_SEED + 700000 + condition_order * 1000 + metric_index,
                include_signflip=True,
            )
            rows.append(
                {
                    "condition_order": condition_order,
                    "condition_id": condition_id,
                    "metric": metric,
                    "metric_label": METRIC_LABELS[metric],
                    "alpha_min": float(frame["alpha"].min()),
                    "alpha_max": float(frame["alpha"].max()),
                    "alpha_count": int(frame["alpha"].nunique()),
                    "auc_method": "per-seed trapezoidal integration",
                    "difference_direction": "ablation_minus_full",
                    "bootstrap_samples": BOOTSTRAP_EFFECT,
                    "signflip_samples": SIGNFLIP_SAMPLES,
                    **statistics,
                }
            )
    result = pd.DataFrame(rows)
    result["holm_t_p_global"] = holm_adjust(result["t_p_raw"])
    result["holm_wilcoxon_p_global"] = holm_adjust(result["wilcoxon_p_raw"])
    result["holm_signflip_p_global"] = holm_adjust(result["signflip_p_raw"])
    return result


def main() -> int:
    frame = pd.read_csv(RAW_PATH)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise RuntimeError("formal manifest is not complete")
    if len(frame) != 4200:
        raise RuntimeError(f"expected 4200 rows, found {len(frame)}")
    if frame.duplicated(["condition_id", "alpha", "seed"]).any():
        raise RuntimeError("duplicate primary keys in raw data")

    critical_report, critical_bootstrap = critical_points(frame)
    primary_alpha = critical_report["primary_alpha"]
    if primary_alpha is None:
        raise RuntimeError("full-model critical alpha was not identified")
    summary = condition_summary(frame)
    effects = paired_effects(frame, float(primary_alpha))
    auc = auc_effects(frame)

    critical_report.update(
        {
            "analysis_status": "formal_nonspatial_ablation_v1",
            "raw_sha256": sha256(RAW_PATH),
            "manifest_sha256": sha256(MANIFEST_PATH),
            "effect_bootstrap_samples": BOOTSTRAP_EFFECT,
            "primary_signflip_samples": SIGNFLIP_SAMPLES,
            "interpretation": (
                "Critical points are internal simulation diagnostics. "
                "Ablation effects are model-internal paired contrasts, not empirical causal estimates."
            ),
        }
    )
    (PROCESSED / "critical_points.json").write_text(
        json.dumps(critical_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    critical_bootstrap.to_csv(
        PROCESSED / "critical_bootstrap.csv", index=False, encoding="utf-8"
    )
    summary.to_csv(
        PROCESSED / "condition_summary.csv", index=False, encoding="utf-8"
    )
    effects.to_csv(
        PROCESSED / "paired_effects.csv", index=False, encoding="utf-8"
    )
    auc.to_csv(PROCESSED / "auc_effects.csv", index=False, encoding="utf-8")
    print(
        f"Analysis complete. Primary alpha={primary_alpha:.2f}; "
        f"paired rows={len(effects)}, AUC rows={len(auc)}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

