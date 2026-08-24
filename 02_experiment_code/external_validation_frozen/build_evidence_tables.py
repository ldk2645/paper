from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "processed"
EXT = ROOT / "external" / "processed"


def main():
    rows = []
    paired = pd.read_csv(PROC / "paired_effects_5conditions.csv")
    paired.loc[paired["is_primary_alpha"].astype(bool)].to_csv(
        PROC / "ablation_primary_alpha.csv", index=False, encoding="utf-8-sig"
    )
    (
        paired.loc[paired["metric"].eq("mean_agenda_divergence")]
        .pivot(index="alpha", columns="condition_id", values="mean_difference")
        .reset_index()
        .to_csv(PROC / "fig4_agenda_effect_chart_data.csv", index=False, encoding="utf-8-sig")
    )
    for r in paired.loc[paired["is_primary_alpha"].astype(bool)].itertuples(index=False):
        rows.append(
            {
                "evidence_family": "formal_ablation_primary_alpha",
                "comparison": f"{r.condition_id} minus full",
                "metric": r.metric,
                "estimate": r.mean_difference,
                "ci_low": r.bootstrap_ci_low,
                "ci_high": r.bootstrap_ci_high,
                "p_value": r.holm_signflip_p_primary_global,
                "p_definition": "paired sign-flip, Holm over 16 primary comparisons",
                "n": r.n_pairs,
                "unit": "paired common-random-seed runs",
                "direction": r.difference_direction,
            }
        )
    auc = pd.read_csv(PROC / "auc_effects_5conditions.csv")
    for r in auc.itertuples(index=False):
        rows.append(
            {
                "evidence_family": "formal_ablation_auc_0_1",
                "comparison": f"{r.condition_id} minus full",
                "metric": r.metric,
                "estimate": r.mean_difference,
                "ci_low": r.bootstrap_ci_low,
                "ci_high": r.bootstrap_ci_high,
                "p_value": r.holm_signflip_p_global,
                "p_definition": "paired sign-flip, Holm over 16 AUC comparisons",
                "n": r.n_pairs,
                "unit": "paired seed-level AUC curves",
                "direction": r.difference_direction,
            }
        )
    macro = pd.read_csv(EXT / "macro_spearman.csv")
    for r in macro.itertuples(index=False):
        rows.append(
            {
                "evidence_family": "external_macro_consistency",
                "comparison": f"GTMI edition {r.gtmi_year} vs OECD trust 2023",
                "metric": r.predictor,
                "estimate": r.spearman_rho,
                "ci_low": r.ci_low,
                "ci_high": r.ci_high,
                "p_value": r.p_holm_15,
                "p_definition": "Spearman test, Holm over 15 index-edition comparisons",
                "n": r.n,
                "unit": "countries",
                "direction": "rank correlation",
            }
        )
    ext = json.loads((EXT / "external_validation_results.json").read_text(encoding="utf-8"))
    s = ext["sentiment_validation"]
    for key, label in [("clustered_regression_emotion", "emotional intensity, 1 SD"), ("clustered_regression_negative", "negative vs non-negative headline")]:
        r = s[key]
        rows.append(
            {
                "evidence_family": "external_news_consistency",
                "comparison": label,
                "metric": "log1p platform feedback",
                "estimate": r["estimate"],
                "ci_low": r["ci_low"],
                "ci_high": r["ci_high"],
                "p_value": r["p_value"],
                "p_definition": "cluster-robust OLS, clustered by news item",
                "n": r["n"],
                "unit": "valid item-platform observations",
                "direction": "conditional log-scale coefficient",
            }
        )
    raw = s["spearman_emotion_popularity"]
    rows.append(
        {
            "evidence_family": "external_news_consistency",
            "comparison": "absolute headline sentiment vs platform feedback",
            "metric": "Spearman rho",
            "estimate": raw["rho"],
            "ci_low": raw["ci_low"],
            "ci_high": raw["ci_high"],
            "p_value": raw["p_value"],
            "p_definition": "unadjusted rank correlation; Fisher-z 95% CI",
            "n": s["valid_platform_rows"],
            "unit": "valid item-platform observations",
            "direction": "rank correlation",
        }
    )
    d = ext["decay_validation"]
    for metric, value, ci in [
        ("share_first_6h", d["mean_share_first_6h"], d["share_first_6h_ci"]),
        ("share_first_12h", d["mean_share_first_12h"], d["share_first_12h_ci"]),
    ]:
        rows.append(
            {
                "evidence_family": "external_attention_decay",
                "comparison": "Facebook Obama + Palestine articles",
                "metric": metric,
                "estimate": value,
                "ci_low": ci[0],
                "ci_high": ci[1],
                "p_value": None,
                "p_definition": "t interval across articles; no null test",
                "n": d["articles_analyzed"],
                "unit": "articles with at least 24 h valid feedback",
                "direction": "share of 24-hour feedback",
            }
        )
    pd.DataFrame(rows).to_csv(PROC / "final_conclusion_data.csv", index=False, encoding="utf-8-sig")

    sources = pd.DataFrame(
        [
            {
                "source": "World Bank GovTech Maturity Index 2025 workbook",
                "url": "https://datacatalog.worldbank.org/search/dataset/0037889/govtech-dataset",
                "license": "CC BY 4.0",
                "downloaded_file": "external/raw/world_bank_gtmi_2025.xlsx",
                "used_data": "2020, 2022 and 2025 GTMI, CGSI, PSDI, DCEI, GTEI for 30 OECD-trust countries",
                "role": "external macro consistency check",
            },
            {
                "source": "OECD Trust, security and dignity, Government at a Glance 2025",
                "url": "https://data-explorer.oecd.org/vis?df%5Bag%5D=OECD.GOV.GIP&df%5Bds%5D=DisseminateFinalDMZ&df%5Bid%5D=DSD_GOV_INT%40DF_GOV_TDG_2025&df%5Bvs%5D=1.1&lc=en",
                "license": "OECD terms and conditions",
                "downloaded_file": "external/raw/oecd_trust_security_dignity_2025.csv",
                "used_data": "2023 TRUST_NG, HMH scale: percentage with high or moderately high trust in national government",
                "role": "external trust outcome",
            },
            {
                "source": "World Bank World Development Indicators API",
                "url": "https://datahelpdesk.worldbank.org/knowledgebase/articles/898599-indicator-api-queries",
                "license": "World Bank Data Terms",
                "downloaded_file": "external/raw/world_bank_internet_2022_2025.json; world_bank_gdp_ppp_per_capita_2022_2025.json",
                "used_data": "latest non-missing value through 2023: IT.NET.USER.ZS and NY.GDP.PCAP.PP.KD",
                "role": "macro regression controls",
            },
            {
                "source": "UCI News Popularity in Multiple Social Media Platforms (dataset 432)",
                "url": "https://doi.org/10.24432/C5H029",
                "license": "CC BY 4.0",
                "downloaded_file": "external/raw/uci_news_social_popularity_432.zip",
                "used_data": "93,239 news items; 256,626 valid item-platform observations; Facebook Obama/Palestine time series for 27,244 eligible articles",
                "role": "emotion-popularity and attention-decay checks",
            },
        ]
    )
    sources.to_csv(PROC / "dataset_sources.csv", index=False, encoding="utf-8-sig")
    print({"conclusion_rows": len(rows), "source_rows": len(sources)})


if __name__ == "__main__":
    main()
