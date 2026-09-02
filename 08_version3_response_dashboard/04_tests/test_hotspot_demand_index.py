"""Tests for the offline platform-attention/demand mismatch index."""

from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


V3_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_DIRECTORY = V3_ROOT / "02_experiment_code"
FIXTURE = (
    V3_ROOT
    / "03_data"
    / "external_index_template"
    / "synthetic_hotspot_demand_fixture.csv"
)
sys.path.insert(0, str(EXPERIMENT_DIRECTORY))

from build_hotspot_demand_index import (  # noqa: E402
    REQUIRED_COLUMNS,
    SOURCE_DEMAND,
    SOURCE_GOVERNMENT,
    SOURCE_WEIBO,
    alignment_score,
    analyse_csv,
    analyse_frame,
    build_rolling_distributions,
    jensen_shannon_divergence,
    load_standard_csv,
    total_variation_distance,
    validate_standard_frame,
    write_outputs,
)


def _row(
    source: str,
    day: int,
    topic: str,
    record_id: str,
    *,
    rank: float = math.nan,
    count: float = 1.0,
    scope: str = "synthetic",
) -> dict[str, object]:
    timestamp = pd.Timestamp("2026-01-01T08:00:00+08:00") + pd.Timedelta(
        days=day
    )
    return {
        "source": source,
        "observed_at": timestamp.isoformat(),
        "region": "test-region",
        "topic": topic,
        "rank": rank,
        "heat": math.nan,
        "count": count,
        "record_id": record_id,
        "access_route": "unit_test_fixture",
        "license_note": "generated_no_external_content",
        "data_scope": scope,
    }


def _seven_day_frame(*, include_government: bool = True) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for day in range(7):
        rows.append(_row(SOURCE_WEIBO, day, "A", f"w-{day}", rank=1.0))
        rows.append(_row(SOURCE_DEMAND, day, "B", f"d-{day}"))
        if include_government:
            rows.append(_row(SOURCE_GOVERNMENT, day, "A", f"g-{day}"))
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS)


class FormulaBoundaryTests(unittest.TestCase):
    def test_identical_distributions_have_exact_alignment_boundary(self) -> None:
        left = np.array([0.7, 0.2, 0.1])
        right = np.array([0.7, 0.2, 0.1])
        self.assertAlmostEqual(jensen_shannon_divergence(left, right), 0.0, places=14)
        self.assertAlmostEqual(alignment_score(left, right), 100.0, places=12)
        self.assertAlmostEqual(total_variation_distance(left, right), 0.0, places=14)

    def test_mutually_exclusive_distributions_have_exact_mismatch_boundary(self) -> None:
        left = np.array([1.0, 0.0])
        right = np.array([0.0, 1.0])
        self.assertAlmostEqual(jensen_shannon_divergence(left, right), 1.0, places=14)
        self.assertAlmostEqual(alignment_score(left, right), 0.0, places=12)
        self.assertAlmostEqual(total_variation_distance(left, right), 1.0, places=14)


class InputContractTests(unittest.TestCase):
    def test_data_scope_is_mandatory_and_cannot_be_blank(self) -> None:
        frame = _seven_day_frame()
        with self.assertRaisesRegex(ValueError, "missing required columns"):
            validate_standard_frame(frame.drop(columns="data_scope"))
        frame.loc[0, "data_scope"] = ""
        with self.assertRaisesRegex(ValueError, "data_scope"):
            validate_standard_frame(frame)

    def test_unexpected_columns_are_rejected_to_keep_input_pii_free(self) -> None:
        frame = _seven_day_frame().assign(message_body="must not enter analysis")
        with self.assertRaisesRegex(ValueError, "unexpected columns"):
            validate_standard_frame(frame)

    def test_non_numeric_supplied_values_are_not_silently_treated_as_missing(self) -> None:
        frame = _seven_day_frame()
        frame["count"] = frame["count"].astype(object)
        frame.loc[0, "count"] = "not-a-number"
        with self.assertRaisesRegex(ValueError, "count contains non-numeric"):
            validate_standard_frame(frame)

    def test_network_url_is_never_accepted_as_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "network URLs"):
            load_standard_csv("https://example.invalid/data.csv")


class RollingIndexTests(unittest.TestCase):
    def test_complete_seven_day_window_hotbias_and_coverage(self) -> None:
        outputs = analyse_frame(_seven_day_frame(), window_days=7, top_k=1)
        self.assertEqual(len(outputs.index_timeseries), 1)
        row = outputs.index_timeseries.iloc[0]
        self.assertAlmostEqual(float(row["alignment_hd"]), 0.0, places=12)
        self.assertAlmostEqual(float(row["blind_spot_tv"]), 100.0, places=12)
        self.assertAlmostEqual(float(row["coverage_at_k"]), 0.0, places=12)
        self.assertEqual(row["top_k_hot_topics"], "A")
        self.assertAlmostEqual(float(row["alignment_gh"]), 100.0, places=12)
        self.assertAlmostEqual(float(row["alignment_gd"]), 0.0, places=12)
        self.assertAlmostEqual(float(row["hot_bias"]), 100.0, places=12)
        self.assertEqual(int(row["weibo_records"]), 7)
        self.assertEqual(int(row["leader_board_records"]), 7)
        self.assertEqual(int(row["government_records"]), 7)

        gaps = outputs.topic_gaps.set_index("topic")
        self.assertAlmostEqual(float(gaps.loc["A", "gap_demand_minus_hot_pp"]), -100.0)
        self.assertAlmostEqual(float(gaps.loc["B", "gap_demand_minus_hot_pp"]), 100.0)

    def test_government_metrics_are_missing_when_g_stream_is_absent(self) -> None:
        outputs = analyse_frame(
            _seven_day_frame(include_government=False), window_days=7, top_k=1
        )
        row = outputs.index_timeseries.iloc[0]
        self.assertTrue(math.isnan(float(row["alignment_gh"])))
        self.assertTrue(math.isnan(float(row["alignment_gd"])))
        self.assertTrue(math.isnan(float(row["hot_bias"])))
        self.assertEqual(int(row["government_records"]), 0)

    def test_rolling_window_drops_oldest_calendar_day(self) -> None:
        rows: list[dict[str, object]] = []
        for day in range(8):
            hot_topic = "A" if day < 7 else "B"
            rows.append(
                _row(SOURCE_WEIBO, day, hot_topic, f"w-roll-{day}", rank=1.0)
            )
            rows.append(_row(SOURCE_DEMAND, day, "A", f"d-roll-{day}"))
        frame = pd.DataFrame(rows, columns=REQUIRED_COLUMNS)
        rolling = build_rolling_distributions(frame, window_days=7)

        first_end = pd.Timestamp("2026-01-07")
        second_end = pd.Timestamp("2026-01-08")
        self.assertEqual(sorted(rolling["window_end"].unique()), [first_end, second_end])
        second_hot = rolling.loc[
            rolling["window_end"].eq(second_end)
            & rolling["source"].eq(SOURCE_WEIBO)
        ].set_index("topic")
        self.assertAlmostEqual(float(second_hot.loc["A", "share"]), 6.0 / 7.0)
        self.assertAlmostEqual(float(second_hot.loc["B", "share"]), 1.0 / 7.0)

    def test_fewer_than_seven_days_produce_no_partial_window(self) -> None:
        frame = _seven_day_frame().loc[
            lambda data: pd.to_datetime(data["observed_at"]).dt.day <= 6
        ]
        outputs = analyse_frame(frame, window_days=7, top_k=1)
        self.assertTrue(outputs.rolling_distributions.empty)
        self.assertTrue(outputs.index_timeseries.empty)
        self.assertTrue(outputs.topic_gaps.empty)


class FixtureAndOutputTests(unittest.TestCase):
    def test_checked_in_fixture_is_synthetic_and_generates_index(self) -> None:
        frame = load_standard_csv(FIXTURE)
        self.assertEqual(set(frame["data_scope"]), {"synthetic"})
        outputs = analyse_csv(FIXTURE, window_days=7, top_k=2)
        self.assertEqual(outputs.metadata["data_scope"], "synthetic")
        self.assertEqual(outputs.metadata["network_access"], "none")
        self.assertIn("not a real Weibo", outputs.metadata["evidence_warning"])
        self.assertEqual(len(outputs.index_timeseries), 1)
        self.assertEqual(outputs.index_timeseries.iloc[0]["data_scope"], "synthetic")
        self.assertTrue(outputs.topic_gaps["data_scope"].eq("synthetic").all())

    def test_writer_emits_all_offline_artifacts_and_metadata(self) -> None:
        outputs = analyse_csv(FIXTURE, window_days=7, top_k=2)
        with tempfile.TemporaryDirectory() as directory:
            paths = write_outputs(outputs, directory)
            self.assertEqual(
                set(paths),
                {"rolling_distributions", "index_timeseries", "topic_gaps", "metadata"},
            )
            self.assertTrue(all(path.is_file() for path in paths.values()))
            metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
            self.assertEqual(metadata["data_scope"], "synthetic")
            self.assertEqual(metadata["network_access"], "none")
            self.assertEqual(len(metadata["input_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
