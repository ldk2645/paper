"""Build Supplementary Fig. S2 from the formal sensitivity outputs.

Figure contract
---------------
Claim: the figure reports, without assuming robustness in advance, how each
parameter, execution-order variant and response strategy changes the detected
critical alpha and the full agenda-divergence curve.
Evidence: panels a and b show seed-block bootstrap 95% intervals for the
registered maximum-gradient estimator; panel c shows mean +/- 95% t intervals
over 50 common random seeds at every alpha.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image


HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
PROCESSED = PACKAGE / "03_data" / "sensitivity" / "processed"
DEFAULT_OUT = PACKAGE / "04_figures" / "supplementary"
SOURCE_OUT = PACKAGE / "03_data" / "sensitivity" / "source_data"

WIDTH_MM = 183.0
HEIGHT_MM = 150.0
MM_PER_INCH = 25.4
BASELINE_COLOR = "#4D4D4D"
LOW_COLOR = "#0072B2"
HIGH_COLOR = "#D55E00"

PARAMETER_ROWS = (
    ("heat_decay_085", "Heat retention λ = 0.85", "lower"),
    ("heat_decay_090", "Heat retention λ = 0.90", "lower"),
    ("response_delay_5", "Response delay δ = 5", "higher"),
    ("response_delay_8", "Response delay δ = 8", "higher"),
    ("drift_rate_001", "Preference drift γ = 0.01", "lower"),
    ("drift_rate_005", "Preference drift γ = 0.05", "higher"),
    ("trust_update_003", "Trust update τT = 0.03", "lower"),
    ("trust_update_012", "Trust update τT = 0.12", "higher"),
    ("trust_feedback_010", "Trust feedback s = 0.10", "lower"),
    ("trust_feedback_050", "Trust feedback s = 0.50", "higher"),
    ("response_threshold_010", "Response threshold θ = 0.10", "lower"),
    ("response_threshold_030", "Response threshold θ = 0.30", "higher"),
    ("response_retention_050", "Response heat retention ρ = 0.50", "lower"),
    ("response_retention_090", "Response heat retention ρ = 0.90", "higher"),
)

STRUCTURE_ROWS = (
    ("baseline", "Default / hard"),
    ("strategy_selective", "Selective response"),
    ("strategy_wait", "Wait response"),
    ("strategy_no_response", "No effective response"),
    ("order_new_information_after_recommendation", "New information after recommendation"),
    ("order_government_action_at_end", "Government action at step end"),
    ("order_decay_before_recommendation", "Decay before recommendation"),
)

CURVE_ROWS = (
    ("baseline", "Hard", "#0072B2", "-"),
    ("strategy_selective", "Selective", "#E69F00", (0, (4, 2))),
    ("strategy_wait", "Wait", "#009E73", (0, (2, 1.5))),
    ("strategy_no_response", "No effective response", "#CC79A7", (0, (6, 2, 1.5, 2))),
)


def configure_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 7.0,
            "axes.labelsize": 7.0,
            "xtick.labelsize": 6.3,
            "ytick.labelsize": 6.1,
            "legend.fontsize": 6.2,
            "axes.linewidth": 0.6,
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
            "xtick.major.size": 3.0,
            "ytick.major.size": 3.0,
            "xtick.direction": "out",
            "ytick.direction": "out",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def validate_inputs(critical: pd.DataFrame, curves: pd.DataFrame) -> None:
    required_critical = {
        "scenario_id",
        "critical_alpha",
        "critical_alpha_ci95_low",
        "critical_alpha_ci95_high",
        "identification_rate",
    }
    required_curves = {
        "scenario_id",
        "alpha",
        "metric",
        "n_seeds",
        "mean",
        "ci95_low",
        "ci95_high",
    }
    if missing := required_critical - set(critical.columns):
        raise ValueError(f"Critical-point table missing: {sorted(missing)}")
    if missing := required_curves - set(curves.columns):
        raise ValueError(f"Curve table missing: {sorted(missing)}")
    expected_ids = {row[0] for row in PARAMETER_ROWS + STRUCTURE_ROWS + CURVE_ROWS}
    if missing := expected_ids - set(critical["scenario_id"]):
        raise ValueError(f"Critical-point scenarios missing: {sorted(missing)}")
    selected = curves[
        curves["scenario_id"].isin([row[0] for row in CURVE_ROWS])
        & (curves["metric"] == "mean_agenda_divergence")
    ]
    counts = selected.groupby("scenario_id")["alpha"].nunique()
    if len(counts) != len(CURVE_ROWS) or not (counts == 21).all():
        raise ValueError("Each response curve must contain 21 alpha values")
    if not (selected["n_seeds"] == 50).all():
        raise ValueError("Each response curve point must summarize 50 seeds")
    finite_columns = ["mean", "ci95_low", "ci95_high"]
    if not np.isfinite(selected[finite_columns].to_numpy(float)).all():
        raise ValueError("Non-finite response-curve values")


def critical_axis_limits(critical: pd.DataFrame, scenario_ids: list[str]) -> tuple[float, float]:
    subset = critical[critical["scenario_id"].isin(scenario_ids)]
    values = subset[["critical_alpha_ci95_low", "critical_alpha_ci95_high"]].to_numpy(float)
    finite = values[np.isfinite(values)]
    if not len(finite):
        return 0.0, 1.0
    low_edge = round(float(finite.min() - 0.05), 10)
    high_edge = round(float(finite.max() + 0.05), 10)
    low = max(0.0, np.floor(low_edge * 20) / 20)
    high = min(1.0, np.ceil(high_edge * 20) / 20)
    if high - low < 0.20:
        midpoint = (high + low) / 2
        low = max(0.0, midpoint - 0.10)
        high = min(1.0, midpoint + 0.10)
    return float(low), float(high)


def draw_baseline_reference(axis: plt.Axes, baseline: pd.Series) -> None:
    axis.axvspan(
        baseline["critical_alpha_ci95_low"],
        baseline["critical_alpha_ci95_high"],
        color="#BDBDBD",
        alpha=0.24,
        linewidth=0,
        zorder=0,
    )
    axis.axvline(
        baseline["critical_alpha"],
        color=BASELINE_COLOR,
        linewidth=0.8,
        linestyle=(0, (3, 2)),
        zorder=1,
    )


def forest_panel(
    axis: plt.Axes,
    critical: pd.DataFrame,
    rows: tuple[tuple, ...],
    baseline: pd.Series,
    parameter_panel: bool,
) -> None:
    by_id = critical.set_index("scenario_id")
    draw_baseline_reference(axis, baseline)
    y_positions = np.arange(len(rows))[::-1]
    for y, item in zip(y_positions, rows):
        scenario_id, label = item[:2]
        row = by_id.loc[scenario_id]
        if pd.isna(row["critical_alpha"]):
            axis.text(
                0.01,
                y,
                "Not identified",
                transform=axis.get_yaxis_transform(),
                va="center",
                ha="left",
                fontsize=5.8,
                color="#666666",
            )
            continue
        if parameter_panel:
            color = LOW_COLOR if item[2] == "lower" else HIGH_COLOR
            marker = "o" if item[2] == "lower" else "s"
        else:
            color = BASELINE_COLOR if scenario_id == "baseline" else "#6A3D9A"
            marker = "D" if scenario_id == "baseline" else "o"
        x = float(row["critical_alpha"])
        xerr = np.array(
            [[x - row["critical_alpha_ci95_low"]], [row["critical_alpha_ci95_high"] - x]]
        )
        axis.errorbar(
            x,
            y,
            xerr=xerr,
            fmt=marker,
            color=color,
            markerfacecolor=color,
            markeredgewidth=0,
            markersize=3.8,
            capsize=2.2,
            elinewidth=0.9,
            zorder=3,
        )
    axis.set_yticks(y_positions, [item[1] for item in rows])
    # Use one shared x scale for both forest panels so critical-point shifts
    # are visually comparable and unused horizontal space is minimized.
    limits = critical_axis_limits(critical, critical["scenario_id"].tolist())
    axis.set_xlim(*limits)
    axis.set_xticks(np.arange(np.ceil(limits[0] * 10) / 10, limits[1] + 0.001, 0.1))
    axis.set_xlabel("Detected critical α (seed-block bootstrap 95% CI)")
    axis.set_ylim(-0.8, len(rows) - 0.2)


def curve_panel(axis: plt.Axes, curves: pd.DataFrame) -> None:
    subset = curves[curves["metric"] == "mean_agenda_divergence"]
    for scenario_id, label, color, linestyle in CURVE_ROWS:
        group = subset[subset["scenario_id"] == scenario_id].sort_values("alpha")
        x = group["alpha"].to_numpy(float)
        mean = group["mean"].to_numpy(float)
        low = group["ci95_low"].to_numpy(float)
        high = group["ci95_high"].to_numpy(float)
        axis.fill_between(x, low, high, color=color, alpha=0.10, linewidth=0)
        axis.plot(x, mean, color=color, linewidth=1.15, linestyle=linestyle, label=label)
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.set_xticks(np.arange(0, 1.01, 0.2))
    axis.set_yticks(np.arange(0, 1.01, 0.2))
    axis.set_xlabel("Recommendation heat weight α")
    axis.set_ylabel("Mean agenda divergence")
    axis.legend(frameon=False, loc="upper left", ncol=1, handlelength=2.4)


def build_figure(critical: pd.DataFrame, curves: pd.DataFrame) -> plt.Figure:
    configure_style()
    figure = plt.figure(
        figsize=(WIDTH_MM / MM_PER_INCH, HEIGHT_MM / MM_PER_INCH)
    )
    grid = figure.add_gridspec(
        2,
        2,
        height_ratios=[1.55, 1.0],
        width_ratios=[1.06, 0.94],
        hspace=0.40,
        wspace=0.46,
    )
    axis_a = figure.add_subplot(grid[0, :])
    axis_b = figure.add_subplot(grid[1, 0])
    axis_c = figure.add_subplot(grid[1, 1])
    baseline = critical.set_index("scenario_id").loc["baseline"]
    forest_panel(axis_a, critical, PARAMETER_ROWS, baseline, parameter_panel=True)
    forest_panel(axis_b, critical, STRUCTURE_ROWS, baseline, parameter_panel=False)
    curve_panel(axis_c, curves)

    for label, axis, x_position in (("a", axis_a, -0.19), ("b", axis_b, -0.35), ("c", axis_c, -0.23)):
        axis.text(
            x_position,
            1.03,
            label,
            transform=axis.transAxes,
            fontsize=8.0,
            fontweight="bold",
            va="bottom",
            ha="left",
        )
    figure.subplots_adjust(left=0.235, right=0.985, bottom=0.085, top=0.975)
    return figure


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    critical = pd.read_csv(args.processed_dir / "sensitivity_critical_points.csv")
    curves = pd.read_csv(args.processed_dir / "sensitivity_curve_summary.csv")
    validate_inputs(critical, curves)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    SOURCE_OUT.mkdir(parents=True, exist_ok=True)
    critical_ids = [row[0] for row in PARAMETER_ROWS + STRUCTURE_ROWS]
    critical[critical["scenario_id"].isin(critical_ids)].to_csv(
        SOURCE_OUT / "FigS2_critical_points_source_data.csv",
        index=False,
        encoding="utf-8-sig",
    )
    curves[
        curves["scenario_id"].isin([row[0] for row in CURVE_ROWS])
        & (curves["metric"] == "mean_agenda_divergence")
    ].to_csv(
        SOURCE_OUT / "FigS2_response_curves_source_data.csv",
        index=False,
        encoding="utf-8-sig",
    )

    figure = build_figure(critical, curves)
    stem = args.output_dir / "FigS2_formal_sensitivity"
    figure.savefig(stem.with_suffix(".svg"), bbox_inches="tight")
    figure.savefig(stem.with_suffix(".pdf"), bbox_inches="tight")
    figure.savefig(stem.with_suffix(".png"), dpi=600, bbox_inches="tight")
    tiff_path = stem.with_suffix(".tiff")
    figure.savefig(
        tiff_path,
        dpi=600,
        bbox_inches="tight",
        pil_kwargs={"compression": "tiff_lzw"},
    )
    plt.close(figure)
    with Image.open(tiff_path) as tiff_image:
        rgb_image = tiff_image.convert("RGB")
        rgb_image.save(tiff_path, dpi=(600, 600), compression="tiff_lzw")
    print(f"Wrote {stem}.{{svg,pdf,png,tiff}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
