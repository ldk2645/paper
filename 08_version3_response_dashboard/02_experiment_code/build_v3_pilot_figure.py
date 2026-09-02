"""Build the submission-style Version 3 pilot figure with Python only."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats


# Mandatory editable-text and publication-font settings.
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Liberation Sans"]
plt.rcParams["svg.fonttype"] = "none"
plt.rcParams["pdf.fonttype"] = 42
plt.rcParams.update({"svg.fonttype": "none", "pdf.fonttype": 42})
plt.rcParams["font.size"] = 7
plt.rcParams["axes.labelsize"] = 7
plt.rcParams["axes.titlesize"] = 7.5
plt.rcParams["xtick.labelsize"] = 6.5
plt.rcParams["ytick.labelsize"] = 6.5
plt.rcParams["legend.fontsize"] = 6.2
plt.rcParams["axes.linewidth"] = 0.8
plt.rcParams["xtick.major.width"] = 0.7
plt.rcParams["ytick.major.width"] = 0.7
plt.rcParams["xtick.major.size"] = 3
plt.rcParams["ytick.major.size"] = 3
plt.rcParams["legend.frameon"] = False


HERE = Path(__file__).resolve().parent
V3_ROOT = HERE.parent
PILOT_DIR = V3_ROOT / "05_outputs" / "pilot"
DEFAULT_RUNS = PILOT_DIR / "v3_pilot_run_summaries.csv"
DEFAULT_PAIRED = PILOT_DIR / "v3_pilot_paired_effects.csv"
DEFAULT_INTERACTIONS = PILOT_DIR / "v3_pilot_timing_interactions.csv"
DEFAULT_STATISTICS = PILOT_DIR / "v3_pilot_statistics.csv"
DEFAULT_OUTPUT_DIR = V3_ROOT / "04_figures"

PRIMARY_METRIC = "primary_log1p_post14_heat_auc"
EARLY = "early_p05_11"
LATE = "late_p95_57"
ALPHAS = (0.40, 0.60, 0.80)
MULTIPLIERS = (0.70, 1.00)
EXPECTED_SEEDS = tuple(range(73000, 73010))

COLORS = {
    "neutral": "#5B5B5B",
    "neutral_light": "#B9B9B9",
    "cooling": "#0F4D92",
    "early": "#0F4D92",
    "late": "#9A4D8E",
    "pooled": "#272727",
    "reach": "#42949E",
    "grid": "#DEDEDE",
}


def _safe_output_dir(path: Path) -> Path:
    root = V3_ROOT.resolve()
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("figure outputs must stay inside Version 3")
    return resolved


def _validate_inputs(
    runs: pd.DataFrame,
    paired: pd.DataFrame,
    interactions: pd.DataFrame,
    statistics_frame: pd.DataFrame,
) -> None:
    required_runs = {
        "run_id",
        "alpha",
        "seed",
        "delay_condition_id",
        "response_heat_multiplier",
        "petition_heat_auc_post_14_days",
        "routine_government_posts_published",
        "mean_routine_government_reach_share_open_period",
    }
    missing = sorted(required_runs.difference(runs.columns))
    if missing:
        raise ValueError(f"run summaries are missing columns: {missing}")
    if len(runs) != 120 or runs["run_id"].duplicated().any():
        raise ValueError("the figure requires the complete 120-run pilot panel")
    if tuple(sorted(runs["alpha"].unique())) != ALPHAS:
        raise ValueError("unexpected alpha levels")
    if tuple(sorted(runs["seed"].unique())) != EXPECTED_SEEDS:
        raise ValueError("unexpected common-seed panel")
    if set(runs["delay_condition_id"]) != {EARLY, LATE}:
        raise ValueError("unexpected delay conditions")
    if tuple(sorted(runs["response_heat_multiplier"].unique())) != MULTIPLIERS:
        raise ValueError("unexpected response heat multipliers")
    if not runs["routine_government_posts_published"].eq(300).all():
        raise ValueError("every run must have 300 routine government posts")
    numeric = [
        "petition_heat_auc_post_14_days",
        "mean_routine_government_reach_share_open_period",
    ]
    if not np.isfinite(runs[numeric].to_numpy(dtype=float)).all():
        raise ValueError("non-finite values found in figure inputs")
    if (runs["petition_heat_auc_post_14_days"] < 0).any():
        raise ValueError("heat AUC cannot be negative")
    if not runs["mean_routine_government_reach_share_open_period"].between(
        0.0, 1.0
    ).all():
        raise ValueError("reach must lie in [0, 1]")
    if not {PRIMARY_METRIC}.issubset(set(paired["metric_id"])):
        raise ValueError("paired effects do not contain the primary metric")
    if not {PRIMARY_METRIC}.issubset(set(interactions["metric_id"])):
        raise ValueError("timing interactions do not contain the primary metric")
    if not {PRIMARY_METRIC}.issubset(set(statistics_frame["metric_id"])):
        raise ValueError("statistics do not contain the primary metric")


def _mean_t_ci(values: np.ndarray) -> tuple[float, float, float]:
    values = np.asarray(values, dtype=float)
    if len(values) < 2 or not np.isfinite(values).all():
        raise ValueError("mean CI requires at least two finite seed values")
    center = float(values.mean())
    half = float(stats.t.ppf(0.975, len(values) - 1) * stats.sem(values))
    return center, center - half, center + half


def _geometric_mean_t_ci(values: np.ndarray) -> tuple[float, float, float]:
    values = np.asarray(values, dtype=float)
    if np.any(values <= 0.0):
        raise ValueError("log-scale reach summary requires strictly positive values")
    center, low, high = _mean_t_ci(np.log10(values))
    return 10.0**center, 10.0**low, 10.0**high


def _panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(
        -0.14,
        1.05,
        label,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=8,
        fontweight="bold",
    )


def _clean_axis(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color=COLORS["grid"], linewidth=0.45, zorder=0)
    ax.set_axisbelow(True)


def build_source_data(
    runs: pd.DataFrame,
    paired: pd.DataFrame,
    interactions: pd.DataFrame,
    statistics_frame: pd.DataFrame,
) -> pd.DataFrame:
    records: list[dict[str, object]] = []

    transformed = runs.assign(
        value=np.log1p(runs["petition_heat_auc_post_14_days"].to_numpy(float))
    )
    for row in transformed.itertuples(index=False):
        records.append(
            {
                "panel_id": "a",
                "record_type": "seed_value",
                "alpha_scope": f"{row.alpha:.2f}",
                "delay_condition_id": row.delay_condition_id,
                "response_heat_multiplier": row.response_heat_multiplier,
                "seed": row.seed,
                "estimate": row.value,
                "ci_low": np.nan,
                "ci_high": np.nan,
                "interval": "none_seed_value",
                "definition": "log1p_petition_heat_auc_post_14_days",
            }
        )
    for keys, group in transformed.groupby(
        ["alpha", "delay_condition_id", "response_heat_multiplier"], sort=True
    ):
        alpha, delay, multiplier = keys
        center, low, high = _mean_t_ci(group["value"].to_numpy(float))
        records.append(
            {
                "panel_id": "a",
                "record_type": "mean_95_t_ci",
                "alpha_scope": f"{alpha:.2f}",
                "delay_condition_id": delay,
                "response_heat_multiplier": multiplier,
                "seed": np.nan,
                "estimate": center,
                "ci_low": low,
                "ci_high": high,
                "interval": "two_sided_95_percent_t_interval_over_seeds",
                "definition": "log1p_petition_heat_auc_post_14_days",
            }
        )

    primary_pairs = paired[paired["metric_id"].eq(PRIMARY_METRIC)]
    cooling_stats = statistics_frame[
        statistics_frame["metric_id"].eq(PRIMARY_METRIC)
        & statistics_frame["contrast_type"].eq(
            "cooling_effect_1_00_minus_0_70"
        )
    ]
    for row in primary_pairs.itertuples(index=False):
        records.append(
            {
                "panel_id": "b",
                "record_type": "seed_paired_effect",
                "alpha_scope": f"{row.alpha:.2f}",
                "delay_condition_id": row.delay_condition_id,
                "response_heat_multiplier": np.nan,
                "seed": row.seed,
                "estimate": row.paired_effect_1_00_minus_0_70,
                "ci_low": np.nan,
                "ci_high": np.nan,
                "interval": "none_seed_value",
                "definition": "logAUC_1.00_minus_logAUC_0.70",
            }
        )
    for row in cooling_stats.itertuples(index=False):
        records.append(
            {
                "panel_id": "b",
                "record_type": "mean_seed_bootstrap_95_ci",
                "alpha_scope": row.alpha_scope,
                "delay_condition_id": row.delay_condition_id,
                "response_heat_multiplier": np.nan,
                "seed": np.nan,
                "estimate": row.estimate,
                "ci_low": row.bootstrap_ci_low,
                "ci_high": row.bootstrap_ci_high,
                "interval": "seed_block_bootstrap_95_percent_ci_10000",
                "definition": "logAUC_1.00_minus_logAUC_0.70",
            }
        )

    primary_interactions = interactions[
        interactions["metric_id"].eq(PRIMARY_METRIC)
    ]
    interaction_stats = statistics_frame[
        statistics_frame["metric_id"].eq(PRIMARY_METRIC)
        & statistics_frame["contrast_type"].eq(
            "timing_interaction_cooling_early_minus_late"
        )
    ]
    for row in primary_interactions.itertuples(index=False):
        records.append(
            {
                "panel_id": "c",
                "record_type": "seed_timing_interaction",
                "alpha_scope": f"{row.alpha:.2f}",
                "delay_condition_id": f"{EARLY}_vs_{LATE}",
                "response_heat_multiplier": np.nan,
                "seed": row.seed,
                "estimate": row.timing_interaction_early_minus_late,
                "ci_low": np.nan,
                "ci_high": np.nan,
                "interval": "none_seed_value",
                "definition": "cooling_benefit_early_minus_late",
            }
        )
    for row in interaction_stats.itertuples(index=False):
        records.append(
            {
                "panel_id": "c",
                "record_type": "mean_seed_bootstrap_95_ci",
                "alpha_scope": row.alpha_scope,
                "delay_condition_id": row.delay_condition_id,
                "response_heat_multiplier": np.nan,
                "seed": np.nan,
                "estimate": row.estimate,
                "ci_low": row.bootstrap_ci_low,
                "ci_high": row.bootstrap_ci_high,
                "p_exact": row.exact_sign_flip_p,
                "p_holm": row.holm_p_alpha,
                "interval": "seed_block_bootstrap_95_percent_ci_10000",
                "definition": "cooling_benefit_early_minus_late",
            }
        )

    seed_reach = (
        runs.groupby(["alpha", "seed"], sort=True)[
            "mean_routine_government_reach_share_open_period"
        ]
        .mean()
        .mul(100.0)
        .rename("reach_percent")
        .reset_index()
    )
    for row in seed_reach.itertuples(index=False):
        records.append(
            {
                "panel_id": "d",
                "record_type": "seed_factorial_average",
                "alpha_scope": f"{row.alpha:.2f}",
                "delay_condition_id": "averaged_over_delay_and_multiplier",
                "response_heat_multiplier": np.nan,
                "seed": row.seed,
                "estimate": row.reach_percent,
                "ci_low": np.nan,
                "ci_high": np.nan,
                "interval": "none_seed_value",
                "definition": "routine_government_reach_percent_open_period",
            }
        )
    for alpha, group in seed_reach.groupby("alpha", sort=True):
        center, low, high = _geometric_mean_t_ci(
            group["reach_percent"].to_numpy(float)
        )
        records.append(
            {
                "panel_id": "d",
                "record_type": "geometric_mean_95_t_ci",
                "alpha_scope": f"{alpha:.2f}",
                "delay_condition_id": "averaged_over_delay_and_multiplier",
                "response_heat_multiplier": np.nan,
                "seed": np.nan,
                "estimate": center,
                "ci_low": low,
                "ci_high": high,
                "interval": "95_percent_t_interval_on_log10_seed_values",
                "definition": "routine_government_reach_percent_open_period",
            }
        )

    source = pd.DataFrame.from_records(records)
    source["n_common_seeds"] = 10
    source["evidence_status"] = "pilot_only_not_formal_evidence"
    return source.sort_values(
        ["panel_id", "record_type", "alpha_scope", "delay_condition_id", "seed"],
        na_position="last",
    ).reset_index(drop=True)


def _plot_panel_a(ax: plt.Axes, source: pd.DataFrame) -> None:
    summary = source[
        source["panel_id"].eq("a")
        & source["record_type"].eq("mean_95_t_ci")
    ]
    x = np.arange(len(ALPHAS), dtype=float)
    designs = [
        (EARLY, 1.00, COLORS["neutral"], "o", "-", "Early, multiplier 1.00"),
        (EARLY, 0.70, COLORS["cooling"], "o", "-", "Early, multiplier 0.70"),
        (LATE, 1.00, COLORS["neutral_light"], "s", "--", "Late, multiplier 1.00"),
        (LATE, 0.70, COLORS["late"], "s", "--", "Late, multiplier 0.70"),
    ]
    for delay, multiplier, color, marker, linestyle, label in designs:
        part = summary[
            summary["delay_condition_id"].eq(delay)
            & summary["response_heat_multiplier"].eq(multiplier)
        ].sort_values("alpha_scope")
        values = part["estimate"].to_numpy(float)
        low = part["ci_low"].to_numpy(float)
        high = part["ci_high"].to_numpy(float)
        ax.errorbar(
            x,
            values,
            yerr=np.vstack([values - low, high - values]),
            color=color,
            marker=marker,
            markersize=3.4,
            markerfacecolor="white" if multiplier == 1.00 else color,
            markeredgewidth=0.8,
            linewidth=1.1,
            linestyle=linestyle,
            capsize=2,
            capthick=0.7,
            label=label,
            zorder=3,
        )
    ax.set_xticks(x, [f"{alpha:.2f}" for alpha in ALPHAS])
    ax.set_xlabel("Recommendation weight, α")
    ax.set_ylabel("log(1 + 14-day heat AUC)")
    ax.set_title("Observed pilot cells", loc="left", pad=5)
    ax.legend(ncol=2, loc="upper left", columnspacing=0.9, handlelength=2.2)
    _clean_axis(ax)
    _panel_label(ax, "a")


def _plot_panel_b(ax: plt.Axes, source: pd.DataFrame) -> None:
    raw = source[
        source["panel_id"].eq("b")
        & source["record_type"].eq("seed_paired_effect")
    ]
    summary = source[
        source["panel_id"].eq("b")
        & source["record_type"].eq("mean_seed_bootstrap_95_ci")
    ]
    x = np.arange(len(ALPHAS), dtype=float)
    for delay, offset, color, marker, label in (
        (EARLY, -0.08, COLORS["early"], "o", "Early response (11 d)"),
        (LATE, 0.08, COLORS["late"], "s", "Late response (57 d)"),
    ):
        part_raw = raw[raw["delay_condition_id"].eq(delay)]
        for index, alpha in enumerate(ALPHAS):
            values = part_raw[
                part_raw["alpha_scope"].eq(f"{alpha:.2f}")
            ].sort_values("seed")["estimate"].to_numpy(float)
            seed_offsets = np.linspace(-0.035, 0.035, len(values))
            ax.scatter(
                np.full(len(values), x[index] + offset) + seed_offsets,
                values,
                s=7,
                color=color,
                alpha=0.32,
                linewidths=0,
                zorder=2,
            )
        part = summary[summary["delay_condition_id"].eq(delay)].sort_values(
            "alpha_scope"
        )
        values = part["estimate"].to_numpy(float)
        low = part["ci_low"].to_numpy(float)
        high = part["ci_high"].to_numpy(float)
        ax.errorbar(
            x + offset,
            values,
            yerr=np.vstack([values - low, high - values]),
            color=color,
            marker=marker,
            markersize=4,
            linewidth=1.2,
            capsize=2.2,
            capthick=0.8,
            label=label,
            zorder=4,
        )
    ax.axhline(0.0, color="#888888", linewidth=0.7, linestyle=":", zorder=1)
    ax.set_xticks(x, [f"{alpha:.2f}" for alpha in ALPHAS])
    ax.set_xlabel("Recommendation weight, α")
    ax.set_ylabel("Cooling benefit (log scale)")
    ax.set_title("Paired multiplier effect", loc="left", pad=5)
    ax.text(
        0.99,
        0.075,
        "Positive = lower heat under 0.70\nAll six exact p = 0.002",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=5.8,
        color="#555555",
    )
    ax.legend(loc="upper left")
    _clean_axis(ax)
    _panel_label(ax, "b")


def _plot_panel_c(ax: plt.Axes, source: pd.DataFrame) -> None:
    raw = source[
        source["panel_id"].eq("c")
        & source["record_type"].eq("seed_timing_interaction")
    ]
    summary = source[
        source["panel_id"].eq("c")
        & source["record_type"].eq("mean_seed_bootstrap_95_ci")
    ].copy()
    order = ["0.40", "0.60", "0.80", "pooled_equal_weight_0.40_0.60_0.80"]
    labels = ["α = 0.40", "α = 0.60", "α = 0.80", "Pooled"]
    y = np.arange(len(order), dtype=float)
    for index, alpha_scope in enumerate(order[:3]):
        values = raw[raw["alpha_scope"].eq(alpha_scope)].sort_values("seed")[
            "estimate"
        ].to_numpy(float)
        y_offsets = np.linspace(-0.12, 0.12, len(values))
        ax.scatter(
            values,
            np.full(len(values), y[index]) + y_offsets,
            s=7,
            color=COLORS["neutral_light"],
            alpha=0.55,
            linewidths=0,
            zorder=2,
        )
    for index, alpha_scope in enumerate(order):
        row = summary[summary["alpha_scope"].eq(alpha_scope)].iloc[0]
        color = COLORS["pooled"] if alpha_scope.startswith("pooled") else COLORS["cooling"]
        ax.errorbar(
            row["estimate"],
            y[index],
            xerr=np.asarray(
                [[row["estimate"] - row["ci_low"]], [row["ci_high"] - row["estimate"]]]
            ),
            color=color,
            marker="D" if alpha_scope.startswith("pooled") else "o",
            markersize=4.2,
            linewidth=1.25,
            capsize=2.2,
            capthick=0.8,
            zorder=4,
        )
    ax.axvline(0.0, color="#777777", linewidth=0.8, linestyle="--", zorder=1)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlabel("Early − late cooling benefit")
    ax.set_title("Timing × cooling interaction", loc="left", pad=5)
    pooled = summary[
        summary["alpha_scope"].str.startswith("pooled")
    ].iloc[0]
    ax.text(
        0.99,
        0.04,
        f"Pooled p = {pooled['p_exact']:.3f}",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=5.8,
        color="#555555",
    )
    _clean_axis(ax)
    ax.grid(axis="x", color=COLORS["grid"], linewidth=0.45)
    ax.grid(axis="y", visible=False)
    _panel_label(ax, "c")


def _plot_panel_d(ax: plt.Axes, source: pd.DataFrame) -> None:
    raw = source[
        source["panel_id"].eq("d")
        & source["record_type"].eq("seed_factorial_average")
    ]
    summary = source[
        source["panel_id"].eq("d")
        & source["record_type"].eq("geometric_mean_95_t_ci")
    ].sort_values("alpha_scope")
    x = np.arange(len(ALPHAS), dtype=float)
    for index, alpha in enumerate(ALPHAS):
        values = raw[raw["alpha_scope"].eq(f"{alpha:.2f}")].sort_values("seed")[
            "estimate"
        ].to_numpy(float)
        offsets = np.linspace(-0.055, 0.055, len(values))
        ax.scatter(
            np.full(len(values), x[index]) + offsets,
            values,
            s=8,
            color=COLORS["reach"],
            alpha=0.32,
            linewidths=0,
            zorder=2,
        )
    values = summary["estimate"].to_numpy(float)
    low = summary["ci_low"].to_numpy(float)
    high = summary["ci_high"].to_numpy(float)
    ax.errorbar(
        x,
        values,
        yerr=np.vstack([values - low, high - values]),
        color=COLORS["reach"],
        marker="o",
        markersize=4.2,
        linewidth=1.2,
        capsize=2.2,
        capthick=0.8,
        zorder=4,
    )
    ax.set_yscale("log")
    ax.set_yticks([0.1, 1.0, 10.0], ["0.1", "1", "10"])
    ax.set_xticks(x, [f"{alpha:.2f}" for alpha in ALPHAS])
    ax.set_xlabel("Recommendation weight, α")
    ax.set_ylabel("Routine-government reach (%)")
    ax.set_title("Publication is not exposure", loc="left", pad=5)
    ax.text(
        0.98,
        0.96,
        "300/300 days published\nin every pilot run",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=5.8,
        color="#555555",
    )
    _clean_axis(ax)
    _panel_label(ax, "d")


def build_figure(
    *,
    runs_path: Path,
    paired_path: Path,
    interactions_path: Path,
    statistics_path: Path,
    output_dir: Path,
    overwrite: bool,
) -> list[Path]:
    runs = pd.read_csv(runs_path)
    paired = pd.read_csv(paired_path)
    interactions = pd.read_csv(interactions_path)
    statistics_frame = pd.read_csv(statistics_path)
    _validate_inputs(runs, paired, interactions, statistics_frame)
    source = build_source_data(runs, paired, interactions, statistics_frame)

    output_dir = _safe_output_dir(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base = output_dir / "Figure_V3_response_pilot"
    source_path = output_dir / "Figure_V3_response_pilot_source_data.csv"
    output_paths = [
        base.with_suffix(".svg"),
        base.with_suffix(".pdf"),
        base.with_suffix(".tiff"),
        base.with_suffix(".png"),
        source_path,
    ]
    existing = [path for path in output_paths if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "refusing to overwrite figure outputs: "
            + ", ".join(path.name for path in existing)
        )

    width_mm = 183
    height_mm = 137
    fig = plt.figure(figsize=(width_mm / 25.4, height_mm / 25.4))
    grid = fig.add_gridspec(
        2,
        2,
        left=0.085,
        right=0.985,
        bottom=0.10,
        top=0.96,
        wspace=0.35,
        hspace=0.42,
    )
    ax_a = fig.add_subplot(grid[0, 0])
    ax_b = fig.add_subplot(grid[0, 1])
    ax_c = fig.add_subplot(grid[1, 0])
    ax_d = fig.add_subplot(grid[1, 1])

    _plot_panel_a(ax_a, source)
    _plot_panel_b(ax_b, source)
    _plot_panel_c(ax_c, source)
    _plot_panel_d(ax_d, source)

    source.to_csv(source_path, index=False, encoding="utf-8-sig")
    fig.savefig(base.with_suffix(".svg"), facecolor="white")
    fig.savefig(base.with_suffix(".pdf"), facecolor="white")
    fig.savefig(
        base.with_suffix(".tiff"),
        dpi=600,
        facecolor="white",
        pil_kwargs={"compression": "tiff_lzw"},
    )
    fig.savefig(base.with_suffix(".png"), dpi=600, facecolor="white")
    plt.close(fig)
    return output_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--paired", type=Path, default=DEFAULT_PAIRED)
    parser.add_argument("--interactions", type=Path, default=DEFAULT_INTERACTIONS)
    parser.add_argument("--statistics", type=Path, default=DEFAULT_STATISTICS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for path in build_figure(
        runs_path=args.runs,
        paired_path=args.paired,
        interactions_path=args.interactions,
        statistics_path=args.statistics,
        output_dir=args.output_dir,
        overwrite=args.overwrite,
    ):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
