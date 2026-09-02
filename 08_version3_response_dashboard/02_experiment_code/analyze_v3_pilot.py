"""Paired statistical analysis for the Version 3 response-heat pilot.

The script treats the random seed as the pairing/blocking unit.  Its primary
endpoint is ``log1p(petition_heat_auc_post_14_days)`` and its primary timing
contrast is a difference in differences:

    [L(1.00) - L(0.70)]_early - [L(1.00) - L(0.70)]_late

A positive contrast therefore means that the 30% heat multiplier produces a
larger cooling benefit under the early-response condition.  The script is for
pilot diagnostics only; its report deliberately does not label the output as
formal or real-world causal evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import pandas as pd
from scipy.special import gammaln


HERE = Path(__file__).resolve().parent
V3_ROOT = HERE.parent
DEFAULT_INPUT = V3_ROOT / "05_outputs" / "pilot" / "v3_pilot_run_summaries.csv"
DEFAULT_OUTPUT_DIR = V3_ROOT / "05_outputs" / "pilot"

# IDs emitted by ``run_v3_experiment.py``.  The day checks below are the
# substantive guard; the labels retain the empirical P5/P95 provenance.
EARLY_CONDITION = "early_p05_11"
LATE_CONDITION = "late_p95_57"
EXPECTED_ALPHAS = (0.40, 0.60, 0.80)
EXPECTED_MULTIPLIERS = (0.70, 1.00)
DEFAULT_BOOTSTRAP_REPETITIONS = 10_000
MAX_EXACT_SIGN_FLIP_N = 20

REQUIRED_COLUMNS = {
    "run_id",
    "alpha",
    "seed",
    "delay_condition_id",
    "response_delay_days",
    "response_heat_multiplier",
    "petition_heat_auc_post_14_days",
    "petition_heat_auc_threshold_to_close",
    "petition_heat_peak_post_14_days",
    "petition_exposures_post_14_days",
    "petition_interactions_post_14_days",
    "mean_trust_post_14_days",
    "mean_agenda_divergence_threshold_to_close",
}


@dataclass(frozen=True)
class MetricSpec:
    metric_id: str
    source_column: str
    label_zh: str
    transform_name: str
    transform: Callable[[np.ndarray], np.ndarray]
    primary: bool = False


def _identity(values: np.ndarray) -> np.ndarray:
    return values.astype(float, copy=False)


def _log1p(values: np.ndarray) -> np.ndarray:
    return np.log1p(values.astype(float, copy=False))


METRICS = (
    MetricSpec(
        metric_id="primary_log1p_post14_heat_auc",
        source_column="petition_heat_auc_post_14_days",
        label_zh="回应后14日请愿热度AUC（log1p）",
        transform_name="log1p",
        transform=_log1p,
        primary=True,
    ),
    MetricSpec(
        metric_id="secondary_log1p_threshold_to_close_heat_auc",
        source_column="petition_heat_auc_threshold_to_close",
        label_zh="门槛日至关闭日请愿热度AUC（log1p）",
        transform_name="log1p",
        transform=_log1p,
    ),
    MetricSpec(
        metric_id="secondary_log1p_post14_heat_peak",
        source_column="petition_heat_peak_post_14_days",
        label_zh="回应后14日请愿峰值热度（log1p）",
        transform_name="log1p",
        transform=_log1p,
    ),
    MetricSpec(
        metric_id="secondary_log1p_post14_exposures",
        source_column="petition_exposures_post_14_days",
        label_zh="回应后14日请愿曝光数（log1p）",
        transform_name="log1p",
        transform=_log1p,
    ),
    MetricSpec(
        metric_id="secondary_log1p_post14_interactions",
        source_column="petition_interactions_post_14_days",
        label_zh="回应后14日请愿互动数（log1p）",
        transform_name="log1p",
        transform=_log1p,
    ),
    MetricSpec(
        metric_id="secondary_mean_trust_post14",
        source_column="mean_trust_post_14_days",
        label_zh="回应后14日平均政府信任",
        transform_name="identity",
        transform=_identity,
    ),
    MetricSpec(
        metric_id="secondary_mean_agenda_divergence_threshold_to_close",
        source_column="mean_agenda_divergence_threshold_to_close",
        label_zh="门槛日至关闭日平均议程偏离",
        transform_name="identity",
        transform=_identity,
    ),
)

METRIC_BY_ID = {metric.metric_id: metric for metric in METRICS}
PRIMARY_METRIC_ID = next(metric.metric_id for metric in METRICS if metric.primary)

OUTPUT_FILENAMES = {
    "paired": "v3_pilot_paired_effects.csv",
    "interactions": "v3_pilot_timing_interactions.csv",
    "statistics": "v3_pilot_statistics.csv",
    "figure": "v3_figure_source_data.csv",
    "report": "V3_PILOT_STATISTICAL_REPORT.md",
}


def _normalize_multiplier(value: float) -> float:
    numeric = float(value)
    for expected in EXPECTED_MULTIPLIERS:
        if math.isclose(numeric, expected, rel_tol=0.0, abs_tol=1e-9):
            return expected
    raise ValueError(
        "response_heat_multiplier must contain only 0.70 and 1.00; "
        f"found {numeric!r}"
    )


def load_and_validate(path: Path) -> tuple[pd.DataFrame, list[str], list[int]]:
    """Load the run panel and enforce the common-seed factorial contract."""

    if not path.is_file():
        raise FileNotFoundError(f"pilot run summary not found: {path}")
    frame = pd.read_csv(path)
    missing = sorted(REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"pilot run summary is missing columns: {missing}")
    if frame.empty:
        raise ValueError("pilot run summary is empty")
    if frame["run_id"].isna().any() or frame["run_id"].duplicated().any():
        raise ValueError("run_id must be non-missing and unique")

    numeric_columns = sorted(
        REQUIRED_COLUMNS.difference({"run_id", "delay_condition_id"})
    )
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        if not np.isfinite(frame[column].to_numpy(dtype=float)).all():
            raise ValueError(f"{column} contains a missing or non-finite value")

    if not np.allclose(frame["seed"], np.rint(frame["seed"])):
        raise ValueError("seed values must be integers")
    frame["seed"] = frame["seed"].astype(int)
    frame["alpha"] = frame["alpha"].round(2)
    observed_alphas = tuple(sorted(frame["alpha"].unique().tolist()))
    if observed_alphas != EXPECTED_ALPHAS:
        raise ValueError(
            f"alpha levels must be exactly {EXPECTED_ALPHAS}; found {observed_alphas}"
        )
    frame["response_heat_multiplier"] = frame[
        "response_heat_multiplier"
    ].map(_normalize_multiplier)

    nonnegative_columns = [
        "petition_heat_auc_post_14_days",
        "petition_heat_auc_threshold_to_close",
        "petition_heat_peak_post_14_days",
        "petition_exposures_post_14_days",
        "petition_interactions_post_14_days",
    ]
    for column in nonnegative_columns:
        if (frame[column] < 0.0).any():
            raise ValueError(f"{column} cannot contain negative values")
    for column in (
        "mean_trust_post_14_days",
        "mean_agenda_divergence_threshold_to_close",
    ):
        if ((frame[column] < 0.0) | (frame[column] > 1.0)).any():
            raise ValueError(f"{column} must lie in [0, 1]")

    delays = sorted(frame["delay_condition_id"].astype(str).unique().tolist())
    for required in (EARLY_CONDITION, LATE_CONDITION):
        if required not in delays:
            raise ValueError(f"required delay condition {required!r} is missing")
    delay_days = (
        frame.groupby("delay_condition_id", sort=True)["response_delay_days"]
        .agg(["min", "max"])
        .reset_index()
    )
    if (delay_days["min"] != delay_days["max"]).any():
        raise ValueError("each delay_condition_id must map to one response delay")
    day_map = dict(zip(delay_days["delay_condition_id"], delay_days["min"]))
    if not math.isclose(float(day_map[EARLY_CONDITION]), 11.0, abs_tol=1e-9):
        raise ValueError(f"{EARLY_CONDITION} must have response_delay_days=11")
    if not math.isclose(float(day_map[LATE_CONDITION]), 57.0, abs_tol=1e-9):
        raise ValueError(f"{LATE_CONDITION} must have response_delay_days=57")

    key = [
        "seed",
        "alpha",
        "delay_condition_id",
        "response_heat_multiplier",
    ]
    if frame.duplicated(key).any():
        duplicate = frame.loc[frame.duplicated(key, keep=False), key].head()
        raise ValueError(
            "duplicate factorial cells found:\n" + duplicate.to_string(index=False)
        )
    seeds = sorted(frame["seed"].unique().tolist())
    expected = pd.MultiIndex.from_product(
        [seeds, EXPECTED_ALPHAS, delays, EXPECTED_MULTIPLIERS], names=key
    )
    observed = pd.MultiIndex.from_frame(frame[key])
    missing_cells = expected.difference(observed)
    unexpected_cells = observed.difference(expected)
    if len(missing_cells) or len(unexpected_cells):
        details = []
        if len(missing_cells):
            details.append(f"missing cells (first 8): {list(missing_cells[:8])}")
        if len(unexpected_cells):
            details.append(
                f"unexpected cells (first 8): {list(unexpected_cells[:8])}"
            )
        raise ValueError("common-seed factorial panel is incomplete; " + "; ".join(details))
    if len(seeds) < 2:
        raise ValueError("at least two common seeds are required")
    if len(seeds) > MAX_EXACT_SIGN_FLIP_N:
        raise ValueError(
            "this pilot script promises exact sign-flip inference and therefore "
            f"supports at most {MAX_EXACT_SIGN_FLIP_N} seeds; found {len(seeds)}"
        )
    return frame.sort_values(key).reset_index(drop=True), delays, seeds


def build_transformed_values(frame: pd.DataFrame) -> pd.DataFrame:
    records: list[pd.DataFrame] = []
    id_columns = [
        "run_id",
        "seed",
        "alpha",
        "delay_condition_id",
        "response_delay_days",
        "response_heat_multiplier",
    ]
    for metric in METRICS:
        values = frame[id_columns].copy()
        raw = frame[metric.source_column].to_numpy(dtype=float)
        values["metric_id"] = metric.metric_id
        values["metric_label_zh"] = metric.label_zh
        values["source_column"] = metric.source_column
        values["transform"] = metric.transform_name
        values["raw_value"] = raw
        values["analysis_value"] = metric.transform(raw)
        records.append(values)
    return pd.concat(records, ignore_index=True)


def build_paired_effects(values: pd.DataFrame) -> pd.DataFrame:
    """Pair 1.00 and 0.70 within seed, alpha and delay."""

    index = [
        "seed",
        "alpha",
        "delay_condition_id",
        "response_delay_days",
        "metric_id",
        "metric_label_zh",
        "source_column",
        "transform",
    ]
    pivot = values.pivot(index=index, columns="response_heat_multiplier", values="analysis_value")
    if 0.70 not in pivot.columns or 1.00 not in pivot.columns:
        raise RuntimeError("both heat multipliers are required after validation")
    paired = pivot.rename(
        columns={0.70: "value_multiplier_0_70", 1.00: "value_multiplier_1_00"}
    ).reset_index()
    paired["paired_effect_1_00_minus_0_70"] = (
        paired["value_multiplier_1_00"] - paired["value_multiplier_0_70"]
    )
    paired["effect_direction"] = (
        "positive_means_multiplier_0_70_reduced_the_endpoint"
    )
    return paired.sort_values(
        ["metric_id", "alpha", "delay_condition_id", "seed"]
    ).reset_index(drop=True)


def build_timing_interactions(paired: pd.DataFrame) -> pd.DataFrame:
    """Build early-minus-late contrasts and multiplier-by-timing interactions."""

    records: list[dict[str, object]] = []
    for metric in METRICS:
        subset = paired[paired["metric_id"].eq(metric.metric_id)]
        for alpha in EXPECTED_ALPHAS:
            alpha_rows = subset[subset["alpha"].eq(alpha)].set_index(
                ["seed", "delay_condition_id"]
            )
            for seed in sorted(subset["seed"].unique()):
                early = alpha_rows.loc[(seed, EARLY_CONDITION)]
                late = alpha_rows.loc[(seed, LATE_CONDITION)]
                benefit_early = float(early["paired_effect_1_00_minus_0_70"])
                benefit_late = float(late["paired_effect_1_00_minus_0_70"])
                early_070 = float(early["value_multiplier_0_70"])
                late_070 = float(late["value_multiplier_0_70"])
                early_100 = float(early["value_multiplier_1_00"])
                late_100 = float(late["value_multiplier_1_00"])
                records.append(
                    {
                        "seed": int(seed),
                        "alpha": float(alpha),
                        "metric_id": metric.metric_id,
                        "metric_label_zh": metric.label_zh,
                        "source_column": metric.source_column,
                        "transform": metric.transform_name,
                        "cooling_benefit_early": benefit_early,
                        "cooling_benefit_late": benefit_late,
                        "timing_interaction_early_minus_late": (
                            benefit_early - benefit_late
                        ),
                        "early_minus_late_multiplier_0_70": early_070 - late_070,
                        "early_minus_late_multiplier_1_00": early_100 - late_100,
                        "interaction_direction": (
                            "positive_means_cooling_benefit_is_larger_when_early"
                        ),
                    }
                )
    return pd.DataFrame.from_records(records).sort_values(
        ["metric_id", "alpha", "seed"]
    ).reset_index(drop=True)


def exact_sign_flip_p(values: Iterable[float]) -> float:
    """Return the exact two-sided randomization p value over all 2**n signs."""

    array = np.asarray(list(values), dtype=float)
    if array.ndim != 1 or array.size < 2 or not np.isfinite(array).all():
        raise ValueError("exact sign-flip input must contain at least two finite values")
    n = int(array.size)
    if n > MAX_EXACT_SIGN_FLIP_N:
        raise ValueError(f"exact sign-flip enumeration is limited to n<={MAX_EXACT_SIGN_FLIP_N}")
    observed = abs(float(array.mean()))
    tolerance = 1e-12 * max(1.0, observed)
    extreme = 0
    total = 1 << n
    for signs in itertools.product((-1.0, 1.0), repeat=n):
        permuted = abs(float(np.dot(array, np.asarray(signs, dtype=float)) / n))
        if permuted >= observed - tolerance:
            extreme += 1
    return float(extreme / total)


def _stable_rng(label: str) -> np.random.Generator:
    digest = hashlib.sha256(label.encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], byteorder="little", signed=False)
    return np.random.default_rng(seed)


def seed_bootstrap_ci(
    values: Iterable[float], *, repetitions: int, label: str
) -> tuple[float, float]:
    """Percentile CI from resampling complete seed-level contrasts."""

    array = np.asarray(list(values), dtype=float)
    if array.ndim != 1 or array.size < 2 or not np.isfinite(array).all():
        raise ValueError("bootstrap input must contain at least two finite values")
    rng = _stable_rng(label)
    indices = rng.integers(0, array.size, size=(repetitions, array.size))
    estimates = array[indices].mean(axis=1)
    low, high = np.quantile(estimates, [0.025, 0.975])
    return float(low), float(high)


def hedges_gz(values: Iterable[float]) -> float:
    """Small-sample-corrected standardized paired mean difference."""

    array = np.asarray(list(values), dtype=float)
    n = int(array.size)
    standard_deviation = float(array.std(ddof=1))
    if n < 3 or math.isclose(standard_deviation, 0.0, abs_tol=1e-15):
        return float("nan")
    degrees_freedom = n - 1
    correction = math.exp(
        gammaln(degrees_freedom / 2.0)
        - 0.5 * math.log(degrees_freedom / 2.0)
        - gammaln((degrees_freedom - 1.0) / 2.0)
    )
    return float(correction * array.mean() / standard_deviation)


def summarize_contrast(
    values: Iterable[float],
    *,
    metric: MetricSpec,
    contrast_type: str,
    alpha_scope: str,
    delay_condition_id: str,
    repetitions: int,
    multiplicity_family: str,
) -> dict[str, object]:
    array = np.asarray(list(values), dtype=float)
    label = "|".join(
        [metric.metric_id, contrast_type, alpha_scope, delay_condition_id]
    )
    estimate = float(array.mean())
    ci_low, ci_high = seed_bootstrap_ci(
        array, repetitions=repetitions, label=label
    )
    p_exact = exact_sign_flip_p(array)
    if metric.transform_name == "log1p":
        if contrast_type == "cooling_effect_1_00_minus_0_70":
            effect_percent = 100.0 * (1.0 - math.exp(-estimate))
            percent_definition = "approximate_percent_reduction_under_0_70"
        else:
            effect_percent = 100.0 * (math.exp(estimate) - 1.0)
            percent_definition = "ratio_scale_percent_change"
    else:
        effect_percent = float("nan")
        percent_definition = "not_applicable_identity_scale"
    return {
        "metric_id": metric.metric_id,
        "metric_label_zh": metric.label_zh,
        "source_column": metric.source_column,
        "transform": metric.transform_name,
        "contrast_type": contrast_type,
        "alpha_scope": alpha_scope,
        "delay_condition_id": delay_condition_id,
        "n_seeds": int(array.size),
        "estimate": estimate,
        "bootstrap_ci_low": ci_low,
        "bootstrap_ci_high": ci_high,
        "ci_excludes_zero": bool(ci_low > 0.0 or ci_high < 0.0),
        "exact_sign_flip_p": p_exact,
        "holm_p_alpha": float("nan"),
        "hedges_gz": hedges_gz(array),
        "effect_percent": effect_percent,
        "effect_percent_definition": percent_definition,
        "bootstrap_repetitions": repetitions,
        "inference_unit": "common_random_seed",
        "multiplicity_family": multiplicity_family,
        "evidence_status": "pilot_only_not_formal_evidence",
    }


def _holm_adjust(p_values: pd.Series) -> pd.Series:
    """Holm family-wise error adjustment, retaining the original row order."""

    p = p_values.to_numpy(dtype=float)
    order = np.argsort(p, kind="stable")
    adjusted_sorted = np.empty_like(p)
    running = 0.0
    count = len(p)
    for rank, index in enumerate(order):
        candidate = (count - rank) * p[index]
        running = max(running, candidate)
        adjusted_sorted[rank] = min(1.0, running)
    adjusted = np.empty_like(p)
    adjusted[order] = adjusted_sorted
    return pd.Series(adjusted, index=p_values.index)


def build_statistics(
    paired: pd.DataFrame,
    interactions: pd.DataFrame,
    *,
    repetitions: int,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for metric in METRICS:
        metric_pairs = paired[paired["metric_id"].eq(metric.metric_id)]
        for alpha in EXPECTED_ALPHAS:
            alpha_pairs = metric_pairs[metric_pairs["alpha"].eq(alpha)]
            for delay, group in alpha_pairs.groupby("delay_condition_id", sort=True):
                rows.append(
                    summarize_contrast(
                        group["paired_effect_1_00_minus_0_70"],
                        metric=metric,
                        contrast_type="cooling_effect_1_00_minus_0_70",
                        alpha_scope=f"{alpha:.2f}",
                        delay_condition_id=str(delay),
                        repetitions=repetitions,
                        multiplicity_family="exploratory_cooling_effects",
                    )
                )

        metric_interactions = interactions[
            interactions["metric_id"].eq(metric.metric_id)
        ]
        for alpha in EXPECTED_ALPHAS:
            alpha_rows = metric_interactions[
                metric_interactions["alpha"].eq(alpha)
            ]
            family = (
                "primary_alpha_stratified_timing_interactions"
                if metric.primary
                else f"secondary_alpha_stratified_{metric.metric_id}"
            )
            rows.append(
                summarize_contrast(
                    alpha_rows["timing_interaction_early_minus_late"],
                    metric=metric,
                    contrast_type="timing_interaction_cooling_early_minus_late",
                    alpha_scope=f"{alpha:.2f}",
                    delay_condition_id=f"{EARLY_CONDITION}_vs_{LATE_CONDITION}",
                    repetitions=repetitions,
                    multiplicity_family=family,
                )
            )
            rows.append(
                summarize_contrast(
                    alpha_rows["early_minus_late_multiplier_0_70"],
                    metric=metric,
                    contrast_type="early_minus_late_within_multiplier_0_70",
                    alpha_scope=f"{alpha:.2f}",
                    delay_condition_id=f"{EARLY_CONDITION}_vs_{LATE_CONDITION}",
                    repetitions=repetitions,
                    multiplicity_family="exploratory_within_0_70",
                )
            )

        seed_level = metric_interactions.groupby("seed", sort=True).agg(
            timing_interaction=("timing_interaction_early_minus_late", "mean"),
            within_070=("early_minus_late_multiplier_0_70", "mean"),
        )
        rows.append(
            summarize_contrast(
                seed_level["timing_interaction"],
                metric=metric,
                contrast_type="timing_interaction_cooling_early_minus_late",
                alpha_scope="pooled_equal_weight_0.40_0.60_0.80",
                delay_condition_id=f"{EARLY_CONDITION}_vs_{LATE_CONDITION}",
                repetitions=repetitions,
                multiplicity_family=(
                    "single_prespecified_primary"
                    if metric.primary
                    else "exploratory_pooled_secondary"
                ),
            )
        )
        rows.append(
            summarize_contrast(
                seed_level["within_070"],
                metric=metric,
                contrast_type="early_minus_late_within_multiplier_0_70",
                alpha_scope="pooled_equal_weight_0.40_0.60_0.80",
                delay_condition_id=f"{EARLY_CONDITION}_vs_{LATE_CONDITION}",
                repetitions=repetitions,
                multiplicity_family="exploratory_within_0_70",
            )
        )

    statistics = pd.DataFrame.from_records(rows)
    stratified = statistics[
        statistics["contrast_type"].eq(
            "timing_interaction_cooling_early_minus_late"
        )
        & statistics["alpha_scope"].isin([f"{alpha:.2f}" for alpha in EXPECTED_ALPHAS])
    ]
    for _, family_rows in stratified.groupby("metric_id", sort=False):
        statistics.loc[family_rows.index, "holm_p_alpha"] = _holm_adjust(
            family_rows["exact_sign_flip_p"]
        )
    return statistics.sort_values(
        ["metric_id", "contrast_type", "alpha_scope", "delay_condition_id"]
    ).reset_index(drop=True)


def build_figure_source(
    paired: pd.DataFrame,
    interactions: pd.DataFrame,
    statistics: pd.DataFrame,
) -> pd.DataFrame:
    """Create one tidy source table for the planned Python paper figure."""

    records: list[dict[str, object]] = []
    primary_pairs = paired[paired["metric_id"].eq(PRIMARY_METRIC_ID)]
    for row in primary_pairs.itertuples(index=False):
        records.append(
            {
                "panel_id": "A",
                "record_type": "seed_paired_effect",
                "metric_id": row.metric_id,
                "alpha_scope": f"{row.alpha:.2f}",
                "delay_condition_id": row.delay_condition_id,
                "seed": row.seed,
                "estimate": row.paired_effect_1_00_minus_0_70,
                "ci_low": np.nan,
                "ci_high": np.nan,
                "p_exact": np.nan,
                "p_holm": np.nan,
                "hedges_gz": np.nan,
                "n_seeds": np.nan,
            }
        )
    primary_cooling = statistics[
        statistics["metric_id"].eq(PRIMARY_METRIC_ID)
        & statistics["contrast_type"].eq("cooling_effect_1_00_minus_0_70")
    ]
    for row in primary_cooling.itertuples(index=False):
        records.append(
            {
                "panel_id": "A",
                "record_type": "summary",
                "metric_id": row.metric_id,
                "alpha_scope": row.alpha_scope,
                "delay_condition_id": row.delay_condition_id,
                "seed": np.nan,
                "estimate": row.estimate,
                "ci_low": row.bootstrap_ci_low,
                "ci_high": row.bootstrap_ci_high,
                "p_exact": row.exact_sign_flip_p,
                "p_holm": row.holm_p_alpha,
                "hedges_gz": row.hedges_gz,
                "n_seeds": row.n_seeds,
            }
        )

    primary_interactions = interactions[
        interactions["metric_id"].eq(PRIMARY_METRIC_ID)
    ]
    for row in primary_interactions.itertuples(index=False):
        records.append(
            {
                "panel_id": "B",
                "record_type": "seed_timing_interaction",
                "metric_id": row.metric_id,
                "alpha_scope": f"{row.alpha:.2f}",
                "delay_condition_id": f"{EARLY_CONDITION}_vs_{LATE_CONDITION}",
                "seed": row.seed,
                "estimate": row.timing_interaction_early_minus_late,
                "ci_low": np.nan,
                "ci_high": np.nan,
                "p_exact": np.nan,
                "p_holm": np.nan,
                "hedges_gz": np.nan,
                "n_seeds": np.nan,
            }
        )
    interaction_stats = statistics[
        statistics["metric_id"].eq(PRIMARY_METRIC_ID)
        & statistics["contrast_type"].eq(
            "timing_interaction_cooling_early_minus_late"
        )
    ]
    for row in interaction_stats.itertuples(index=False):
        records.append(
            {
                "panel_id": "B",
                "record_type": "summary",
                "metric_id": row.metric_id,
                "alpha_scope": row.alpha_scope,
                "delay_condition_id": row.delay_condition_id,
                "seed": np.nan,
                "estimate": row.estimate,
                "ci_low": row.bootstrap_ci_low,
                "ci_high": row.bootstrap_ci_high,
                "p_exact": row.exact_sign_flip_p,
                "p_holm": row.holm_p_alpha,
                "hedges_gz": row.hedges_gz,
                "n_seeds": row.n_seeds,
            }
        )

    within_070 = statistics[
        statistics["metric_id"].eq(PRIMARY_METRIC_ID)
        & statistics["contrast_type"].eq(
            "early_minus_late_within_multiplier_0_70"
        )
    ]
    for row in within_070.itertuples(index=False):
        records.append(
            {
                "panel_id": "C",
                "record_type": "summary",
                "metric_id": row.metric_id,
                "alpha_scope": row.alpha_scope,
                "delay_condition_id": row.delay_condition_id,
                "seed": np.nan,
                "estimate": row.estimate,
                "ci_low": row.bootstrap_ci_low,
                "ci_high": row.bootstrap_ci_high,
                "p_exact": row.exact_sign_flip_p,
                "p_holm": row.holm_p_alpha,
                "hedges_gz": row.hedges_gz,
                "n_seeds": row.n_seeds,
            }
        )

    downstream = statistics[
        statistics["contrast_type"].eq(
            "timing_interaction_cooling_early_minus_late"
        )
        & statistics["alpha_scope"].eq(
            "pooled_equal_weight_0.40_0.60_0.80"
        )
    ]
    for row in downstream.itertuples(index=False):
        records.append(
            {
                "panel_id": "D",
                "record_type": "summary",
                "metric_id": row.metric_id,
                "alpha_scope": row.alpha_scope,
                "delay_condition_id": row.delay_condition_id,
                "seed": np.nan,
                "estimate": row.estimate,
                "ci_low": row.bootstrap_ci_low,
                "ci_high": row.bootstrap_ci_high,
                "p_exact": row.exact_sign_flip_p,
                "p_holm": row.holm_p_alpha,
                "hedges_gz": row.hedges_gz,
                "n_seeds": row.n_seeds,
            }
        )
    figure = pd.DataFrame.from_records(records)
    figure["evidence_status"] = "pilot_only_not_formal_evidence"
    return figure.sort_values(
        ["panel_id", "record_type", "metric_id", "alpha_scope", "delay_condition_id", "seed"],
        na_position="last",
    ).reset_index(drop=True)


def _fmt(value: object, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    return f"{float(value):.{digits}f}"


def _markdown_table(frame: pd.DataFrame, columns: list[tuple[str, str]]) -> str:
    header = "| " + " | ".join(label for _, label in columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, separator]
    for row in frame.itertuples(index=False):
        mapping = row._asdict()
        cells: list[str] = []
        for key, _ in columns:
            value = mapping[key]
            if key in {
                "estimate",
                "bootstrap_ci_low",
                "bootstrap_ci_high",
                "exact_sign_flip_p",
                "holm_p_alpha",
                "hedges_gz",
            }:
                cells.append(_fmt(value))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_report(
    *,
    source_path: Path,
    frame: pd.DataFrame,
    delays: list[str],
    seeds: list[int],
    statistics: pd.DataFrame,
    repetitions: int,
) -> str:
    primary = statistics[statistics["metric_id"].eq(PRIMARY_METRIC_ID)]
    pooled = primary[
        primary["contrast_type"].eq(
            "timing_interaction_cooling_early_minus_late"
        )
        & primary["alpha_scope"].eq(
            "pooled_equal_weight_0.40_0.60_0.80"
        )
    ].iloc[0]
    if pooled["bootstrap_ci_low"] > 0.0:
        conclusion = "本次pilot中，早回应的降温收益大于晚回应。"
    elif pooled["bootstrap_ci_high"] < 0.0:
        conclusion = "本次pilot中，晚回应的降温收益大于早回应。"
    else:
        conclusion = (
            "本次pilot未检出早回应与晚回应在降温收益上的稳定差异；"
            "这不等于证明二者完全相同。"
        )

    alpha_interactions = primary[
        primary["contrast_type"].eq(
            "timing_interaction_cooling_early_minus_late"
        )
        & primary["alpha_scope"].isin([f"{alpha:.2f}" for alpha in EXPECTED_ALPHAS])
    ][
        [
            "alpha_scope",
            "n_seeds",
            "estimate",
            "bootstrap_ci_low",
            "bootstrap_ci_high",
            "exact_sign_flip_p",
            "holm_p_alpha",
            "hedges_gz",
        ]
    ]
    cooling = primary[
        primary["contrast_type"].eq("cooling_effect_1_00_minus_0_70")
        & primary["delay_condition_id"].isin([EARLY_CONDITION, LATE_CONDITION])
    ][
        [
            "alpha_scope",
            "delay_condition_id",
            "n_seeds",
            "estimate",
            "bootstrap_ci_low",
            "bootstrap_ci_high",
            "exact_sign_flip_p",
            "hedges_gz",
        ]
    ]
    within = primary[
        primary["contrast_type"].eq("early_minus_late_within_multiplier_0_70")
    ][
        [
            "alpha_scope",
            "n_seeds",
            "estimate",
            "bootstrap_ci_low",
            "bootstrap_ci_high",
            "exact_sign_flip_p",
            "hedges_gz",
        ]
    ]
    seed_note = (
        "种子数达到建议的pilot筛查下限（12）。"
        if len(seeds) >= 12
        else "种子数少于12；本结果只能用于管道与大效应筛查。"
    )

    return f"""# Version 3 小规模配对实验统计报告

> **证据状态：pilot，仅用于机制与可检测性检查，不是正式实验结果，也不是现实世界因果证据。**

## 结论摘要

{conclusion}

主交互定义为：`[log1p(AUC)_1.00 - log1p(AUC)_0.70]_early - [log1p(AUC)_1.00 - log1p(AUC)_0.70]_late`。正值表示早回应的30%降温收益更强，负值表示晚回应更强。

三个alpha等权汇总的交互估计为 **{_fmt(pooled['estimate'])}**，按共同种子bootstrap得到的95% CI为 **[{_fmt(pooled['bootstrap_ci_low'])}, {_fmt(pooled['bootstrap_ci_high'])}]**，精确符号翻转 `p={_fmt(pooled['exact_sign_flip_p'])}`，Hedges `g_z={_fmt(pooled['hedges_gz'])}`。

{seed_note}

## 实验与数据完整性

- 输入：`{source_path.name}`
- 运行行数：{len(frame)}
- 共同随机种子：{len(seeds)}个（{min(seeds)}–{max(seeds)}）
- alpha：0.40、0.60、0.80
- 回应热度乘数：1.00与0.70
- 输入时延条件：{', '.join(delays)}
- 主要早晚对比：`{EARLY_CONDITION}` 对 `{LATE_CONDITION}`
- 每个 `seed × alpha × delay` 都同时具有1.00和0.70，未把旧V2结果混作V3对照。

## 主指标

主指标是回应后14日请愿热度积分的 `log1p` 变换。回应后的局部窗口用于捕捉一次性热度乘数的短期后果；末100步发生在回应和请愿关闭之后，不能替代本主指标。

### 0.70相对1.00的配对降温效应

正值表示0.70组的回应后14日热度AUC较低。

{_markdown_table(cooling, [
    ('alpha_scope', 'alpha'),
    ('delay_condition_id', '时延'),
    ('n_seeds', 'n'),
    ('estimate', '估计'),
    ('bootstrap_ci_low', '95% CI下限'),
    ('bootstrap_ci_high', '95% CI上限'),
    ('exact_sign_flip_p', '精确p'),
    ('hedges_gz', 'Hedges gz'),
])}

### 早晚时机 × 降温机制交互

alpha分层的三个交互属于同一个检验族，`Holm p`控制这三个比较的家族错误率。

{_markdown_table(alpha_interactions, [
    ('alpha_scope', 'alpha'),
    ('n_seeds', 'n'),
    ('estimate', '交互估计'),
    ('bootstrap_ci_low', '95% CI下限'),
    ('bootstrap_ci_high', '95% CI上限'),
    ('exact_sign_flip_p', '原始精确p'),
    ('holm_p_alpha', 'Holm p'),
    ('hedges_gz', 'Hedges gz'),
])}

### 仅在0.70组内比较早回应与晚回应

该比较回答0.70组是否存在表面早晚差异，但不能单独隔离30%降温机制；因而必须与上面的差分中的差分共同解释。

{_markdown_table(within, [
    ('alpha_scope', 'alpha范围'),
    ('n_seeds', 'n'),
    ('estimate', '早－晚'),
    ('bootstrap_ci_low', '95% CI下限'),
    ('bootstrap_ci_high', '95% CI上限'),
    ('exact_sign_flip_p', '精确p'),
    ('hedges_gz', 'Hedges gz'),
])}

## 统计方法

1. 随机种子是唯一推断与重抽样单位；没有把同一种子的不同alpha或条件当成独立观测。
2. 95% CI通过按种子整块重抽样{repetitions:,}次得到。
3. 双侧p值枚举所有 `2^n` 个符号组合，是精确符号翻转检验，而非大样本近似。
4. 效应量为小样本校正的配对标准化均值差Hedges `g_z`。
5. 唯一预设主检验是三个alpha等权汇总的早晚降温交互；alpha分层交互使用Holm校正。其他终点和组内比较均为探索性结果。
6. 置信区间只描述模型随机种子造成的Monte Carlo不确定性，不代表英国请愿者或中国公众总体的抽样误差。

## 解释边界

- `response_heat_multiplier=1.00`仍然发布政府回应，因此它是“无强制降温”对照，不是“无政府回应”对照。
- 检出0.70相对1.00的差异只能说明模型中的降温机制产生了后果，不能证明现实政府回应必然降低30%舆情热度。
- 未检出早晚交互应表述为“在本pilot规模和参数下未检出”，不能写成“早晚完全没有差异”。
- 正式论文结论必须由预先固定设计、至少50个共同种子及完整发布QA的正式实验支持。
"""


def _safe_output_dir(path: Path) -> Path:
    resolved_root = V3_ROOT.resolve()
    resolved = path.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError("all Version 3 analysis outputs must stay inside the V3 directory")
    return resolved


def write_outputs(
    *,
    paired: pd.DataFrame,
    interactions: pd.DataFrame,
    statistics: pd.DataFrame,
    figure_source: pd.DataFrame,
    report: str,
    output_dir: Path,
    overwrite: bool,
) -> list[Path]:
    output_dir = _safe_output_dir(output_dir)
    paths = [output_dir / filename for filename in OUTPUT_FILENAMES.values()]
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "refusing to overwrite existing pilot analysis outputs: "
            + ", ".join(path.name for path in existing)
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    paired.to_csv(paths[0], index=False, encoding="utf-8-sig")
    interactions.to_csv(paths[1], index=False, encoding="utf-8-sig")
    statistics.to_csv(paths[2], index=False, encoding="utf-8-sig")
    figure_source.to_csv(paths[3], index=False, encoding="utf-8-sig")
    paths[4].write_text(report, encoding="utf-8")
    return paths


def analyze(
    *,
    input_path: Path,
    output_dir: Path,
    repetitions: int = DEFAULT_BOOTSTRAP_REPETITIONS,
    overwrite: bool = False,
) -> list[Path]:
    if repetitions < 1_000:
        raise ValueError("bootstrap repetitions must be at least 1,000")
    frame, delays, seeds = load_and_validate(input_path)
    values = build_transformed_values(frame)
    paired = build_paired_effects(values)
    interactions = build_timing_interactions(paired)
    statistics = build_statistics(
        paired, interactions, repetitions=repetitions
    )
    figure_source = build_figure_source(paired, interactions, statistics)
    report = build_report(
        source_path=input_path,
        frame=frame,
        delays=delays,
        seeds=seeds,
        statistics=statistics,
        repetitions=repetitions,
    )
    return write_outputs(
        paired=paired,
        interactions=interactions,
        statistics=statistics,
        figure_source=figure_source,
        report=report,
        output_dir=output_dir,
        overwrite=overwrite,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--bootstrap-repetitions",
        type=int,
        default=DEFAULT_BOOTSTRAP_REPETITIONS,
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace existing V3 pilot analysis outputs",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = analyze(
        input_path=args.input,
        output_dir=args.output_dir,
        repetitions=args.bootstrap_repetitions,
        overwrite=args.overwrite,
    )
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
