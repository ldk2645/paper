"""Regression and mechanism tests for the isolated Version 3 model.

Run from the repository root with::

    python -m unittest discover -s 08_version3_response_dashboard/04_tests -v

The tests deliberately use small populations for speed.  Institutional timing
tests retain the observed petition-700024 threshold day so that the 11-day and
57-day response conditions are checked at their documented calendar steps.
"""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


TEST_FILE = Path(__file__).resolve()
V3_ROOT = TEST_FILE.parents[1]
REPOSITORY_ROOT = TEST_FILE.parents[2]
MODEL_DIRECTORY = V3_ROOT / "01_model"
if str(MODEL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(MODEL_DIRECTORY))

from base_v2 import PendingPetitionResponse  # noqa: E402
from model_v3 import (  # noqa: E402
    V1_FROZEN_SHA256,
    V2_FROZEN_SHA256,
    Version3Config,
    Version3Simulation,
)


EXPECTED_V1_SHA256 = (
    "AB78E6C64AFB6FD487E40A48FBBCD1B09A84EE3FBC9085530F8833DE3543D7EC"
)
EXPECTED_V2_SHA256 = (
    "83BCD501B5A22C59832CC5441FFDF1054361E46C75E1BEE39F70E8E8CA0FC8DF"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _short_config(**overrides: object) -> Version3Config:
    """Return a compact observed-calendar configuration for mechanism tests."""

    values: dict[str, object] = {
        "steps": 20,
        "population_size": 24,
        "attention_budget": 3,
        "initial_information": 4,
        "spontaneous_posts_per_step": 1,
        "petition_close_step": 18,
        "observed_response_threshold_step": 2,
        "observed_debate_threshold_step": 12,
        "observed_debate_step": 16,
        "response_delay": 3,
        "seed": 83000,
    }
    values.update(overrides)
    return Version3Config.case_700024(**values)


def _calendar_config(
    *, response_delay: int, seed: int = 83001, **overrides: object
) -> Version3Config:
    """Keep the case threshold at day 14 while reducing population cost."""

    values: dict[str, object] = {
        "steps": 190,
        "population_size": 24,
        "attention_budget": 3,
        "initial_information": 4,
        "spontaneous_posts_per_step": 1,
        "response_delay": response_delay,
        "seed": seed,
    }
    values.update(overrides)
    return Version3Config.case_700024(**values)


class VersionIsolationTests(unittest.TestCase):
    def test_v1_and_v2_parent_snapshots_are_byte_identical(self) -> None:
        live_v1 = REPOSITORY_ROOT / "01_model_core" / "model.py"
        live_v2 = (
            REPOSITORY_ROOT
            / "07_version2_uk_petition"
            / "01_model"
            / "model_v2.py"
        )
        v3_v1_snapshot = MODEL_DIRECTORY / "base_v1.py"
        v3_v2_snapshot = MODEL_DIRECTORY / "base_v2.py"

        self.assertEqual(EXPECTED_V1_SHA256, V1_FROZEN_SHA256)
        self.assertEqual(EXPECTED_V2_SHA256, V2_FROZEN_SHA256)
        self.assertEqual(EXPECTED_V1_SHA256, _sha256(live_v1))
        self.assertEqual(EXPECTED_V1_SHA256, _sha256(v3_v1_snapshot))
        self.assertEqual(EXPECTED_V2_SHA256, _sha256(live_v2))
        self.assertEqual(EXPECTED_V2_SHA256, _sha256(v3_v2_snapshot))
        self.assertEqual(live_v1.read_bytes(), v3_v1_snapshot.read_bytes())
        self.assertEqual(live_v2.read_bytes(), v3_v2_snapshot.read_bytes())


class GovernmentPublicationTests(unittest.TestCase):
    def test_exactly_one_routine_government_item_is_published_each_day(self) -> None:
        config = _short_config()
        result = Version3Simulation(config).run()

        self.assertEqual(config.steps, result.summary["routine_government_posts_published"])
        self.assertEqual(
            config.steps,
            int(result.metrics["routine_government_posts_published"].sum()),
        )
        self.assertTrue(
            result.metrics["routine_government_posts_published"].eq(1).all()
        )
        np.testing.assert_array_equal(
            result.metrics["cumulative_routine_government_posts"].to_numpy(),
            np.arange(1, config.steps + 1),
        )

    def test_response_day_has_one_additional_government_item(self) -> None:
        config = _short_config(response_delay=3)
        result = Version3Simulation(config).run()
        due_step = config.observed_response_threshold_step + config.response_delay

        response_rows = result.metrics[
            result.metrics["response_government_posts_published"].eq(1)
        ]
        self.assertEqual([due_step], response_rows["step"].tolist())
        self.assertEqual(
            1, result.summary["response_government_posts_published"]
        )
        self.assertEqual(
            2,
            int(
                response_rows.iloc[0]["routine_government_posts_published"]
                + response_rows.iloc[0]["response_government_posts_published"]
            ),
        )
        published_events = result.events[
            result.events["event_type"].eq("government_response_published")
        ]
        self.assertEqual([due_step], published_events["step"].tolist())


class ResponseMechanismTests(unittest.TestCase):
    def _execute_manual_response(
        self, multiplier: float
    ) -> tuple[Version3Simulation, object]:
        config = _short_config(response_heat_multiplier=multiplier)
        simulation = Version3Simulation(config)
        petition_item = simulation._petition_item()
        petition_item.heat = 10.0
        simulation._new_information(
            topic=config.petition_topic_index,
            emotional_intensity=0.9,
            source="spontaneous",
            step=0,
            heat=8.0,
        )
        same_topic_nonpetition = simulation.information_pool[-1]
        simulation.pending_responses = [
            PendingPetitionResponse(
                petition_id=config.petition_id,
                trigger_step=0,
                due_step=0,
            )
        ]

        trust_signal, executed = simulation._government_action(0)
        self.assertEqual(1, executed)
        self.assertEqual(0.0, trust_signal)
        return simulation, same_topic_nonpetition

    def test_response_multiplier_070_reduces_heat_exactly_thirty_percent(self) -> None:
        simulation, same_topic_nonpetition = self._execute_manual_response(0.70)

        self.assertAlmostEqual(7.0, simulation._petition_item().heat)
        self.assertAlmostEqual(-3.0, simulation._last_response_heat_delta)
        self.assertAlmostEqual(
            10.0, simulation._last_response_heat_before_immediate
        )
        self.assertAlmostEqual(
            7.0, simulation._last_response_heat_after_immediate
        )
        self.assertAlmostEqual(
            0.30, simulation._last_realized_heat_reduction_fraction
        )
        self.assertAlmostEqual(8.0, same_topic_nonpetition.heat)

    def test_response_multiplier_100_does_not_force_cooling(self) -> None:
        simulation, same_topic_nonpetition = self._execute_manual_response(1.00)

        self.assertAlmostEqual(10.0, simulation._petition_item().heat)
        self.assertAlmostEqual(0.0, simulation._last_response_heat_delta)
        self.assertAlmostEqual(
            10.0, simulation._last_response_heat_before_immediate
        )
        self.assertAlmostEqual(
            10.0, simulation._last_response_heat_after_immediate
        )
        self.assertAlmostEqual(
            0.0, simulation._last_realized_heat_reduction_fraction
        )
        self.assertAlmostEqual(8.0, same_topic_nonpetition.heat)

    def test_response_targets_only_the_focal_petition(self) -> None:
        simulation, same_topic_nonpetition = self._execute_manual_response(0.70)

        self.assertAlmostEqual(7.0, simulation._petition_item().heat)
        self.assertAlmostEqual(8.0, same_topic_nonpetition.heat)
        self.assertEqual(
            1,
            sum(
                item.source == "government_response"
                for item in simulation.information_pool
            ),
        )
        self.assertEqual(1, simulation.routine_government_posts_published)
        self.assertEqual(1, simulation.response_government_posts_published)

    def test_early_and_late_delays_execute_once_on_exact_case_days(self) -> None:
        for delay, expected_step in ((11, 25), (57, 71)):
            with self.subTest(response_delay=delay):
                result = Version3Simulation(
                    _calendar_config(response_delay=delay)
                ).run()
                published = result.events[
                    result.events["event_type"].eq(
                        "government_response_published"
                    )
                ]

                self.assertEqual([expected_step], published["step"].tolist())
                self.assertEqual(
                    expected_step, result.summary["response_executed_step"]
                )
                self.assertEqual(delay, result.summary["realized_response_delay_days"])
                self.assertEqual(1, result.summary["responses_scheduled"])
                self.assertEqual(1, result.summary["responses_executed"])
                self.assertEqual(
                    1, result.summary["response_government_posts_published"]
                )

    def test_common_seed_heat_groups_have_identical_pre_response_trajectories(self) -> None:
        common: dict[str, object] = {
            "steps": 40,
            "population_size": 30,
            "attention_budget": 3,
            "initial_information": 5,
            "spontaneous_posts_per_step": 1,
            "petition_close_step": 38,
            "observed_response_threshold_step": 14,
            "observed_debate_threshold_step": 35,
            "observed_debate_step": 39,
            "response_delay": 11,
            "seed": 83123,
            "alpha": 0.60,
        }
        neutral = Version3Simulation(
            Version3Config.case_700024(
                response_heat_multiplier=1.00, **common
            )
        ).run()
        cooling = Version3Simulation(
            Version3Config.case_700024(
                response_heat_multiplier=0.70, **common
            )
        ).run()
        response_step = 25
        neutral_pre = neutral.metrics[neutral.metrics["step"] < response_step]
        cooling_pre = cooling.metrics[cooling.metrics["step"] < response_step]

        # The treatment label is recorded from step zero; it is the only field
        # allowed to differ before the response is actually executed.
        pd.testing.assert_frame_equal(
            neutral_pre.drop(columns=["response_heat_multiplier"]).reset_index(
                drop=True
            ),
            cooling_pre.drop(columns=["response_heat_multiplier"]).reset_index(
                drop=True
            ),
        )
        pd.testing.assert_frame_equal(
            neutral.events[neutral.events["step"] < response_step].reset_index(
                drop=True
            ),
            cooling.events[cooling.events["step"] < response_step].reset_index(
                drop=True
            ),
        )


class DashboardDiagnosticsTests(unittest.TestCase):
    def test_dashboard_indices_and_distributions_stay_in_valid_ranges(self) -> None:
        result = Version3Simulation(_short_config(alpha=0.60)).run()
        metrics = result.metrics

        for column in (
            "hotspot_demand_misalignment",
            "hotspot_demand_jsd",
            "hotspot_demand_topk_overlap",
            "hotspot_demand_top1_agreement",
            "hotspot_baseline_demand_misalignment",
            "hotspot_baseline_demand_jsd",
            "hotspot_baseline_demand_topk_overlap",
            "hotspot_baseline_demand_top1_agreement",
        ):
            self.assertTrue(np.isfinite(metrics[column]).all(), column)
            self.assertTrue(metrics[column].between(0.0, 1.0).all(), column)
        self.assertTrue(
            metrics["hotspot_demand_rank_correlation"].between(-1.0, 1.0).all()
        )

        hotspot_columns = [
            column for column in metrics if column.startswith("hotspot_share_")
        ]
        current_demand_columns = [
            column
            for column in metrics
            if column.startswith("current_demand_share_")
        ]
        baseline_demand_columns = [
            column
            for column in metrics
            if column.startswith("baseline_demand_share_")
        ]
        self.assertEqual(result.config.topic_count, len(hotspot_columns))
        self.assertEqual(result.config.topic_count, len(current_demand_columns))
        self.assertEqual(result.config.topic_count, len(baseline_demand_columns))
        np.testing.assert_allclose(metrics[hotspot_columns].sum(axis=1), 1.0)
        np.testing.assert_allclose(
            metrics[current_demand_columns].sum(axis=1), 1.0
        )
        np.testing.assert_allclose(
            metrics[baseline_demand_columns].sum(axis=1), 1.0
        )
        self.assertTrue((metrics[hotspot_columns] >= 0.0).all().all())
        self.assertTrue((metrics[current_demand_columns] >= 0.0).all().all())
        self.assertTrue((metrics[baseline_demand_columns] >= 0.0).all().all())
        self.assertTrue(
            metrics["hotspot_top_topic"].isin(result.config.topic_names).all()
        )
        self.assertTrue(
            metrics["demand_top_topic"].isin(result.config.topic_names).all()
        )
        self.assertTrue(
            metrics["baseline_demand_top_topic"]
            .isin(result.config.topic_names)
            .all()
        )


class ReproducibilityTests(unittest.TestCase):
    def test_same_configuration_and_seed_are_fully_deterministic(self) -> None:
        config = _short_config(seed=83999, response_heat_multiplier=0.70)

        first = Version3Simulation(config).run()
        second = Version3Simulation(config).run()

        pd.testing.assert_frame_equal(first.metrics, second.metrics)
        pd.testing.assert_frame_equal(first.storms, second.storms)
        pd.testing.assert_frame_equal(first.events, second.events)
        self.assertEqual(first.summary, second.summary)


if __name__ == "__main__":
    unittest.main()
