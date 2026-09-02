"""Regression and mechanism tests for the isolated UK-petition Version 2.

Run from the repository root with::

    python -m unittest discover -s 07_version2_uk_petition/04_tests -v

The tests intentionally exercise the institutional state transitions directly
as well as a short end-to-end run.  They never import or mutate the live V1
module; the only V1 access is a byte-level integrity check.
"""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIRECTORY = V2_ROOT / "01_model"
RUNNER_DIRECTORY = V2_ROOT / "02_experiment_code"
sys.path.insert(0, str(MODEL_DIRECTORY))
sys.path.insert(0, str(RUNNER_DIRECTORY))

from model_v2 import (  # noqa: E402
    PendingPetitionResponse,
    UKPetitionConfig,
    UKPetitionSimulation,
    V1_FROZEN_SHA256,
)
from run_v2_experiment import (  # noqa: E402
    DELAY_CONDITIONS,
    _safe_output_dir,
    build_tasks,
)


EXPECTED_V1_SHA256 = (
    "AB78E6C64AFB6FD487E40A48FBBCD1B09A84EE3FBC9085530F8833DE3543D7EC"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _observed_config(**overrides: object) -> UKPetitionConfig:
    """Return a small, valid observed-calendar configuration for fast tests."""

    values: dict[str, object] = {
        "steps": 12,
        "population_size": 8,
        "attention_budget": 1,
        "initial_information": 0,
        "spontaneous_posts_per_step": 0,
        "petition_close_step": 8,
        "observed_response_threshold_step": 2,
        "observed_debate_threshold_step": 6,
        "observed_debate_step": 9,
        "response_delay": 2,
        "seed": 73000,
    }
    values.update(overrides)
    return UKPetitionConfig.case_700024(**values)


def _synthetic_config(**overrides: object) -> UKPetitionConfig:
    """Return a small endogenous-support configuration for signing tests."""

    values: dict[str, object] = {
        "steps": 8,
        "population_size": 4,
        "attention_budget": 1,
        "initial_information": 0,
        "spontaneous_posts_per_step": 0,
        "petition_close_step": 5,
        "trigger_mode": "synthetic_unique_support",
        "synthetic_support_threshold_fraction": 0.50,
        "signature_probability_on_exposure": 1.0,
        "response_delay": 2,
        "seed": 73001,
    }
    values.update(overrides)
    return UKPetitionConfig.case_700024(**values)


def _petition_recommendations(simulation: UKPetitionSimulation) -> np.ndarray:
    petition_index = next(
        index
        for index, item in enumerate(simulation.information_pool)
        if item.item_id == simulation.petition.petition_item_id
    )
    return np.full(
        (simulation.config.population_size, 1),
        petition_index,
        dtype=int,
    )


class VersionIsolationTests(unittest.TestCase):
    def test_v1_hash_and_snapshot_are_byte_identical(self) -> None:
        live_v1 = REPOSITORY_ROOT / "01_model_core" / "model.py"
        frozen_snapshot = MODEL_DIRECTORY / "base_v1.py"

        self.assertEqual(EXPECTED_V1_SHA256, V1_FROZEN_SHA256)
        self.assertEqual(EXPECTED_V1_SHA256, _sha256(live_v1))
        self.assertEqual(EXPECTED_V1_SHA256, _sha256(frozen_snapshot))
        self.assertEqual(live_v1.read_bytes(), frozen_snapshot.read_bytes())


class InstitutionalThresholdTests(unittest.TestCase):
    def test_response_threshold_uses_exact_greater_than_or_equal_once(self) -> None:
        simulation = UKPetitionSimulation(_observed_config())
        step = simulation.config.observed_response_threshold_step
        zeros = np.zeros(simulation.config.topic_count, dtype=float)

        simulation.petition.observed_signature_count = 9_999
        self.assertFalse(simulation._trigger_condition_met(step))
        self.assertEqual(
            0,
            simulation._monitor_and_schedule(
                step=step,
                organic_attention_by_topic=zeros,
                total_attention=0.0,
            ),
        )

        simulation.petition.observed_signature_count = 10_000
        self.assertTrue(simulation._trigger_condition_met(step))
        self.assertEqual(
            1,
            simulation._monitor_and_schedule(
                step=step,
                organic_attention_by_topic=zeros,
                total_attention=0.0,
            ),
        )
        self.assertEqual(
            0,
            simulation._monitor_and_schedule(
                step=step,
                organic_attention_by_topic=zeros,
                total_attention=0.0,
            ),
        )

        self.assertEqual(step, simulation.petition.response_threshold_step)
        self.assertEqual(1, simulation.responses_scheduled)
        self.assertEqual(1, len(simulation.pending_responses))
        threshold_events = [
            event
            for event in simulation.event_records
            if event["event_type"] == "response_threshold_reached"
        ]
        self.assertEqual(1, len(threshold_events))
        self.assertEqual(10_000, threshold_events[0]["value"])

    def test_debate_threshold_uses_exact_greater_than_or_equal_once(self) -> None:
        simulation = UKPetitionSimulation(_observed_config())
        step = simulation.config.observed_debate_threshold_step
        zeros = np.zeros(simulation.config.topic_count, dtype=float)
        # Isolate the debate milestone from the already-tested response trigger.
        simulation.petition.response_threshold_step = (
            simulation.config.observed_response_threshold_step
        )

        simulation.petition.observed_signature_count = 99_999
        simulation._monitor_and_schedule(
            step=step,
            organic_attention_by_topic=zeros,
            total_attention=0.0,
        )
        self.assertIsNone(simulation.petition.debate_threshold_step)

        simulation.petition.observed_signature_count = 100_000
        simulation._monitor_and_schedule(
            step=step,
            organic_attention_by_topic=zeros,
            total_attention=0.0,
        )
        simulation._monitor_and_schedule(
            step=step + 1,
            organic_attention_by_topic=zeros,
            total_attention=0.0,
        )

        self.assertEqual(step, simulation.petition.debate_threshold_step)
        debate_events = [
            event
            for event in simulation.event_records
            if event["event_type"] == "debate_threshold_reached"
        ]
        self.assertEqual(1, len(debate_events))
        self.assertEqual(100_000, debate_events[0]["value"])


class PetitionLifecycleTests(unittest.TestCase):
    def test_response_executes_once_at_the_exact_due_step(self) -> None:
        config = _observed_config(response_delay=3)
        simulation = UKPetitionSimulation(config)
        trigger_step = config.observed_response_threshold_step
        due_step = trigger_step + config.response_delay
        zeros = np.zeros(config.topic_count, dtype=float)
        simulation.petition.observed_signature_count = 10_000
        simulation._monitor_and_schedule(
            step=trigger_step,
            organic_attention_by_topic=zeros,
            total_attention=0.0,
        )

        for step in range(trigger_step, due_step):
            _, executed = simulation._government_action(step)
            self.assertEqual(0, executed)
            self.assertIsNone(simulation.petition.response_executed_step)

        _, executed = simulation._government_action(due_step)
        self.assertEqual(1, executed)
        self.assertEqual(due_step, simulation.petition.response_executed_step)
        self.assertEqual(config.response_delay, due_step - trigger_step)

        _, executed_again = simulation._government_action(due_step + 1)
        self.assertEqual(0, executed_again)
        self.assertEqual(1, simulation.responses_executed)
        published_events = [
            event
            for event in simulation.event_records
            if event["event_type"] == "government_response_published"
        ]
        self.assertEqual(1, len(published_events))

    def test_response_changes_only_the_linked_petition(self) -> None:
        config = _observed_config(
            response_heat_multiplier=0.40,
            direct_response_trust_signal=0.25,
        )
        simulation = UKPetitionSimulation(config)
        petition_item = simulation._petition_item()
        petition_item.heat = 10.0
        simulation._new_information(
            topic=config.petition_topic_index,
            emotional_intensity=0.9,
            source="spontaneous",
            step=0,
            heat=8.0,
        )
        same_topic_item = simulation.information_pool[-1]
        simulation.pending_responses = [
            PendingPetitionResponse(
                petition_id=config.petition_id,
                trigger_step=1,
                due_step=3,
            )
        ]

        trust_signal, executed = simulation._government_action(3)

        self.assertEqual(1, executed)
        self.assertAlmostEqual(4.0, petition_item.heat)
        self.assertAlmostEqual(8.0, same_topic_item.heat)
        self.assertAlmostEqual(-6.0, simulation._last_response_heat_delta)
        self.assertAlmostEqual(0.25, trust_signal)
        self.assertEqual(
            1,
            sum(
                item.source == "government_response"
                for item in simulation.information_pool
            ),
        )

    def test_response_adoption_and_cooling_are_independent(self) -> None:
        config = _observed_config(
            response_disposition="no_policy_change",
            response_heat_multiplier=1.0,
            direct_response_trust_signal=0.0,
        )
        simulation = UKPetitionSimulation(config)
        petition_item = simulation._petition_item()
        petition_item.heat = 7.5
        simulation.pending_responses = [
            PendingPetitionResponse(
                petition_id=config.petition_id,
                trigger_step=1,
                due_step=3,
            )
        ]

        trust_signal, executed = simulation._government_action(3)

        self.assertEqual(1, executed, "a formal response must be observable")
        self.assertEqual(
            "no_policy_change",
            simulation.petition.response_disposition,
            "publication must not imply policy adoption",
        )
        self.assertAlmostEqual(
            7.5,
            petition_item.heat,
            msg="publication must not imply automatic cooling",
        )
        self.assertAlmostEqual(0.0, simulation._last_response_heat_delta)
        self.assertAlmostEqual(0.0, trust_signal)
        published = [
            event
            for event in simulation.event_records
            if event["event_type"] == "government_response_published"
        ]
        self.assertEqual("no_policy_change", published[0]["value"])

    def test_petition_survives_heat_pruning_before_and_after_closure(self) -> None:
        simulation = UKPetitionSimulation(_observed_config())
        petition_id = simulation.petition.petition_item_id
        simulation._petition_item().heat = 0.0

        for step in (0, simulation.config.petition_close_step - 1):
            simulation._decay_and_prune(step)
            self.assertIn(
                petition_id,
                [item.item_id for item in simulation.information_pool],
            )
            self.assertTrue(simulation._petition_is_visible(step))

        for step in (
            simulation.config.petition_close_step,
            simulation.config.petition_close_step + 10,
        ):
            simulation._decay_and_prune(step)
            self.assertIn(
                petition_id,
                [item.item_id for item in simulation.information_pool],
            )
            self.assertFalse(simulation._petition_is_visible(step))

    def test_each_agent_signs_at_most_once_and_not_after_closure(self) -> None:
        simulation = UKPetitionSimulation(_synthetic_config())
        recommendations = _petition_recommendations(simulation)

        simulation._update_petition_support(0, recommendations)
        self.assertEqual(simulation.config.population_size, simulation._last_new_unique_signers)
        self.assertEqual(
            simulation.config.population_size,
            int(simulation.has_signed_focal_petition.sum()),
        )

        simulation._update_petition_support(1, recommendations)
        self.assertEqual(0, simulation._last_new_unique_signers)
        self.assertEqual(
            simulation.config.population_size,
            int(simulation.has_signed_focal_petition.sum()),
        )

        closed_simulation = UKPetitionSimulation(_synthetic_config())
        closed_recommendations = _petition_recommendations(closed_simulation)
        closed_simulation._update_petition_support(
            closed_simulation.config.petition_close_step,
            closed_recommendations,
        )
        self.assertEqual(0, closed_simulation._last_new_unique_signers)
        self.assertFalse(closed_simulation.has_signed_focal_petition.any())


class ReproducibilityTests(unittest.TestCase):
    def test_same_configuration_and_seed_are_fully_deterministic(self) -> None:
        config = _observed_config(seed=73123)

        first = UKPetitionSimulation(config).run()
        second = UKPetitionSimulation(config).run()

        pd.testing.assert_frame_equal(first.metrics, second.metrics)
        pd.testing.assert_frame_equal(first.storms, second.storms)
        pd.testing.assert_frame_equal(first.events, second.events)
        self.assertEqual(first.summary, second.summary)


class RunnerDesignTests(unittest.TestCase):
    def test_formal_panel_is_5250_complete_common_seed_runs(self) -> None:
        tasks = pd.DataFrame.from_records(build_tasks("formal"))
        key = ["condition_id", "alpha", "seed"]

        self.assertEqual(5_250, len(tasks))
        self.assertEqual(set(DELAY_CONDITIONS), set(tasks["condition_id"]))
        self.assertEqual(21, tasks["alpha"].nunique())
        self.assertEqual(50, tasks["seed"].nunique())
        self.assertFalse(tasks.duplicated(key).any())
        self.assertTrue(
            tasks.groupby(["condition_id", "alpha"]).size().eq(50).all()
        )
        empirical = tasks[
            tasks["condition_id"].eq("conditional_empirical_resample")
        ]
        self.assertTrue(
            empirical.groupby("seed")["response_delay_days"].nunique().eq(1).all()
        )

    def test_runner_rejects_output_outside_version2(self) -> None:
        with self.assertRaises(ValueError):
            _safe_output_dir(REPOSITORY_ROOT / "outside_v2")


if __name__ == "__main__":
    unittest.main()
