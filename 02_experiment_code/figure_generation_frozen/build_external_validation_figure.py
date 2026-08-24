from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "external" / "processed"
OUT = ROOT / "figures"
OUT.mkdir(parents=True, exist_ok=True)

MM = 1 / 25.4
width_mm = 183
WIDTH = width_mm * MM
COLORS = {2020: "#D55E00", 2022: "#0072B2", 2025: "#8E44AD"}
INK = "#20252B"
GRAY = "#69737D"
TEAL = "#009E73"

mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "font.size": 7,
        "axes.labelsize": 7,
        "xtick.labelsize": 6,
        "ytick.labelsize": 6,
        "legend.fontsize": 6,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.linewidth": 0.65,
        "xtick.major.width": 0.55,
        "ytick.major.width": 0.55,
        "xtick.major.size": 2.5,
        "ytick.major.size": 2.5,
        "legend.frameon": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
    }
)


def panel_label(ax, label):
    ax.text(-0.17, 1.07, label, transform=ax.transAxes, fontsize=8, fontweight="bold", va="top", ha="left")


def style(ax):
    ax.tick_params(direction="out", pad=2)
    ax.spines["left"].set_color(INK)
    ax.spines["bottom"].set_color(INK)


def main():
    countries = pd.read_csv(DATA / "macro_country_panel.csv")
    corr = pd.read_csv(DATA / "macro_spearman.csv")
    reg = pd.read_csv(DATA / "news_sentiment_regression_cluster.csv")
    decay = pd.read_csv(DATA / "facebook_public_affairs_decay_curve.csv")

    fig, axes = plt.subplots(2, 2, figsize=(WIDTH, 124 * MM))

    # a, temporally aligned macro comparison
    ax = axes[0, 0]
    d = countries.loc[countries["Year"].eq(2022)].sort_values("GTMI")
    ax.scatter(d["GTMI"], d["trust_national_pct"], s=15, color=COLORS[2022], alpha=0.82, edgecolors="white", linewidths=0.35)
    fit = np.polyfit(d["GTMI"], d["trust_national_pct"], 1)
    xx = np.linspace(d["GTMI"].min(), d["GTMI"].max(), 100)
    ax.plot(xx, np.polyval(fit, xx), color=COLORS[2022], lw=1.1)
    row = corr.loc[corr["gtmi_year"].eq(2022) & corr["predictor"].eq("GTMI")].iloc[0]
    ax.text(0.03, 0.96, f"Spearman ρ = {row.spearman_rho:.2f}\nP = {row.p_value:.2f}; n = {int(row.n)} countries", transform=ax.transAxes, va="top", ha="left", color=INK)
    ax.set_xlabel("GovTech Maturity Index, 2022")
    ax.set_ylabel("Trust in national government, 2023 (%)")
    panel_label(ax, "a")
    style(ax)

    # b, edition sensitivity for cross-country correlations
    ax = axes[0, 1]
    predictors = ["GTMI", "CGSI", "PSDI", "DCEI", "GTEI"]
    display = {"GTMI": "Overall GTMI", "CGSI": "Core systems", "PSDI": "Public services", "DCEI": "Citizen engagement", "GTEI": "Enablers"}
    ybase = np.arange(len(predictors))[::-1]
    offsets = {2020: 0.20, 2022: 0.0, 2025: -0.20}
    for year in [2020, 2022, 2025]:
        q = corr.loc[corr["gtmi_year"].eq(year)].set_index("predictor").loc[predictors]
        y = ybase + offsets[year]
        x = q["spearman_rho"].to_numpy()
        lo = q["ci_low"].to_numpy()
        hi = q["ci_high"].to_numpy()
        ax.errorbar(x, y, xerr=np.vstack([x - lo, hi - x]), fmt="o", ms=3.2, lw=0.85, capsize=1.5, color=COLORS[year], label=str(year))
    ax.axvline(0, color="#8C8C8C", lw=0.65)
    ax.set_yticks(ybase, [display[x] for x in predictors])
    ax.set_xlim(-0.65, 0.75)
    ax.set_xlabel("Spearman ρ with 2023 government trust (95% CI)")
    ax.legend(ncol=3, loc="lower center", bbox_to_anchor=(0.5, 1.015), handlelength=1.2, columnspacing=0.9)
    panel_label(ax, "b")
    style(ax)

    # c, adjusted emotionality coefficients
    ax = axes[1, 0]
    terms = ["z_emotion_intensity", "negative"]
    labels = ["Emotional intensity\n(per 1 SD)", "Negative headline\n(vs non-negative)"]
    q = reg.set_index("term").loc[terms]
    estimates = 100 * (np.exp(q["estimate"].to_numpy()) - 1)
    lows = 100 * (np.exp(q["ci_low"].to_numpy()) - 1)
    highs = 100 * (np.exp(q["ci_high"].to_numpy()) - 1)
    ypos = np.array([1, 0])
    ax.errorbar(estimates, ypos, xerr=np.vstack([estimates - lows, highs - estimates]), fmt="o", color=COLORS[2022], ms=4, lw=1.1, capsize=2)
    ax.axvline(0, color="#8C8C8C", lw=0.65)
    ax.set_yticks(ypos, labels)
    ax.set_ylim(-0.65, 1.65)
    ax.set_xlabel("Conditional change in 1 + feedback (%)")
    ax.text(0.03, 0.05, "Cluster-robust OLS; n = 256,626 platform observations\nControls: topic, platform, month and headline length", transform=ax.transAxes, va="bottom", ha="left", color=GRAY, fontsize=5.5)
    ax.text(0.97, 0.95, "Raw rank correlation: ρ = −0.003\n95% CI [−0.007, 0.001]", transform=ax.transAxes, va="top", ha="right", color=GRAY, fontsize=5.5)
    panel_label(ax, "c")
    style(ax)

    # d, aligned public-affairs attention decay
    ax = axes[1, 1]
    x = decay["hours_since_first_observed"].to_numpy()
    mean = 100 * decay["mean_share_of_24h_feedback"].to_numpy()
    lo = 100 * decay["ci_low"].to_numpy()
    hi = 100 * decay["ci_high"].to_numpy()
    ax.fill_between(x, lo, hi, color=TEAL, alpha=0.16, lw=0)
    ax.plot(x, mean, color=TEAL, lw=1.25)
    ax.axvline(6, color=GRAY, lw=0.6, ls=(0, (2, 2)))
    ax.axvline(12, color=GRAY, lw=0.6, ls=(0, (2, 2)))
    ax.text(6.15, ax.get_ylim()[1] * 0.74, "60.9% by 6 h", color=GRAY, fontsize=5.5)
    ax.text(12.15, ax.get_ylim()[1] * 0.56, "77.7% by 12 h", color=GRAY, fontsize=5.5)
    ax.set_xlim(0, 24)
    ax.set_xlabel("Hours since first observed interval")
    ax.set_ylabel("Mean share of 24-h feedback per interval (%)")
    ax.text(0.98, 0.96, "n = 27,244 public-affairs articles\nMean ± 95% CI across articles", transform=ax.transAxes, ha="right", va="top", color=INK, fontsize=5.5)
    panel_label(ax, "d")
    style(ax)

    fig.subplots_adjust(left=0.105, right=0.985, bottom=0.115, top=0.965, wspace=0.37, hspace=0.38)
    fig.savefig(OUT / "Fig6_public_data_validation.svg")
    fig.savefig(OUT / "Fig6_public_data_validation.pdf")
    fig.savefig(OUT / "Fig6_public_data_validation.png", dpi=600)
    fig.savefig(
        OUT / "Fig6_public_data_validation.tiff",
        dpi=600,
        pil_kwargs={"compression": "tiff_lzw"},
    )
    plt.close(fig)
    print({"status": "ok", "figure": str(OUT / "Fig6_public_data_validation.pdf")})


if __name__ == "__main__":
    main()
