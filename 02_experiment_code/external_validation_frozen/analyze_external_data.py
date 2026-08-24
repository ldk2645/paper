from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "external" / "raw"
OUT = ROOT / "external" / "processed"
OUT.mkdir(parents=True, exist_ok=True)
RNG = np.random.default_rng(20260811)


def zscore(x: pd.Series) -> np.ndarray:
    a = x.to_numpy(dtype=float)
    return (a - a.mean()) / a.std(ddof=0)


def ols_robust(y: np.ndarray, X: np.ndarray, names: list[str], clusters=None) -> pd.DataFrame:
    """OLS with HC3 or one-way cluster-robust covariance."""
    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    n, p = X.shape
    xtxi = np.linalg.pinv(X.T @ X)
    beta = xtxi @ X.T @ y
    resid = y - X @ beta
    if clusters is None:
        h = np.einsum("ij,jk,ik->i", X, xtxi, X)
        adj = resid / np.clip(1.0 - h, 1e-10, None)
        meat = X.T @ ((adj**2)[:, None] * X)
        cov = xtxi @ meat @ xtxi
        df = max(n - p, 1)
        method = "HC3"
    else:
        frame = pd.DataFrame(X * resid[:, None])
        frame["cluster"] = np.asarray(clusters)
        scores = frame.groupby("cluster", sort=False).sum().drop(columns=[]).to_numpy()
        g = scores.shape[0]
        meat = scores.T @ scores
        correction = (g / max(g - 1, 1)) * ((n - 1) / max(n - p, 1))
        cov = correction * (xtxi @ meat @ xtxi)
        df = max(g - 1, 1)
        method = "cluster(IDLink)"
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    tval = beta / se
    pval = 2 * stats.t.sf(np.abs(tval), df=df)
    crit = stats.t.ppf(0.975, df=df)
    return pd.DataFrame(
        {
            "term": names,
            "estimate": beta,
            "std_error": se,
            "t": tval,
            "df": df,
            "p_value": pval,
            "ci_low": beta - crit * se,
            "ci_high": beta + crit * se,
            "covariance": method,
            "n": n,
        }
    )


def bootstrap_spearman(x: np.ndarray, y: np.ndarray, n_boot: int = 5000):
    rho, p = stats.spearmanr(x, y)
    if len(x) > 10000:
        # At very large n, a row bootstrap is needlessly expensive and its interval
        # is numerically indistinguishable from the standard Fisher-z interval.
        z = np.arctanh(np.clip(rho, -0.999999, 0.999999))
        delta = 1.96 / math.sqrt(len(x) - 3)
        return float(rho), float(p), np.tanh([z - delta, z + delta]).tolist(), 0
    vals = np.empty(n_boot)
    n = len(x)
    for i in range(n_boot):
        idx = RNG.integers(0, n, n)
        vals[i] = stats.spearmanr(x[idx], y[idx]).statistic
    return float(rho), float(p), np.nanquantile(vals, [0.025, 0.975]).tolist(), n_boot


def latest_wdi(filename: str, value_name: str) -> pd.DataFrame:
    payload = json.loads((RAW / filename).read_text(encoding="utf-8"))
    rows = pd.DataFrame(payload[1])
    rows = rows.loc[rows["value"].notna() & rows["countryiso3code"].str.len().eq(3)].copy()
    rows["year"] = rows["date"].astype(int)
    rows = rows.loc[rows["year"].le(2023)].copy()
    rows = rows.sort_values(["countryiso3code", "year"], ascending=[True, False])
    rows = rows.drop_duplicates("countryiso3code")
    return rows[["countryiso3code", "year", "value"]].rename(
        columns={"countryiso3code": "Code", "year": f"{value_name}_year", "value": value_name}
    )


def macro_validation() -> dict:
    gtmi = pd.read_excel(
        RAW / "world_bank_gtmi_2025.xlsx",
        sheet_name="GTMI_Data",
        usecols=["Year", "Code", "Economy", "GTMI", "CGSI", "PSDI", "DCEI", "GTEI"],
    )
    gtmi["Year"] = pd.to_numeric(gtmi["Year"], errors="coerce")
    gtmi = gtmi.loc[gtmi["Year"].isin([2020, 2022, 2025])].copy()
    gtmi["Code"] = gtmi["Code"].astype(str).str.strip()
    for col in ["GTMI", "CGSI", "PSDI", "DCEI", "GTEI"]:
        gtmi[col] = pd.to_numeric(gtmi[col], errors="coerce")

    oecd = pd.read_csv(RAW / "oecd_trust_security_dignity_2025.csv")
    trust = oecd.loc[
        oecd["MEASURE"].eq("TRUST_NG")
        & oecd["SCALE"].eq("HMH")
        & oecd["TIME_PERIOD"].eq(2023)
        & oecd["REF_AREA"].str.len().eq(3),
        ["REF_AREA", "Reference area", "TIME_PERIOD", "OBS_VALUE"],
    ].rename(
        columns={
            "REF_AREA": "Code",
            "Reference area": "OECD_country",
            "TIME_PERIOD": "trust_year",
            "OBS_VALUE": "trust_national_pct",
        }
    )
    internet = latest_wdi("world_bank_internet_2022_2025.json", "internet_pct")
    gdp = latest_wdi("world_bank_gdp_ppp_per_capita_2022_2025.json", "gdp_ppp_pc")
    joined = trust.merge(gtmi, on="Code", how="inner").merge(internet, on="Code", how="left").merge(gdp, on="Code", how="left")
    joined["log_gdp_ppp_pc"] = np.log(joined["gdp_ppp_pc"])
    joined = joined.sort_values("Code")
    joined.to_csv(OUT / "macro_country_panel.csv", index=False, encoding="utf-8-sig")

    correlations = []
    regressions = []
    loo_rows = []
    for gtmi_year in [2020, 2022, 2025]:
        year_data = joined.loc[joined["Year"].eq(gtmi_year)].copy()
        for predictor in ["GTMI", "DCEI", "PSDI", "GTEI", "CGSI"]:
            d = year_data.dropna(subset=[predictor, "trust_national_pct"]).copy()
            rho, p, ci, reps = bootstrap_spearman(d[predictor].to_numpy(), d["trust_national_pct"].to_numpy())
            correlations.append(
                {
                    "gtmi_year": gtmi_year,
                    "predictor": predictor,
                    "outcome": "trust_national_pct_2023",
                    "n": len(d),
                    "spearman_rho": rho,
                    "p_value": p,
                    "ci_low": ci[0],
                    "ci_high": ci[1],
                    "bootstrap_reps": reps,
                    "ci_method": "percentile bootstrap",
                }
            )
            loos = []
            for code in d["Code"]:
                q = d.loc[d["Code"].ne(code)]
                loos.append(stats.spearmanr(q[predictor], q["trust_national_pct"]).statistic)
            loo_rows.append(
                {
                    "gtmi_year": gtmi_year,
                    "predictor": predictor,
                    "n": len(d),
                    "loo_rho_min": float(np.min(loos)),
                    "loo_rho_max": float(np.max(loos)),
                }
            )

            d2 = year_data.dropna(subset=[predictor, "trust_national_pct", "internet_pct", "log_gdp_ppp_pc"]).copy()
            X = np.column_stack(
                [
                    np.ones(len(d2)),
                    zscore(d2[predictor]),
                    zscore(d2["internet_pct"]),
                    zscore(d2["log_gdp_ppp_pc"]),
                ]
            )
            res = ols_robust(
                d2["trust_national_pct"].to_numpy(),
                X,
                ["Intercept", f"z_{predictor}", "z_internet_pct", "z_log_gdp_ppp_pc"],
            )
            res.insert(0, "gtmi_year", gtmi_year)
            res.insert(1, "model_predictor", predictor)
            regressions.append(res)
    corr = pd.DataFrame(correlations)
    order = np.argsort(corr["p_value"].to_numpy())
    holm = np.empty(len(corr))
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (len(corr) - rank) * corr.loc[idx, "p_value"])
        holm[idx] = min(running, 1.0)
    corr["p_holm_15"] = holm
    reg = pd.concat(regressions, ignore_index=True)
    loo = pd.DataFrame(loo_rows)
    corr.to_csv(OUT / "macro_spearman.csv", index=False, encoding="utf-8-sig")
    reg.to_csv(OUT / "macro_regression_hc3.csv", index=False, encoding="utf-8-sig")
    loo.to_csv(OUT / "macro_leave_one_out.csv", index=False, encoding="utf-8-sig")
    return {
        "oecd_trust_rows_2023": int(len(trust)),
        "gtmi_rows_three_editions": int(len(gtmi)),
        "joined_country_year_rows": int(len(joined)),
        "countries_per_edition": int(joined["Code"].nunique()),
        "complete_control_rows_per_edition": int(joined.loc[joined.Year.eq(2022), ["GTMI", "trust_national_pct", "internet_pct", "log_gdp_ppp_pc"]].dropna().shape[0]),
        "correlations": corr.to_dict("records"),
        "temporally_aligned_adjusted_gtmi_2022": reg.loc[(reg.gtmi_year.eq(2022)) & (reg.model_predictor.eq("GTMI")) & reg.term.eq("z_GTMI")].iloc[0].to_dict(),
        "current_edition_adjusted_gtmi_2025": reg.loc[(reg.gtmi_year.eq(2025)) & (reg.model_predictor.eq("GTMI")) & reg.term.eq("z_GTMI")].iloc[0].to_dict(),
    }


def news_sentiment_validation() -> dict:
    news = pd.read_csv(RAW / "uci432" / "Data" / "News_Final.csv")
    before = len(news) * 3
    long = news.melt(
        id_vars=["IDLink", "Topic", "PublishDate", "SentimentHeadline", "Headline"],
        value_vars=["Facebook", "GooglePlus", "LinkedIn"],
        var_name="platform",
        value_name="popularity",
    )
    long = long.loc[long["popularity"].ge(0)].copy()
    long["log_popularity"] = np.log1p(long["popularity"])
    long["emotion_intensity"] = long["SentimentHeadline"].abs()
    long["negative"] = long["SentimentHeadline"].lt(0).astype(int)
    long["headline_chars_log"] = np.log1p(long["Headline"].fillna("").str.len())
    long["month"] = pd.to_datetime(long["PublishDate"], errors="coerce").dt.to_period("M").astype(str)
    long["emotion_quintile"] = pd.qcut(long["emotion_intensity"].rank(method="first"), 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"])

    predictors = pd.DataFrame(
        {
            "Intercept": 1.0,
            "z_emotion_intensity": zscore(long["emotion_intensity"]),
            "negative": long["negative"].to_numpy(),
            "z_headline_chars_log": zscore(long["headline_chars_log"]),
        }
    )
    for col in ["Topic", "platform", "month"]:
        dummies = pd.get_dummies(long[col], prefix=col, drop_first=True, dtype=float)
        predictors = pd.concat([predictors.reset_index(drop=True), dummies.reset_index(drop=True)], axis=1)
    res = ols_robust(
        long["log_popularity"].to_numpy(),
        predictors.to_numpy(),
        predictors.columns.tolist(),
        clusters=long["IDLink"].to_numpy(),
    )
    res.to_csv(OUT / "news_sentiment_regression_cluster.csv", index=False, encoding="utf-8-sig")

    rho, p, ci, reps = bootstrap_spearman(
        long["emotion_intensity"].to_numpy(), long["log_popularity"].to_numpy(), n_boot=1000
    )
    q = (
        long.groupby(["platform", "emotion_quintile"], observed=True)
        .agg(
            n=("log_popularity", "size"),
            mean_log_popularity=("log_popularity", "mean"),
            sd_log_popularity=("log_popularity", "std"),
            mean_emotion_intensity=("emotion_intensity", "mean"),
        )
        .reset_index()
    )
    q["se"] = q["sd_log_popularity"] / np.sqrt(q["n"])
    q["ci_low"] = q["mean_log_popularity"] - 1.96 * q["se"]
    q["ci_high"] = q["mean_log_popularity"] + 1.96 * q["se"]
    q.to_csv(OUT / "news_emotion_quintiles.csv", index=False, encoding="utf-8-sig")
    primary = res.loc[res.term.eq("z_emotion_intensity")].iloc[0]
    negative = res.loc[res.term.eq("negative")].iloc[0]
    return {
        "news_items": int(len(news)),
        "candidate_platform_rows": int(before),
        "valid_platform_rows": int(len(long)),
        "excluded_minus_one_rows": int(before - len(long)),
        "topics": news["Topic"].value_counts().to_dict(),
        "spearman_emotion_popularity": {"rho": rho, "p_value": p, "ci_low": ci[0], "ci_high": ci[1], "bootstrap_reps": reps, "ci_method": "Fisher-z approximation"},
        "clustered_regression_emotion": primary.to_dict(),
        "clustered_regression_negative": negative.to_dict(),
    }


def decay_validation() -> dict:
    aligned = []
    article_rows = []
    for topic in ["Obama", "Palestine"]:
        d = pd.read_csv(RAW / "uci432" / "Data" / f"Facebook_{topic}.csv")
        arr = d.filter(regex=r"^TS").to_numpy(dtype=float)
        valid_count = (arr >= 0).sum(axis=1)
        eligible = valid_count >= 72  # at least 24 hours of 20-minute bins
        for row_id, values in zip(d.loc[eligible, "IDLink"].to_numpy(), arr[eligible]):
            valid = values[values >= 0][:72]
            increments = np.diff(np.r_[0.0, valid])
            increments = np.clip(increments, 0, None)
            total = increments.sum()
            if total <= 0:
                continue
            norm = increments / total
            aligned.append(norm)
            article_rows.append(
                {
                    "IDLink": int(row_id),
                    "topic": topic.lower(),
                    "valid_bins": int((values >= 0).sum()),
                    "total_24h_feedback": float(total),
                    "share_first_6h": float(norm[:18].sum()),
                    "share_first_12h": float(norm[:36].sum()),
                }
            )
    matrix = np.vstack(aligned)
    article = pd.DataFrame(article_rows)
    article.to_csv(OUT / "facebook_public_affairs_article_decay.csv", index=False, encoding="utf-8-sig")
    mean_curve = matrix.mean(axis=0)
    curve_se = matrix.std(axis=0, ddof=1) / math.sqrt(len(matrix))
    curve = pd.DataFrame(
        {
            "bin": np.arange(1, 73),
            "hours_since_first_observed": np.arange(1, 73) / 3,
            "mean_share_of_24h_feedback": mean_curve,
            "ci_low": np.clip(mean_curve - 1.96 * curve_se, 0, None),
            "ci_high": mean_curve + 1.96 * curve_se,
        }
    )
    curve.to_csv(OUT / "facebook_public_affairs_decay_curve.csv", index=False, encoding="utf-8-sig")

    peak_idx = int(np.argmax(mean_curve))
    threshold = mean_curve[peak_idx] / 2
    later = np.where(mean_curve[peak_idx:] <= threshold)[0]
    half_life_bins = int(later[0]) if len(later) else None

    def boot_mean_ci(col: str):
        a = article[col].to_numpy()
        se = a.std(ddof=1) / math.sqrt(len(a))
        crit = stats.t.ppf(0.975, df=len(a) - 1)
        return float(a.mean()), [float(a.mean() - crit * se), float(a.mean() + crit * se)]

    share6, ci6 = boot_mean_ci("share_first_6h")
    share12, ci12 = boot_mean_ci("share_first_12h")
    return {
        "source_files": ["Facebook_Obama.csv", "Facebook_Palestine.csv"],
        "eligible_rule": "at least 72 valid 20-minute bins (24 hours), positive total feedback",
        "articles_analyzed": int(len(article)),
        "topic_counts": article["topic"].value_counts().to_dict(),
        "aggregate_peak_bin": peak_idx + 1,
        "aggregate_peak_hours": (peak_idx + 1) / 3,
        "half_peak_decay_bins_after_peak": half_life_bins,
        "half_peak_decay_hours_after_peak": None if half_life_bins is None else half_life_bins / 3,
        "mean_share_first_6h": share6,
        "share_first_6h_ci": ci6,
        "mean_share_first_12h": share12,
        "share_first_12h_ci": ci12,
        "curve_ci_method": "normal approximation across articles",
        "share_ci_method": "t interval across articles",
    }


def main():
    macro = macro_validation()
    sentiment = news_sentiment_validation()
    decay = decay_validation()
    results = {
        "analysis_date": "2026-08-11",
        "random_seed": 20260811,
        "macro_validation": macro,
        "sentiment_validation": sentiment,
        "decay_validation": decay,
        "interpretation_guardrail": "External-data results are observational consistency checks, not parameter calibration or causal identification.",
    }
    (OUT / "external_validation_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=lambda x: float(x) if isinstance(x, np.floating) else int(x)),
        encoding="utf-8",
    )
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
