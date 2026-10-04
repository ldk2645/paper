"""Integration checks for the restored government/platform/public feedback path."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from abm_jasss.cli import aggregate_governance, task
from abm_jasss.model import Config, simulate, summarize


def restored(**kwargs):
    base = Config(n_agents=24, steps=24, final_window=8, survey_size=8,
                  initial_items=8, government_policy="respond",
                  government_interval=2, government_delay=3,
                  routine_publication_interval=4, response_threshold=.2,
                  trust_update_rate=.15, trust_feedback_strength=.5)
    return replace(base, **kwargs)


class CertainInteractions:
    """Only override item emotion: every shown item has unit interaction multiplier."""
    def __init__(self, generator):
        self.generator = generator

    def __getattr__(self, name):
        return getattr(self.generator, name)

    def beta(self, a, b):
        return np.ones(np.broadcast_arrays(a, b)[0].shape)


class RestoredModelTests(unittest.TestCase):
    def test_disabled_response_preserves_routine_publication(self):
        config = restored(response_enabled=False)
        result = simulate(config, 72)
        routine = [event for event in result["events"] if event["kind"] == "routine_publication"]
        self.assertEqual([event["step"] for event in routine], [0, 4, 8, 12, 16, 20])
        self.assertEqual([event["topic"] for event in routine], [0, 1, 2, 0, 1, 2])
        self.assertEqual(len(result["events"]), len(routine))
        self.assertEqual(result["pending_responses"], [])
        self.assertEqual(sum(row["official_arrivals"] for row in result["rows"]), 6)
        for row in result["rows"]:
            for key in ("responses_scheduled", "responses_executed", "response_arrivals", "response_exposure_share"):
                self.assertEqual(row[key], 0)

    def test_heat_action_is_delayed_and_applies_only_to_ordinary_target_items(self):
        config = restored(n_agents=4, survey_size=4, steps=4, final_window=2,
                          initial_items=1, arrivals_per_step=1, attention_budget=100,
                          supply_weights=(1, 0, 0, 0), agenda_topics=(0,),
                          heat_retention=1, heat_floor=0, government_interval=1,
                          government_delay=1, routine_publication_interval=1,
                          response_threshold=.4, response_heat_retention=.5,
                          interaction_mean=1, interaction_sd=0, trust_feedback_strength=0)
        real_factory = np.random.default_rng
        with patch("abm_jasss.model.np.random.default_rng",
                   side_effect=lambda seed: CertainInteractions(real_factory(seed))):
            result = simulate(config, 17)
        actions = [event for event in result["events"] if event["kind"] == "response_executed"]
        self.assertEqual([event["step"] for event in actions], [1, 2, 3])
        # At t=0 two ordinary items and one official item each receive 4 interactions.
        # The t=1 action must scale ordinary heat 8 to 4, excluding official heat 4.
        self.assertEqual(actions[0]["heat_before"], 8)
        self.assertEqual(actions[0]["heat_after_immediate"], 4)
        # Three ordinary items get another 4 interactions each at t=1: 4 + 12 = 16.
        self.assertEqual(actions[1]["heat_before"], 16)
        self.assertEqual(actions[1]["heat_after_immediate"], 8)
        self.assertAlmostEqual(result["rows"][1]["response_exposure_share"], 1 / 6)
        self.assertAlmostEqual(result["rows"][1]["official_exposure_share"], 3 / 6)
        for event in actions:
            self.assertEqual(event["step"] - event["trigger_step"], 1)
            self.assertEqual(event["topic"], 0)

    def test_heat_control_off_keeps_actions_and_replies(self):
        result = simulate(restored(response_heat_retention=1), 12)
        actions = [event for event in result["events"] if event["kind"] == "response_executed"]
        self.assertTrue(actions)
        for event in actions:
            self.assertEqual(event["heat_before"], event["heat_after_immediate"])
            self.assertEqual(event["immediate_reduction_fraction"], 0)
            self.assertTrue(event["reply_published"])
        self.assertEqual(sum(row["response_arrivals"] for row in result["rows"]), len(actions))
        self.assertTrue(all(row["response_effect_immediate"] == 0 for row in result["rows"]))

    def test_monitoring_capacity_queue_and_disabled_reply(self):
        config = restored(government_interval=3, government_delay=5, response_capacity=2,
                          response_threshold=0, response_publish=False)
        result = simulate(config, 25)
        pending = {}
        for event in result["events"]:
            if event["kind"] == "response_scheduled":
                self.assertNotIn(event["topic"], pending)
                self.assertEqual(event["step"] % 3, 0)
                self.assertEqual(event["due_step"], event["step"] + 5)
                pending[event["topic"]] = event
            elif event["kind"] == "response_executed":
                plan = pending.pop(event["topic"])
                self.assertEqual(plan["trigger_step"], event["trigger_step"])
                self.assertEqual(event["step"], plan["due_step"])
                self.assertFalse(event["reply_published"])
        self.assertEqual(set(pending), {event["topic"] for event in result["pending_responses"]})
        self.assertTrue(all(row["responses_scheduled"] <= 2 for row in result["rows"]))
        self.assertEqual(sum(row["response_arrivals"] for row in result["rows"]), 0)
        self.assertGreater(sum(row["responses_executed"] for row in result["rows"]), 0)

    def test_trust_updates_without_feedback_do_not_change_world(self):
        config = restored(trust_feedback_strength=0)
        exposure = simulate(config, 41)
        alignment = simulate(replace(config, trust_rule="alignment"), 41)
        self.assertEqual(exposure["events"], alignment["events"])
        for left, right in zip(exposure["rows"], alignment["rows"]):
            self.assertEqual({key: value for key, value in left.items() if not key.startswith("trust_")},
                             {key: value for key, value in right.items() if not key.startswith("trust_")})
        self.assertNotEqual(exposure["rows"][-1]["trust_mean"], alignment["rows"][-1]["trust_mean"])
        self.assertNotEqual(exposure["initial_trust_mean"], exposure["rows"][-1]["trust_mean"])
        feedback = simulate(replace(config, trust_feedback_strength=1), 41)
        self.assertNotEqual([row["interactions"] for row in exposure["rows"]],
                            [row["interactions"] for row in feedback["rows"]])

    def test_trust_spread_and_agenda_are_distinct_from_public_truth(self):
        config = restored(population_weights=(.01, .01, .01, .97), agenda_topics=(0, 1, 2),
                          preference_concentration=100, initial_trust_sd=.15)
        result = simulate(config, 30)
        self.assertLess(result["rows"][0]["public_preference_on_agenda"], .1)
        self.assertGreater(result["rows"][0]["trust_p90"], result["rows"][0]["trust_p10"])
        for row in result["rows"]:
            self.assertAlmostEqual(row["public_preference_on_agenda"], sum(row[f"truth_{k}"] for k in (0, 1, 2)))
            self.assertAlmostEqual(row["agenda_gap"], config.agenda_target_share - row["agenda_attention_share"])
            for key in ("official_exposure_share", "response_exposure_share", "response_effect_immediate",
                        "agenda_attention_share", "agenda_shortfall", "trust_mean", "trust_p10", "trust_p90"):
                self.assertGreaterEqual(row[key], 0)
                self.assertLessEqual(row[key], 1)
            self.assertLessEqual(row["response_exposure_share"], row["official_exposure_share"])

    def test_census_information_changes_target_with_skewed_content_supply(self):
        config = restored(n_agents=30, survey_size=30, population_weights=(.97, .01, .01, .01),
                          preference_concentration=100, supply_weights=(0, 0, 0, 1), alpha=1,
                          initial_items=24, agenda_topics=(0,), observation_interval=1,
                          observation_window=1, government_interval=1, government_delay=2,
                          response_threshold=.3)
        platform = simulate(config, 37)
        census = simulate(replace(config, active_arm="survey"), 37)
        first_platform = next(event for event in platform["events"] if event["kind"] == "response_scheduled")
        first_census = next(event for event in census["events"] if event["kind"] == "response_scheduled")
        self.assertEqual(first_platform["topic"], 3)
        self.assertEqual(first_census["topic"], 0)
        self.assertEqual(first_platform["step"], 0)
        self.assertEqual(first_census["step"], 0)
        self.assertTrue(all(row["error_survey"] < 1e-12 for row in census["rows"]))
        self.assertLess(first_census["target_estimation_error"], 1e-12)
        self.assertGreater(first_platform["target_estimation_error"], .5)

    def test_terminal_pending_and_storm_censoring_are_retained(self):
        config = restored(steps=12, final_window=4, government_delay=30,
                          population_weights=(.001, .001, .001, .997), preference_concentration=1000,
                          supply_weights=(0, 0, 0, 1), agenda_topics=(0,),
                          alpha=0, attention_budget=1, active_arm="oracle", response_threshold=.4)
        result = simulate(config, 62)
        self.assertEqual(len(result["pending_responses"]), 1)
        self.assertEqual(result["pending_responses"][0]["due_step"], 30)
        self.assertEqual(sum(row["responses_executed"] for row in result["rows"]), 0)
        self.assertEqual(result["storm_episodes"], [dict(start_step=0, end_step=11, duration=12,
                                                      peak_value=1, right_censored=True)])
        summary = summarize(result)[0]
        self.assertEqual(summary["responses_scheduled"], 1)
        self.assertEqual(summary["responses_pending_at_end"], 1)
        self.assertEqual(summary["longest_observed_storm"], 12)

    def test_cli_event_artifact_and_governance_aggregate(self):
        config = restored(steps=10, final_window=4)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "events").mkdir()
            result = task(config, 5, str(output), "restored", False)
            artifact = json.loads((output / "events" / "restored.json").read_text())
            self.assertEqual(set(artifact), {"events", "storm_episodes", "pending_responses"})
            scheduled = sum(event["kind"] == "response_scheduled" for event in artifact["events"])
            executed = sum(event["kind"] == "response_executed" for event in artifact["events"])
            self.assertEqual(scheduled - executed, len(artifact["pending_responses"]))
            metrics = aggregate_governance(result["summary"])
            by_name = {row["metric"]: row for row in metrics}
            self.assertEqual(by_name["responses_scheduled"]["mean"], scheduled)
            self.assertEqual(by_name["responses_executed"]["mean"], executed)
            self.assertEqual(by_name["responses_pending_at_end"]["mean"], scheduled - executed)
            self.assertTrue(all(row["n_runs"] == 1 and row["ci_low"] is None for row in metrics))


if __name__ == "__main__":
    unittest.main()
