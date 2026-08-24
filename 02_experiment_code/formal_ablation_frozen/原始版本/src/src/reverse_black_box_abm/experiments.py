"""Parameter sweeps and change-point estimation for the ABM."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .model import ReverseBlackBoxSimulation, SimulationConfig


SUMMARY_METRICS = (
    "mean_agenda_divergence",
    "system_stability",
    "mean_agenda_share",
    "mean_official_attention_share",
    "mean_trust",
    "mean_learning_cost",
    "storm_frequency_per_100_steps",
    "storm_time_share",
    "storm_mean_peak",
    "storm_max_peak",
    "storm_mean_duration",
    "total_interactions",
)


def parse_alpha_range(specification: str) -> list[float]:
    """Parse either ``0,0.2,0.5`` or inclusive ``start:stop:step`` syntax."""

    text = specification.strip()
    if ":" not in text:
        values = [float(value.strip()) for value in text.split(",") if value.strip()]
    else:
        parts = [float(value.strip()) for value in text.split(":")]
        if len(parts) != 3:
            raise ValueError("alpha range must be start:stop:step")
        start, stop, step = parts
        if step <= 0:
            raise ValueError("alpha step must be positive")
        count = int(np.floor((stop - start) / step + 1e-9)) + 1
        values = [start + index * step for index in range(count)]
        if values and values[-1] < stop - 1e-9:
            values.append(stop)
    cleaned = sorted({round(value, 10) for value in values})
    if not cleaned or cleaned[0] < 0.0 or cleaned[-1] > 1.0:
        raise ValueError("all alpha values must fall between 0 and 1")
    return cleaned


def summarize_replicates(replicates: pd.DataFrame) -> pd.DataFrame:
    """Aggregate replicate-level summaries by alpha."""

    rows: list[dict[str, Any]] = []
    for alpha, group in replicates.groupby("alpha", sort=True):
        row: dict[str, Any] = {
            "alpha": float(alpha),
            "replicates": int(len(group)),
        }
        for metric in SUMMARY_METRICS:
            if metric not in group:
                continue
            values = group[metric].astype(float)
            row[metric] = float(values.mean())
            row[f"{metric}_sd"] = float(values.std(ddof=0))
        rows.append(row)
    return pd.DataFrame(rows).sort_values("alpha").reset_index(drop=True)


def detect_critical_alpha(
    summary: pd.DataFrame,
    metric: str = "mean_agenda_divergence",
    minimum_range: float = 0.015,
) -> float | None:
    """Estimate the critical alpha as the point of steepest sustained change.

    A three-point smoothed series is used before calculating the numerical
    derivative.  If the observed metric is effectively flat, ``None`` is
    returned instead of inventing a threshold.
    """

    if len(summary) < 3 or metric not in summary:
        return None
    ordered = summary.sort_values("alpha")
    x = ordered["alpha"].to_numpy(dtype=float)
    y = ordered[metric].to_numpy(dtype=float)
    if not np.all(np.isfinite(y)) or float(np.ptp(y)) < minimum_range:
        return None

    smoothed = (
        pd.Series(y)
        .rolling(window=3, center=True, min_periods=1)
        .mean()
        .to_numpy()
    )
    gradient = np.gradient(smoothed, x)
    if metric in {"mean_trust", "mean_agenda_share"}:
        index = int(np.argmin(gradient))
    else:
        index = int(np.argmax(gradient))
    return float(x[index])


def bootstrap_critical_interval(
    replicates: pd.DataFrame,
    *,
    metric: str = "mean_agenda_divergence",
    samples: int = 200,
    seed: int = 2026,
) -> tuple[float | None, float | None]:
    """Bootstrap a percentile interval for the estimated critical point."""

    if samples <= 0 or replicates.empty:
        return None, None
    rng = np.random.default_rng(seed)
    grouped = {
        float(alpha): group.reset_index(drop=True)
        for alpha, group in replicates.groupby("alpha", sort=True)
    }
    estimates: list[float] = []
    for _ in range(samples):
        sampled_groups = []
        for group in grouped.values():
            indices = rng.integers(0, len(group), size=len(group))
            sampled_groups.append(group.iloc[indices])
        sampled = pd.concat(sampled_groups, ignore_index=True)
        estimate = detect_critical_alpha(
            summarize_replicates(sampled), metric=metric
        )
        if estimate is not None:
            estimates.append(estimate)
    if not estimates:
        return None, None
    lower, upper = np.quantile(
        estimates, [0.025, 0.975], method="nearest"
    )
    return float(lower), float(upper)


def run_alpha_sweep(
    base_config: SimulationConfig,
    alphas: Iterable[float],
    *,
    replicates: int = 5,
    bootstrap_samples: int = 200,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Run all alpha/replicate combinations and return tidy results."""

    if replicates <= 0:
        raise ValueError("replicates must be positive")
    alpha_values = sorted({float(alpha) for alpha in alphas})
    if not alpha_values:
        raise ValueError("at least one alpha value is required")

    rows: list[dict[str, Any]] = []
    for alpha in alpha_values:
        for replicate in range(replicates):
            # Common random numbers: replicate r uses the same seed for every
            # alpha, reducing Monte Carlo noise in between-alpha comparisons.
            seed = int(base_config.seed + replicate)
            config = replace(base_config, alpha=alpha, seed=seed)
            result = ReverseBlackBoxSimulation(config).run()
            row = dict(result.summary)
            row["replicate"] = replicate
            rows.append(row)

    replicate_frame = pd.DataFrame(rows).sort_values(
        ["alpha", "replicate"]
    ).reset_index(drop=True)
    summary = summarize_replicates(replicate_frame)
    critical = detect_critical_alpha(summary)
    lower, upper = bootstrap_critical_interval(
        replicate_frame,
        samples=bootstrap_samples,
        seed=base_config.seed + 911,
    )
    critical_report = {
        "metric": "mean_agenda_divergence",
        "critical_alpha": critical,
        "bootstrap_95_percent_interval": [lower, upper],
        "method": (
            "three-point smoothing plus maximum numerical slope; "
            "common random numbers across alpha; nearest-grid bootstrap quantiles"
        ),
        "bootstrap_samples": bootstrap_samples,
        "interpretation": (
            "Exploratory change point. It is a simulation diagnostic, "
            "not an empirically estimated causal threshold."
        ),
    }
    return replicate_frame, summary, critical_report
