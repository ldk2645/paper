"""Constructed P1 mechanism acceptance, separate from effect-size evidence.

The label check holds object identities and potential shocks fixed; it does not
claim finite-sample invariance after independently regenerating a population.
"""
from dataclasses import replace
import unittest
from unittest.mock import patch

import numpy as np

from abm_jasss.research_config import ResearchConfig
from abm_jasss.research_governance import DecisionSettings, ResponseQueue
from abm_jasss.research_outcomes import summarize_world
from abm_jasss.research_world import ResearchWorld


def mechanism_config(**changes):
    values = dict(
        n_agents=12, n_topics=2, steps=8, final_window=3,
        population_weights=(1., 1.), agenda_topics=(0,), advantaged_topic=1,
        initial_items=8, arrivals_per_step=2, attention_budget=2,
        emotion_mean=.8, emotion_advantage=0., official_emotion_mean=.8,
        interaction_mean=1., interaction_sd=0., drift_rate=0.,
        survey_size=12, survey_interval=1, observation_window=2,
        update_frequency=1, inference_grid=4, reference_agents=2,
        response_threshold=0., routine_publication_interval=2,
        completion_followup=2, trust_feedback_strength=0.,
    )
    values.update(changes)
    return ResearchConfig(**values)


class ResearchS1MechanismTests(unittest.TestCase):
    def test_zero_delay_uses_yesterdays_survey_but_reply_is_consumed_today(self):
        world = ResearchWorld(mechanism_config(
            pref_info=True, sampling_rate=0., government_delay=0,
            attention_budget=100), 201)
        world.preferences[:] = (.1, .9)
        first = world.step()
        self.assertEqual(first["responses_scheduled"], 0)
        self.assertEqual(world.survey_log[0]["available_at"], 1)

        # A sharply changed current truth is unavailable to the decision maker.
        world.preferences[:] = (.9, .1)
        row = world.step()
        event = world.events[-1]
        self.assertEqual(event["topic"], 1)
        self.assertEqual(event["trigger_step"], 1)
        self.assertEqual(event["due_step"], 1)
        self.assertEqual(event["execution_step"], 1)
        self.assertEqual(event["waiting_time"], 0)
        np.testing.assert_allclose(event["P_trigger"], (.9, .1))
        self.assertEqual(event["P_trigger"], event["P_execution"])
        self.assertEqual(world.information_log[-1]["survey"]["measured_at"], 0)
        self.assertEqual(world.government_estimates[-1]["consumed_fields"], ["survey.estimate"])
        self.assertGreater(row["response_exposure_share"], 0)
        reply = next(item for item in world.publication_log if item["source"] == 2)
        self.assertIn(reply["item_id"], {item["item_id"] for item in world.catalogs["1"]})

        # The new preference can affect a response only after its own delivery.
        world.step()
        self.assertEqual(world.events[-1]["topic"], 0)
        self.assertEqual(world.information_log[-1]["survey"]["measured_at"], 1)

    def test_scheduling_capacity_does_not_throttle_already_due_execution(self):
        parent = ResearchWorld(mechanism_config(
            n_topics=3, population_weights=(1., 1., 1.), advantaged_topic=2,
            pref_info=True, sampling_rate=0., government_delay=3,
            response_capacity=2, response_threshold=.1), 202)
        parent.preferences[:] = (.5, .3, .2)
        parent.run(2)
        pending = parent.queue.snapshot()["pending"]
        self.assertEqual(len(pending), 2)
        branch = parent.fork("capacity_one", {"response_capacity": 1}).run(6)

        self.assertEqual(branch.trajectory[2]["responses_scheduled"], 1)
        self.assertEqual(branch.trajectory[2]["pending_count"], 3)
        self.assertEqual(branch.trajectory[3]["responses_scheduled"], 0)
        # Both inherited plans fall due together despite the new capacity of 1.
        self.assertEqual(branch.trajectory[4]["responses_executed"], 2)
        self.assertEqual(branch.trajectory[4]["responses_scheduled"], 0)
        self.assertEqual(branch.trajectory[5]["responses_scheduled"], 1)
        self.assertEqual(branch.trajectory[5]["responses_executed"], 1)
        for plan in pending:
            event = next(e for e in branch.events if e["event_id"] == plan["event_id"])
            self.assertEqual(event["execution_step"], plan["due_step"])
            self.assertEqual(event["action_parameters"], plan["action_parameters"])
        self.assertEqual(parent.queue.snapshot()["pending"], pending)

    def test_full_heat_off_blocks_active_response_and_trust_heat_paths(self):
        for ranking in ("topk", "softmax"):
            with self.subTest(ranking=ranking):
                config = mechanism_config(
                    steps=6, full_heat_off=True, ranking=ranking,
                    pref_info=True, rule_info=True, government_delay=0,
                    heat_retention=.01, heat_floor=1e8, max_item_age=20,
                    response_heat_retention=.1, trust_response_gain=5.,
                    trust_update_rate=.5, trust_feedback_strength=.5)
                cold = ResearchWorld(config, 203)
                hot = ResearchWorld(config, 203)
                initial_heat = np.arange(1, len(hot.ids) + 1, dtype=float) * 100.
                initial_ids = hot.ids.copy()
                hot.heat[:] = initial_heat
                cold.run()
                hot.run()

                self.assertGreater(sum(row["interactions"] for row in hot.trajectory), 0)
                executed = [event for event in hot.events if event["execution_step"] is not None]
                self.assertTrue(any(event["heat_before"] > 0 for event in executed))
                self.assertTrue(all(event["heat_before"] == event["heat_after_immediate"]
                                    and not event["heat_action_enabled"] for event in executed))
                self.assertTrue(all(row["response_effect_immediate"] == 0 for row in hot.trajectory))
                np.testing.assert_array_equal(hot.heat[np.isin(hot.ids, initial_ids)], initial_heat)
                np.testing.assert_array_equal(cold.heat, np.zeros(len(cold.heat)))
                np.testing.assert_array_equal(hot.trust, cold.trust)
                np.testing.assert_array_equal(hot.ids, cold.ids)
                self.assertEqual(hot.trajectory, cold.trajectory)
                self.assertEqual(hot.public_signal_ticks, cold.public_signal_ticks)
                # The disclosed inverse also ignores heat, including residual heat
                # carried by a hypothetical already-hot boundary state.
                self.assertEqual([r["estimate"] for r in hot.government_estimates],
                                 [r["estimate"] for r in cold.government_estimates])

    def test_trust_update_feedback_factorial_preserves_initial_distribution(self):
        worlds = {}
        for update, feedback in ((False, False), (False, True), (True, False), (True, True)):
            world = ResearchWorld(mechanism_config(
                n_agents=24, survey_size=24, pref_info=True, government_delay=0,
                full_heat_off=True, alpha=0., max_item_age=20,
                population_weights=(1., 1.), supply_weights=(0., 1.),
                trust_update_rate=.8 if update else 0.,
                trust_feedback_strength=1. if feedback else 0.,
                trust_official_gain=0., trust_offagenda_penalty=3.), 204)
            world.preferences[:] = (0., 1.)
            world.topics[:] = 1
            world.emotions[:] = 1.
            initial_trust = world.trust.copy()
            world.run()
            worlds[update, feedback] = world
            with self.subTest(update=update, feedback=feedback):
                if update:
                    self.assertFalse(np.array_equal(world.trust, initial_trust))
                else:
                    np.testing.assert_array_equal(world.trust, initial_trust)
                summary = summarize_world(world.trajectory, world.events, world.config.analysis_config())
                for metric in ("platform_representation_gap", "perception_error", "targeting_error_trigger"):
                    self.assertIsNotNone(summary[metric], metric)

        self.assertEqual(len({world.initial_state_hash for world in worlds.values()}), 1)
        for world in worlds.values():
            np.testing.assert_array_equal(world.baseline_trust, worlds[False, False].baseline_trust)
        self.assertGreater(float(np.std(worlds[False, False].baseline_trust)), 0)
        # Feedback=0 makes the dynamic and frozen trust worlds physically identical.
        self.assertEqual(worlds[False, False].public_signal_ticks, worlds[True, False].public_signal_ticks)
        self.assertEqual(worlds[False, False].supply_log, worlds[True, False].supply_log)
        # Feedback acts before this tick's update: initial activity agrees, later
        # activity diverges once trust has actually changed.
        activity = lambda world: [row["interactions"] for row in world.trajectory]
        self.assertEqual(activity(worlds[False, True])[0], activity(worlds[True, True])[0])
        self.assertNotEqual(activity(worlds[False, True])[1:], activity(worlds[True, True])[1:])
        self.assertNotEqual(activity(worlds[False, False]), activity(worlds[False, True]))

    def test_topic_relabeling_preserves_consumption_and_preference_drift(self):
        mapping = np.array([2, 0, 1])  # old index -> new index
        inverse = np.argsort(mapping)
        for ranking in ("topk", "softmax"):
            with self.subTest(ranking=ranking):
                config = mechanism_config(
                    n_topics=3, population_weights=(1., 2., 3.), advantaged_topic=2,
                    ranking=ranking, response_enabled=False, alpha=.6,
                    initial_items=9, drift_rate=.2, drift_threshold=1,
                    trust_update_rate=.3, trust_feedback_strength=.4)
                original = ResearchWorld(config, 205)
                original.topics[:] = np.arange(9) % 3
                original.heat[:] = np.arange(9, dtype=float)
                relabeled = ResearchWorld.from_snapshot(original.snapshot())
                relabeled.config = replace(
                    config, agenda_topics=tuple(int(mapping[k]) for k in config.agenda_topics),
                    advantaged_topic=int(mapping[config.advantaged_topic]),
                    population_weights=tuple(np.asarray(config.population_weights)[inverse]))
                relabeled.preferences = original.preferences[:, inverse].copy()
                relabeled.initial_truth = original.initial_truth[inverse].copy()
                relabeled.topics = mapping[original.topics]

                # A shared fixed catalog avoids confounding relabeling with
                # topic-indexed publication identities or a new supply draw.
                with patch.object(original, "add_content"), patch.object(relabeled, "add_content"):
                    first, second = original.step(), relabeled.step()
                for key in ("P_true", "E_exposure", "S_public"):
                    self.assertIsNotNone(first[key])
                    np.testing.assert_allclose(np.asarray(first[key])[inverse], second[key])
                for key in ("interactions", "exposure_gap", "platform_representation_gap",
                            "official_exposure_share", "agenda_attention_share", "trust_mean"):
                    self.assertAlmostEqual(first[key], second[key])
                np.testing.assert_allclose(original.preferences[:, inverse], relabeled.preferences)
                np.testing.assert_array_equal(original.heat, relabeled.heat)
                np.testing.assert_allclose(original.trust, relabeled.trust)

    def test_topic_relabeling_preserves_selective_scheduling_and_due_targets(self):
        mapping = np.array([2, 0, 1])
        inverse = np.argsort(mapping)
        settings = DecisionSettings(3, (0, 2), .1, "selective", 1, 2, 0, .7, True)
        original = ResponseQueue(settings)
        relabeled = ResponseQueue(replace(settings, agenda_topics=(2, 1)))
        estimate = np.array([.25, .6, .15])
        # Topic 1 has the largest estimated demand but is not on the agenda.
        original.schedule(3, estimate, True, np.random.default_rng(9), {"packet": "history"})
        relabeled.schedule(3, estimate[inverse], True, np.random.default_rng(9), {"packet": "history"})
        first, second = original.due(3), relabeled.due(3)
        self.assertEqual({plan["topic"] for plan in first}, {0, 2})
        self.assertEqual({int(mapping[plan["topic"]]) for plan in first},
                         {plan["topic"] for plan in second})
        by_topic = {plan["topic"]: plan for plan in second}
        for plan in first:
            other = by_topic[int(mapping[plan["topic"]])]
            for key in ("signal_value", "trigger_step", "due_step", "action_parameters"):
                self.assertEqual(plan[key], other[key])
        self.assertEqual(original.pending, {})
        self.assertEqual(relabeled.pending, {})


if __name__ == "__main__":
    unittest.main()
