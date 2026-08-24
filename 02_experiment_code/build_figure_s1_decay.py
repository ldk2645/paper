"""Build Supplementary Fig. S1: empirical 24-hour attention decay.

Figure contract
---------------
Claim: public-affairs attention combines a very large initial burst with a
heavier 6--24 h tail than an illustrative per-20-min geometric decay with
retention lambda=0.95.
Evidence: panel a shows interval shares and their article-level uncertainty;
panel b shows cumulative shares and the independently calculated 6 h/12 h
confidence intervals.
Replicate unit: 27,244 Facebook public-affairs articles with complete 24 h
coverage.  The geometric curve is a deterministic comparator, not a fitted
model and not a calibration of one simulation step to 20 minutes.
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
DEFAULT_INPUT = (
    PACKAGE
    / "03_data"
    / "external"
    / "processed"
    / "facebook_public_affairs_decay_curve.csv"
)
DEFAULT_OUT = PACKAGE / "04_figures" / "supplementary"
SOURCE_OUT = PACKAGE / "03_data" / "external" / "source_data"

WIDTH_MM = 183.0
HEIGHT_MM = 78.0
MM_PER_INCH = 25.4
EMPIRICAL = "#0072B2"
COMPARATOR = "#D55E00"
N_ARTICLES = 27_244


def configure_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 7.0,
            "axes.labelsize": 7.0,
            "axes.titlesize": 7.0,
            "xtick.labelsize": 6.5,
            "ytick.labelsize": 6.5,
            "legend.fontsize": 6.5,
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


def prepare_source(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {
        "bin",
        "hours_since_first_observed",
        "mean_share_of_24h_feedback",
        "ci_low",
        "ci_high",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Decay input is missing columns: {sorted(missing)}")
    frame = frame.sort_values("bin").reset_index(drop=True).copy()
    if len(frame) != 72 or frame["bin"].tolist() != list(range(1, 73)):
        raise ValueError("Expected exactly 72 consecutive 20-minute bins")
    if not np.isclose(frame["mean_share_of_24h_feedback"].sum(), 1.0, atol=1e-9):
        raise ValueError("Empirical interval shares do not sum to one")
    if not (
        (frame["ci_low"] > 0)
        & (frame["ci_low"] <= frame["mean_share_of_24h_feedback"])
        & (frame["mean_share_of_24h_feedback"] <= frame["ci_high"])
    ).all():
        raise ValueError("Invalid empirical confidence interval")

    geometric = 0.05 * np.power(0.95, np.arange(len(frame), dtype=float))
    geometric /= geometric.sum()
    frame["empirical_cumulative_share"] = frame[
        "mean_share_of_24h_feedback"
    ].cumsum()
    frame["lambda_095_share_normalized_to_24h"] = geometric
    frame["lambda_095_cumulative_share"] = np.cumsum(geometric)
    frame["n_articles"] = N_ARTICLES

    landmark_rows = []
    empirical_intervals = {
        6: (0.6091167963592367, 0.6056264081099337, 0.6126071846085396),
        12: (0.7773948493037308, 0.7746514445838925, 0.7801382540235692),
    }
    for hour, (estimate, low, high) in empirical_intervals.items():
        index = hour * 3 - 1
        calculated = float(frame.loc[index, "empirical_cumulative_share"])
        if not np.isclose(calculated, estimate, atol=1e-10):
            raise ValueError(f"Cumulative share does not reconcile at {hour} h")
        landmark_rows.append(
            {
                "hour": hour,
                "empirical_cumulative_share": estimate,
                "empirical_ci95_low": low,
                "empirical_ci95_high": high,
                "lambda_095_cumulative_share": float(
                    frame.loc[index, "lambda_095_cumulative_share"]
                ),
                "n_articles": N_ARTICLES,
                "empirical_interval_method": "two-sided 95% t interval across articles",
                "comparator_note": "deterministic lambda=0.95 geometric weights normalized across the same 72 bins",
            }
        )
    return frame, pd.DataFrame(landmark_rows)


def build_figure(source: pd.DataFrame, landmarks: pd.DataFrame) -> plt.Figure:
    configure_style()
    figure, axes = plt.subplots(
        1,
        2,
        figsize=(WIDTH_MM / MM_PER_INCH, HEIGHT_MM / MM_PER_INCH),
        gridspec_kw={"wspace": 0.32},
    )
    x = source["hours_since_first_observed"].to_numpy(float)
    empirical = source["mean_share_of_24h_feedback"].to_numpy(float)
    low = source["ci_low"].to_numpy(float)
    high = source["ci_high"].to_numpy(float)
    comparator = source["lambda_095_share_normalized_to_24h"].to_numpy(float)

    if np.any(empirical <= 0) or np.any(low <= 0) or np.any(comparator <= 0):
        raise ValueError("Log-scale series must be strictly positive")
    axes[0].fill_between(x, low, high, color=EMPIRICAL, alpha=0.18, linewidth=0)
    axes[0].plot(x, empirical, color=EMPIRICAL, linewidth=1.25, label="Empirical")
    axes[0].plot(
        x,
        comparator,
        color=COMPARATOR,
        linewidth=1.0,
        linestyle=(0, (4, 2)),
        label="Geometric λ = 0.95",
    )
    axes[0].set_yscale("log")
    axes[0].set_xlim(0, 24)
    axes[0].set_ylim(0.001, 0.5)
    axes[0].set_xticks([0, 6, 12, 18, 24])
    axes[0].set_yticks([0.001, 0.01, 0.1, 0.5])
    axes[0].set_yticklabels(["0.1%", "1%", "10%", "50%"])
    axes[0].set_xlabel("Hours since first observation")
    axes[0].set_ylabel("Share per 20-min bin (log scale)")
    axes[0].legend(frameon=False, loc="upper right", handlelength=2.2)

    empirical_cumulative = source["empirical_cumulative_share"].to_numpy(float)
    comparator_cumulative = source["lambda_095_cumulative_share"].to_numpy(float)
    axes[1].plot(x, empirical_cumulative, color=EMPIRICAL, linewidth=1.35)
    axes[1].plot(
        x,
        comparator_cumulative,
        color=COMPARATOR,
        linewidth=1.0,
        linestyle=(0, (4, 2)),
    )
    axes[1].axhline(1.0, color="#777777", linewidth=0.5, linestyle=(0, (2, 2)))
    for row in landmarks.itertuples(index=False):
        error = np.array(
            [
                [row.empirical_cumulative_share - row.empirical_ci95_low],
                [row.empirical_ci95_high - row.empirical_cumulative_share],
            ]
        )
        axes[1].errorbar(
            row.hour,
            row.empirical_cumulative_share,
            yerr=error,
            fmt="o",
            color=EMPIRICAL,
            markersize=3.2,
            capsize=2,
            elinewidth=0.8,
            zorder=4,
        )
        axes[1].plot(
            row.hour,
            row.lambda_095_cumulative_share,
            marker="s",
            color=COMPARATOR,
            markersize=2.8,
            zorder=4,
        )
        text_x, text_y = (
            (6.7, 0.54) if row.hour == 6 else (12.7, 0.68)
        )
        axes[1].text(
            text_x,
            text_y,
            f"{row.hour} h: {row.empirical_cumulative_share:.1%} vs "
            f"{row.lambda_095_cumulative_share:.1%}",
            ha="left",
            va="center",
            fontsize=6.0,
            color="#222222",
        )
    axes[1].set_xlim(0, 24)
    axes[1].set_ylim(0, 1.03)
    axes[1].set_xticks([0, 6, 12, 18, 24])
    axes[1].set_yticks(np.arange(0, 1.01, 0.2))
    axes[1].set_yticklabels([f"{value:.0%}" for value in np.arange(0, 1.01, 0.2)])
    axes[1].set_xlabel("Hours since first observation")
    axes[1].set_ylabel("Cumulative share of 24-h feedback")

    for label, axis in zip(("a", "b"), axes):
        axis.text(
            -0.16,
            1.04,
            label,
            transform=axis.transAxes,
            fontsize=8.0,
            fontweight="bold",
            va="bottom",
            ha="left",
        )
    figure.subplots_adjust(left=0.085, right=0.985, bottom=0.19, top=0.93)
    return figure


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    source, landmarks = prepare_source(pd.read_csv(args.input))
    SOURCE_OUT.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    source.to_csv(
        SOURCE_OUT / "FigS1_attention_decay_source_data.csv",
        index=False,
        encoding="utf-8-sig",
    )
    landmarks.to_csv(
        SOURCE_OUT / "FigS1_attention_decay_landmarks.csv",
        index=False,
        encoding="utf-8-sig",
    )

    figure = build_figure(source, landmarks)
    stem = args.output_dir / "FigS1_attention_decay"
    figure.savefig(stem.with_suffix(".svg"), bbox_inches="tight")
    figure.savefig(stem.with_suffix(".pdf"), bbox_inches="tight")
    figure.savefig(stem.with_suffix(".png"), dpi=600, bbox_inches="tight")
    tiff_path = stem.with_suffix(".tiff")
    figure.savefig(
        tiff_path, dpi=600, bbox_inches="tight", pil_kwargs={"compression": "tiff_lzw"}
    )
    plt.close(figure)
    with Image.open(tiff_path) as tiff_image:
        rgb_image = tiff_image.convert("RGB")
        rgb_image.save(tiff_path, dpi=(600, 600), compression="tiff_lzw")
    print(f"Wrote {stem}.{{svg,pdf,png,tiff}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
