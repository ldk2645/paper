"""Offline platform-attention versus institutional-demand index builder.

This module deliberately has no HTTP client and performs no collection.  It
accepts a provenance-labelled, PII-free standard CSV and compares three
optional information streams:

``weibo_hot``
    A platform attention ranking.  By default each observation is weighted by
    ``1 / log2(rank + 1)``.
``leader_board``
    Public, institutionalised demands.  Each row counts once unless ``count``
    supplies an aggregate frequency.
``government_daily``
    Government information publications.  This stream is optional and is used
    only for the government HotBias diagnostic.

The primary score uses base-2 Jensen-Shannon divergence::

    alignment = 100 * (1 - sqrt(JSD_2(H, D)))

The blind-spot score is 100 times total-variation distance::

    blind_spot = 50 * sum(abs(H - D))

Both scores are bounded by 0 and 100.  Identical distributions therefore have
alignment=100 and blind_spot=0, while mutually exclusive distributions have
alignment=0 and blind_spot=100.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd


SOURCE_WEIBO = "weibo_hot"
SOURCE_DEMAND = "leader_board"
SOURCE_GOVERNMENT = "government_daily"
ALLOWED_SOURCES = frozenset(
    {SOURCE_WEIBO, SOURCE_DEMAND, SOURCE_GOVERNMENT}
)
REQUIRED_COLUMNS = (
    "source",
    "observed_at",
    "region",
    "topic",
    "rank",
    "heat",
    "count",
    "record_id",
    "access_route",
    "license_note",
    "data_scope",
)
WEIBO_WEIGHT_MODES = frozenset({"rank", "heat", "count"})
DEFAULT_TIMEZONE = "Asia/Shanghai"

ROLLING_COLUMNS = (
    "data_scope",
    "region",
    "window_start",
    "window_end",
    "window_days",
    "source",
    "topic",
    "rolling_weight",
    "rolling_records",
    "share",
)
INDEX_COLUMNS = (
    "data_scope",
    "region",
    "window_start",
    "window_end",
    "window_days",
    "top_k",
    "topic_count",
    "jsd_hd",
    "alignment_hd",
    "blind_spot_tv",
    "coverage_at_k",
    "top_k_hot_topics",
    "alignment_gh",
    "alignment_gd",
    "hot_bias",
    "weibo_records",
    "leader_board_records",
    "government_records",
)
GAP_COLUMNS = (
    "data_scope",
    "region",
    "window_start",
    "window_end",
    "window_days",
    "topic",
    "weibo_share",
    "leader_board_share",
    "government_share",
    "gap_demand_minus_hot_pp",
)


@dataclass(frozen=True)
class IndexOutputs:
    """Tables and metadata returned by :func:`analyse_frame`."""

    rolling_distributions: pd.DataFrame
    index_timeseries: pd.DataFrame
    topic_gaps: pd.DataFrame
    metadata: dict[str, Any]


def _normalise_distribution(values: Sequence[float] | np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or array.size == 0:
        raise ValueError("a distribution must be a non-empty one-dimensional array")
    if not np.isfinite(array).all() or np.any(array < 0.0):
        raise ValueError("distribution values must be finite and non-negative")
    total = float(array.sum())
    if total <= 0.0:
        raise ValueError("a distribution must have positive total mass")
    return array / total


def jensen_shannon_divergence(
    left: Sequence[float] | np.ndarray,
    right: Sequence[float] | np.ndarray,
) -> float:
    """Return base-2 Jensen-Shannon divergence in the closed interval [0, 1]."""

    p = _normalise_distribution(left)
    q = _normalise_distribution(right)
    if p.shape != q.shape:
        raise ValueError("the two distributions must have the same shape")
    midpoint = 0.5 * (p + q)

    def _kl(values: np.ndarray) -> float:
        mask = values > 0.0
        return float(np.sum(values[mask] * np.log2(values[mask] / midpoint[mask])))

    value = 0.5 * _kl(p) + 0.5 * _kl(q)
    # Protect exact boundary tests from harmless floating-point overshoot.
    return float(np.clip(value, 0.0, 1.0))


def alignment_score(
    left: Sequence[float] | np.ndarray,
    right: Sequence[float] | np.ndarray,
) -> float:
    """Return 0--100 alignment derived from the square root of JSD."""

    divergence = jensen_shannon_divergence(left, right)
    return float(np.clip(100.0 * (1.0 - math.sqrt(divergence)), 0.0, 100.0))


def total_variation_distance(
    left: Sequence[float] | np.ndarray,
    right: Sequence[float] | np.ndarray,
) -> float:
    """Return total-variation distance in the closed interval [0, 1]."""

    p = _normalise_distribution(left)
    q = _normalise_distribution(right)
    if p.shape != q.shape:
        raise ValueError("the two distributions must have the same shape")
    return float(np.clip(0.5 * np.abs(p - q).sum(), 0.0, 1.0))


def _require_nonempty_text(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    for column in columns:
        values = frame[column].astype("string").str.strip()
        if values.isna().any() or values.eq("").any():
            raise ValueError(f"column {column!r} must not contain blank values")


def validate_standard_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalise the strict, PII-free input schema.

    Exact columns are required so that a username, message body, telephone
    number, or precise address cannot accidentally flow into derived outputs.
    Every row must also carry ``data_scope`` and provenance fields; the module
    never infers that synthetic or incomplete data are real observations.
    """

    missing = sorted(set(REQUIRED_COLUMNS) - set(frame.columns))
    unexpected = sorted(set(frame.columns) - set(REQUIRED_COLUMNS))
    if missing:
        raise ValueError(f"missing required columns: {missing}")
    if unexpected:
        raise ValueError(f"unexpected columns are not permitted: {unexpected}")
    if frame.empty:
        raise ValueError("the input CSV must contain at least one observation")

    clean = frame.loc[:, REQUIRED_COLUMNS].copy()
    text_columns = (
        "source",
        "region",
        "topic",
        "record_id",
        "access_route",
        "license_note",
        "data_scope",
    )
    _require_nonempty_text(clean, text_columns)
    for column in text_columns:
        clean[column] = clean[column].astype("string").str.strip()

    unknown_sources = sorted(set(clean["source"]) - ALLOWED_SOURCES)
    if unknown_sources:
        raise ValueError(f"unknown source values: {unknown_sources}")

    observed = pd.to_datetime(clean["observed_at"], errors="coerce", utc=True)
    if observed.isna().any():
        bad_rows = clean.index[observed.isna()].tolist()
        raise ValueError(f"observed_at contains invalid timestamps at rows {bad_rows}")
    clean["observed_at"] = observed.dt.tz_convert(DEFAULT_TIMEZONE)

    for column in ("rank", "heat", "count"):
        original = clean[column]
        blank = original.isna() | original.astype("string").str.strip().eq("")
        numeric = pd.to_numeric(original, errors="coerce")
        invalid = ~blank & numeric.isna()
        if invalid.any():
            bad_rows = clean.index[invalid].tolist()
            raise ValueError(f"{column} contains non-numeric values at rows {bad_rows}")
        clean[column] = numeric
    if (clean["rank"].dropna() <= 0.0).any():
        raise ValueError("rank values must be positive when supplied")
    if (clean["heat"].dropna() < 0.0).any():
        raise ValueError("heat values must be non-negative when supplied")
    if (clean["count"].dropna() <= 0.0).any():
        raise ValueError("count values must be positive when supplied")
    for column in ("rank", "heat", "count"):
        supplied = clean[column].dropna().to_numpy(dtype=float)
        if supplied.size and not np.isfinite(supplied).all():
            raise ValueError(f"{column} values must be finite")

    identity = ["source", "observed_at", "region", "record_id"]
    duplicates = clean.duplicated(identity, keep=False)
    if duplicates.any():
        examples = clean.loc[duplicates, identity].head(5).to_dict("records")
        raise ValueError(f"duplicate observation identifiers: {examples}")
    return clean


def load_standard_csv(path: str | Path) -> pd.DataFrame:
    """Read and validate one local CSV.  URLs are explicitly rejected."""

    raw_path = str(path)
    if "://" in raw_path:
        raise ValueError("network URLs are not accepted; provide a local CSV path")
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    return validate_standard_frame(pd.read_csv(source))


def _scope_label(frame: pd.DataFrame) -> str:
    scopes = sorted(str(value) for value in frame["data_scope"].unique())
    return scopes[0] if len(scopes) == 1 else "mixed[" + "+".join(scopes) + "]"


def _effective_weights(frame: pd.DataFrame, weibo_weight: str) -> pd.Series:
    if weibo_weight not in WEIBO_WEIGHT_MODES:
        raise ValueError(f"weibo_weight must be one of {sorted(WEIBO_WEIGHT_MODES)}")
    counts = frame["count"].fillna(1.0).astype(float)
    weights = counts.copy()
    is_weibo = frame["source"].eq(SOURCE_WEIBO)
    if not is_weibo.any():
        return weights

    if weibo_weight == "rank":
        if frame.loc[is_weibo, "rank"].isna().any():
            raise ValueError("all weibo_hot rows require rank for rank weighting")
        ranks = frame.loc[is_weibo, "rank"].to_numpy(dtype=float)
        weights.loc[is_weibo] *= 1.0 / np.log2(ranks + 1.0)
    elif weibo_weight == "heat":
        if frame.loc[is_weibo, "heat"].isna().any():
            raise ValueError("all weibo_hot rows require heat for heat weighting")
        heat = frame.loc[is_weibo, "heat"].to_numpy(dtype=float)
        weights.loc[is_weibo] *= np.log1p(heat)
    # count mode intentionally leaves the base count unchanged.
    if (weights <= 0.0).any() or not np.isfinite(weights.to_numpy()).all():
        raise ValueError("the selected weighting scheme produced non-positive weights")
    return weights


def build_rolling_distributions(
    frame: pd.DataFrame,
    *,
    window_days: int = 7,
    weibo_weight: str = "rank",
) -> pd.DataFrame:
    """Build full-calendar rolling topic distributions for every region/source.

    A result is emitted only after a complete calendar window is available.
    Missing observation days contribute zero rather than silently shortening
    the window.
    """

    if not isinstance(window_days, int) or window_days < 1:
        raise ValueError("window_days must be a positive integer")
    clean = validate_standard_frame(frame)
    scope = _scope_label(clean)
    weighted = clean.copy()
    weighted["effective_weight"] = _effective_weights(weighted, weibo_weight)
    weighted["date"] = (
        weighted["observed_at"].dt.normalize().dt.tz_localize(None)
    )
    daily = (
        weighted.groupby(["region", "date", "source", "topic"], observed=True)
        .agg(
            daily_weight=("effective_weight", "sum"),
            daily_records=("record_id", "size"),
        )
        .reset_index()
    )

    pieces: list[pd.DataFrame] = []
    for region, region_daily in daily.groupby("region", sort=True, observed=True):
        first_day = pd.Timestamp(region_daily["date"].min())
        last_day = pd.Timestamp(region_daily["date"].max())
        if (last_day - first_day).days + 1 < window_days:
            continue
        dates = pd.date_range(first_day, last_day, freq="D")
        sources = sorted(str(value) for value in region_daily["source"].unique())
        topics = sorted(str(value) for value in region_daily["topic"].unique())
        complete_index = pd.MultiIndex.from_product(
            [dates, sources, topics], names=["date", "source", "topic"]
        )
        complete = (
            region_daily.set_index(["date", "source", "topic"])[
                ["daily_weight", "daily_records"]
            ]
            .reindex(complete_index, fill_value=0.0)
            .reset_index()
        )
        complete["rolling_weight"] = complete.groupby(
            ["source", "topic"], sort=False, observed=True
        )["daily_weight"].transform(
            lambda values: values.rolling(window_days, min_periods=window_days).sum()
        )
        complete["rolling_records"] = complete.groupby(
            ["source", "topic"], sort=False, observed=True
        )["daily_records"].transform(
            lambda values: values.rolling(window_days, min_periods=window_days).sum()
        )
        complete = complete.loc[complete["rolling_weight"].notna()].copy()
        source_totals = complete.groupby(
            ["date", "source"], sort=False, observed=True
        )["rolling_weight"].transform("sum")
        complete["share"] = np.where(
            source_totals > 0.0,
            complete["rolling_weight"] / source_totals,
            np.nan,
        )
        complete["data_scope"] = scope
        complete["region"] = str(region)
        complete["window_start"] = complete["date"] - pd.to_timedelta(
            window_days - 1, unit="D"
        )
        complete["window_end"] = complete["date"]
        complete["window_days"] = window_days
        pieces.append(complete.loc[:, ROLLING_COLUMNS])

    if not pieces:
        return pd.DataFrame(columns=ROLLING_COLUMNS)
    return (
        pd.concat(pieces, ignore_index=True)
        .sort_values(["region", "window_end", "source", "topic"])
        .reset_index(drop=True)
    )


def _source_vector(group: pd.DataFrame, source: str, topics: list[str]) -> np.ndarray | None:
    subset = group.loc[group["source"].eq(source) & group["share"].notna()]
    if subset.empty or float(subset["rolling_weight"].sum()) <= 0.0:
        return None
    shares = subset.set_index("topic")["share"].reindex(topics, fill_value=0.0)
    return _normalise_distribution(shares.to_numpy(dtype=float))


def _source_records(group: pd.DataFrame, source: str) -> int:
    subset = group.loc[group["source"].eq(source)]
    return int(round(float(subset["rolling_records"].sum()))) if not subset.empty else 0


def calculate_indices(
    rolling_distributions: pd.DataFrame,
    *,
    top_k: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calculate index and per-topic gap tables from rolling distributions."""

    if not isinstance(top_k, int) or top_k < 1:
        raise ValueError("top_k must be a positive integer")
    if rolling_distributions.empty:
        return pd.DataFrame(columns=INDEX_COLUMNS), pd.DataFrame(columns=GAP_COLUMNS)

    index_rows: list[dict[str, Any]] = []
    gap_rows: list[dict[str, Any]] = []
    keys = ["data_scope", "region", "window_start", "window_end", "window_days"]
    for key, group in rolling_distributions.groupby(keys, sort=True, observed=True):
        scope, region, window_start, window_end, window_days = key
        topics = sorted(str(value) for value in group["topic"].unique())
        hot = _source_vector(group, SOURCE_WEIBO, topics)
        demand = _source_vector(group, SOURCE_DEMAND, topics)
        if hot is None or demand is None:
            continue
        government = _source_vector(group, SOURCE_GOVERNMENT, topics)
        jsd_hd = jensen_shannon_divergence(hot, demand)
        alignment_hd = alignment_score(hot, demand)
        blind_spot = 100.0 * total_variation_distance(hot, demand)

        ranked_topics = sorted(
            ((topic, float(hot[index])) for index, topic in enumerate(topics) if hot[index] > 0.0),
            key=lambda pair: (-pair[1], pair[0]),
        )
        top_topics = [topic for topic, _ in ranked_topics[:top_k]]
        topic_index = {topic: index for index, topic in enumerate(topics)}
        coverage = 100.0 * float(
            sum(demand[topic_index[topic]] for topic in top_topics)
        )

        if government is None:
            alignment_gh = math.nan
            alignment_gd = math.nan
            hot_bias = math.nan
        else:
            alignment_gh = alignment_score(government, hot)
            alignment_gd = alignment_score(government, demand)
            hot_bias = alignment_gh - alignment_gd

        index_rows.append(
            {
                "data_scope": scope,
                "region": region,
                "window_start": window_start,
                "window_end": window_end,
                "window_days": int(window_days),
                "top_k": top_k,
                "topic_count": len(topics),
                "jsd_hd": jsd_hd,
                "alignment_hd": alignment_hd,
                "blind_spot_tv": blind_spot,
                "coverage_at_k": coverage,
                "top_k_hot_topics": "|".join(top_topics),
                "alignment_gh": alignment_gh,
                "alignment_gd": alignment_gd,
                "hot_bias": hot_bias,
                "weibo_records": _source_records(group, SOURCE_WEIBO),
                "leader_board_records": _source_records(group, SOURCE_DEMAND),
                "government_records": _source_records(group, SOURCE_GOVERNMENT),
            }
        )
        for index, topic in enumerate(topics):
            gap_rows.append(
                {
                    "data_scope": scope,
                    "region": region,
                    "window_start": window_start,
                    "window_end": window_end,
                    "window_days": int(window_days),
                    "topic": topic,
                    "weibo_share": float(hot[index]),
                    "leader_board_share": float(demand[index]),
                    "government_share": (
                        float(government[index]) if government is not None else math.nan
                    ),
                    "gap_demand_minus_hot_pp": 100.0 * float(demand[index] - hot[index]),
                }
            )

    return (
        pd.DataFrame(index_rows, columns=INDEX_COLUMNS),
        pd.DataFrame(gap_rows, columns=GAP_COLUMNS),
    )


def analyse_frame(
    frame: pd.DataFrame,
    *,
    window_days: int = 7,
    top_k: int = 3,
    weibo_weight: str = "rank",
) -> IndexOutputs:
    """Validate one frame and produce all offline index tables."""

    clean = validate_standard_frame(frame)
    rolling = build_rolling_distributions(
        clean, window_days=window_days, weibo_weight=weibo_weight
    )
    indices, gaps = calculate_indices(rolling, top_k=top_k)
    scope_label = _scope_label(clean)
    metadata: dict[str, Any] = {
        "data_scope": scope_label,
        "evidence_warning": (
            "Synthetic code demonstration only; this is not a real Weibo or "
            "Leader Board validation."
            if "synthetic" in scope_label
            else "Interpret results only within the explicitly declared input data_scope."
        ),
        "row_count": int(len(clean)),
        "regions": sorted(str(value) for value in clean["region"].unique()),
        "sources": sorted(str(value) for value in clean["source"].unique()),
        "window_days": window_days,
        "top_k": top_k,
        "weibo_weight": weibo_weight,
        "network_access": "none",
        "complete_calendar_windows_only": True,
        "formula": {
            "jsd_hd": "0.5*KL2(H||M)+0.5*KL2(D||M), M=(H+D)/2",
            "alignment_hd": "100*(1-sqrt(JSD_2(H,D)))",
            "blind_spot_tv": "50*sum(abs(H-D))",
            "gap_demand_minus_hot_pp": "100*(D_k-H_k)",
            "coverage_at_k": "100*sum(D_k for k in TopK(H))",
            "hot_bias": "Alignment(G,H)-Alignment(G,D)",
        },
    }
    return IndexOutputs(rolling, indices, gaps, metadata)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def analyse_csv(
    input_path: str | Path,
    *,
    window_days: int = 7,
    top_k: int = 3,
    weibo_weight: str = "rank",
) -> IndexOutputs:
    """Load a local CSV, analyse it, and attach input provenance metadata."""

    supplied_path = Path(input_path)
    source = supplied_path.resolve()
    outputs = analyse_frame(
        load_standard_csv(source),
        window_days=window_days,
        top_k=top_k,
        weibo_weight=weibo_weight,
    )
    metadata = dict(outputs.metadata)
    metadata["input_file"] = supplied_path.as_posix()
    metadata["input_sha256"] = _sha256(source)
    return IndexOutputs(
        outputs.rolling_distributions,
        outputs.index_timeseries,
        outputs.topic_gaps,
        metadata,
    )


def write_outputs(outputs: IndexOutputs, output_directory: str | Path) -> dict[str, Path]:
    """Write the three derived CSVs and one metadata JSON file."""

    destination = Path(output_directory)
    destination.mkdir(parents=True, exist_ok=True)
    paths = {
        "rolling_distributions": destination / "rolling_topic_distributions.csv",
        "index_timeseries": destination / "hotspot_demand_index.csv",
        "topic_gaps": destination / "topic_visibility_gap.csv",
        "metadata": destination / "hotspot_demand_index_metadata.json",
    }
    outputs.rolling_distributions.to_csv(paths["rolling_distributions"], index=False)
    outputs.index_timeseries.to_csv(paths["index_timeseries"], index=False)
    outputs.topic_gaps.to_csv(paths["topic_gaps"], index=False)
    paths["metadata"].write_text(
        json.dumps(outputs.metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return paths


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the offline platform-attention/demand mismatch index."
    )
    parser.add_argument("--input", required=True, type=Path, help="Local standard CSV")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument(
        "--weibo-weight", choices=sorted(WEIBO_WEIGHT_MODES), default="rank"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    outputs = analyse_csv(
        args.input,
        window_days=args.window_days,
        top_k=args.top_k,
        weibo_weight=args.weibo_weight,
    )
    paths = write_outputs(outputs, args.output_dir)
    summary = {
        "data_scope": outputs.metadata["data_scope"],
        "input_rows": outputs.metadata["row_count"],
        "index_rows": int(len(outputs.index_timeseries)),
        "outputs": {name: str(path.resolve()) for name, path in paths.items()},
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
