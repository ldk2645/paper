"""Integration acceptance for the separately versioned research engine.

Small deterministic worlds exercise the actual observation/decision/platform
boundary. These are implementation checks, not evidence for treatment benefit.
"""
import copy
from dataclasses import replace
import json
import unittest

import numpy as np

from abm_jasss.research_config import ResearchConfig
from abm_jasss.research_outcomes import summarize_world
from abm_jasss.research_randomness import AddressedRandomness
from abm_jasss.research_world import ResearchWorld, canonical_hash, jsonable


def small_config(**changes):
    values = dict(
        n_agents=12, n_topics=2, steps=12, final_window=4,
        population_weights=(1., 1.), agenda_topics=(0,), advantaged_topic=1,
        initial_items=8, arrivals_per_step=2, attention_budget=2,
        emotion_mean=.8, emotion_advantage=0., official_emotion_mean=.8,
        interaction_mean=1., interaction_sd=0., trust_feedback_strength=0.,
        survey_size=6, survey_interval=2, observation_window=2,
        update_frequency=1, inference_grid=4, reference_agents=2,
        response_threshold=0., routine_publication_interval=2,
        completion_followup=3,
    )
    values.update(changes)
    return ResearchConfig(**values)


class ResearchWorldTests(unittest.TestCase):
    def test_four_cells_deliver_and_consume_only_authorized_information(self):
        initial_hashes = set()
        budgets = set()
        for pref, rule in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(pref_info=pref, rule_info=rule):
                world = ResearchWorld(small_config(pref_info=pref, rule_info=rule), 41)
                initial_hashes.add(world.initial_state_hash)
                world.run(4)
                self.assertTrue(any(row["has_data"] for row in world.trajectory))
                updates = [row for row in world.government_estimates if row["updated"]]
                self.assertTrue(updates)
                used = {field for row in updates for field in row["consumed_fields"]}
                self.assertEqual("survey.estimate" in used, pref)
                self.assertEqual("rule.alpha" in used, rule)
                for info, record in zip(world.information_log, world.government_estimates):
                    self.assertNotIn("P_true", info)
                    self.assertNotIn("E_exposure", info)
                    self.assertEqual("survey" in record["allowed_fields"], pref)
                    self.assertEqual("rule" in record["allowed_fields"], rule)
                    if not pref:
                        self.assertIsNone(info["survey"])
                    if not rule:
                        self.assertIsNone(info["rule"])
                budgets.add(updates[0]["forward_evaluations"])
        self.assertEqual(len(initial_hashes), 1)
        self.assertEqual(len(budgets), 1)

    def test_same_exposure_can_generate_different_public_interaction_signals(self):
        config = small_config(alpha=0., attention_budget=1, response_enabled=False,
                              drift_rate=0., trust_update_rate=0.)
        first = ResearchWorld(config, 43)
        # Both topics have selectable content and equally sized interested groups.
        # Only the groups' private willingness to interact differs across worlds.
        midpoint = config.n_agents // 2
        first.preferences[:midpoint] = (1., 0.)
        first.preferences[midpoint:] = (0., 1.)
        first.topics[:] = np.arange(len(first.topics)) % config.n_topics
        first.emotions[:] = 1.
        second = ResearchWorld.from_snapshot(first.snapshot())
        first.emotionality[:midpoint], first.emotionality[midpoint:] = 1., 0.
        second.emotionality[:midpoint], second.emotionality[midpoint:] = 0., 1.

        first_row, second_row = first.step(), second.step()

        self.assertEqual(first_row["P_true"], second_row["P_true"])
        self.assertEqual(first_row["E_exposure"], [.5, .5])
        self.assertEqual(first_row["E_exposure"], second_row["E_exposure"])
        self.assertGreater(first_row["interactions"], 0)
        self.assertGreater(second_row["interactions"], 0)
        self.assertEqual(first_row["S_public"], [1., 0.])
        self.assertEqual(second_row["S_public"], [0., 1.])
        self.assertNotEqual(first.public_signal_ticks[0]["raw_counts"],
                            second.public_signal_ticks[0]["raw_counts"])

    def test_hidden_preferences_and_evaluator_history_cannot_change_current_decisions(self):
        original = ResearchWorld(small_config(pref_info=False, rule_info=False,
                                              government_delay=3), 44).run(1)
        altered = ResearchWorld.from_snapshot(original.snapshot())
        altered.preferences[:] = (0., 1.)
        altered.truth_history["0"] = [0., 1.]
        altered.trajectory[0]["P_true"] = [0., 1.]
        altered.trajectory[0]["E_exposure"] = [0., 1.]
        self.assertNotEqual(original.trajectory[0], altered.trajectory[0])
        # Keep all currently deliverable evidence and government state fixed.
        self.assertEqual(original.pending_packets, altered.pending_packets)
        self.assertEqual(original.catalogs, altered.catalogs)
        self.assertEqual(original.sensing.snapshot(), altered.sensing.snapshot())
        self.assertEqual(original.queue.snapshot(), altered.queue.snapshot())
        self.assertEqual(original.randomness.snapshot(), altered.randomness.snapshot())

        original_row, altered_row = original.step(), altered.step()

        self.assertNotEqual(original_row["P_true"], altered_row["P_true"])
        self.assertEqual(original.information_log[-1], altered.information_log[-1])
        self.assertEqual(original.government_estimates[-1], altered.government_estimates[-1])
        self.assertTrue(original.government_estimates[-1]["updated"])
        self.assertGreater(original_row["responses_scheduled"], 0)
        self.assertEqual(original.queue.snapshot(), altered.queue.snapshot())
        government_actions = lambda world: [
            {key: value for key, value in event.items()
             if key not in {"P_trigger", "P_execution"}}
            for event in world.events if event["trigger_step"] == 1]
        self.assertEqual(government_actions(original), government_actions(altered))

    def test_zero_and_positive_delay_schedule_then_execute_without_duplicate_topics(self):
        for delay in (0, 3):
            with self.subTest(delay=delay):
                world = ResearchWorld(small_config(pref_info=True, sampling_rate=0.,
                                                   government_delay=delay), 7).run()
                self.assertTrue(world.events)
                self.assertEqual(world.trajectory[0]["responses_scheduled"], 0)
                self.assertEqual(world.trajectory[1]["responses_scheduled"], 1)
                executed = [event for event in world.events if event["execution_step"] is not None]
                self.assertTrue(executed)
                self.assertEqual(len({e["event_id"] for e in world.events}), len(world.events))
                for event in world.events:
                    self.assertEqual(event["due_step"] - event["trigger_step"], delay)
                    self.assertEqual(event["P_trigger"], world.trajectory[event["trigger_step"]]["P_true"])
                    if event["execution_step"] is None:
                        self.assertIsNone(event["P_execution"])
                        self.assertGreaterEqual(event["due_step"], world.tick)
                    else:
                        self.assertEqual(event["execution_step"], event["due_step"])
                        self.assertEqual(event["waiting_time"], delay)
                        self.assertEqual(event["P_execution"], world.trajectory[event["execution_step"]]["P_true"])
                for topic in range(world.config.n_topics):
                    events = [e for e in world.events if e["topic"] == topic]
                    for previous, current in zip(events, events[1:]):
                        self.assertIsNotNone(previous["execution_step"])
                        self.assertGreater(current["trigger_step"], previous["execution_step"])
                # An executed reply is actually in that tick's ranking pool.
                first = executed[0]
                catalog = world.catalogs[str(first["execution_step"])]
                replies = [p for p in world.publication_log if p["source"] == 2
                           and p["born"] == first["execution_step"] and p["topic"] == first["topic"]]
                self.assertTrue(replies)
                self.assertIn(replies[0]["item_id"], {item["item_id"] for item in catalog})

    def test_public_delivery_and_estimator_use_never_precede_source_availability(self):
        world = ResearchWorld(small_config(observation_delay=2, update_frequency=2), 21).run()
        self.assertTrue(world.observation_packets)
        for delivery in world.observation_packets:
            self.assertEqual(delivery["available_at"], delivery["generated_at"] + 3)
            self.assertEqual(delivery["received_at"], delivery["available_at"])
        for info, row, estimate in zip(world.information_log, world.trajectory,
                                      world.government_estimates):
            now = row["step"]
            packet = info["public_packet"]
            if packet is not None:
                self.assertLess(packet["window_end"], now)
                self.assertLessEqual(packet["available_at"], now)
                self.assertEqual(info["catalog_observed_at"], packet["window_end"])
            if estimate["estimate_input_packet_id"] is not None:
                used = world.packet_index[estimate["estimate_input_packet_id"]]
                self.assertLessEqual(used["available_at"], estimate["estimate_updated_at"])
                self.assertLess(used["window_end"], estimate["estimate_updated_at"])
        self.assertTrue(all(row["S_available"] is None for row in world.trajectory[:3]))
        # Tick 3 receives data but must wait for the registered tick 4 update.
        self.assertIsNotNone(world.trajectory[3]["S_available"])
        self.assertFalse(world.government_estimates[3]["updated"])
        self.assertEqual(world.trajectory[3]["P_hat_gov"], world.trajectory[2]["P_hat_gov"])

    def test_legal_survey_drives_decisions_without_public_observations(self):
        world = ResearchWorld(small_config(pref_info=True, sampling_rate=0.,
                                           government_delay=0), 8).run()
        self.assertTrue(all(row["S_public"] is None and row["S_available"] is None
                            for row in world.trajectory))
        self.assertFalse(world.trajectory[0]["has_data"])
        self.assertTrue(world.trajectory[1]["has_data"])
        self.assertGreater(sum(row["responses_executed"] for row in world.trajectory), 0)
        for row in world.government_estimates:
            if row["updated"]:
                self.assertEqual(row["consumed_fields"], ["survey.estimate"])
                self.assertIsNone(row["estimate_input_packet_id"])

    def test_snapshot_json_restore_reproduces_every_remaining_boundary(self):
        config = small_config(pref_info=True, rule_info=True, observation_delay=2,
                              survey_delay=1, smoothing=.4, update_frequency=2,
                              sampling_rate=.5, observation_noise=.2, drift_rate=.1,
                              drift_threshold=1, trust_feedback_strength=.3)
        original = ResearchWorld(config, 103).run(5)
        snapshot = json.loads(json.dumps(original.snapshot(), allow_nan=False))
        self.assertTrue(snapshot["state"]["pending_packets"])
        self.assertTrue(snapshot["state"]["pending_surveys"])
        self.assertTrue(snapshot["state"]["queue"]["pending"])
        restored = ResearchWorld.from_snapshot(snapshot)
        self.assertEqual(original.snapshot(), restored.snapshot())
        for _ in range(original.tick, config.steps):
            self.assertEqual(original.step(), restored.step())
            self.assertEqual(original.snapshot(), restored.snapshot())
        uninterrupted = ResearchWorld(config, 103).run()
        self.assertEqual(original.snapshot(), uninterrupted.snapshot())

    def test_snapshot_rejects_modified_payload_and_wrong_boundary(self):
        world = ResearchWorld(small_config(), 8).run(2)
        corrupt = world.snapshot()
        corrupt["state"]["arrays"]["preferences"][0][0] += .01
        with self.assertRaisesRegex(ValueError, "hash"):
            ResearchWorld.from_snapshot(corrupt)
        wrong_phase = world.snapshot()
        wrong_phase["state"]["phase"] = "mid_consumption"
        wrong_phase["state_hash"] = canonical_hash(wrong_phase["state"])
        with self.assertRaisesRegex(ValueError, "phase"):
            ResearchWorld.from_snapshot(wrong_phase)

    def test_forks_share_pre_treatment_hash_and_are_independent_objects(self):
        parent = ResearchWorld(small_config(pref_info=True), 19).run(4)
        before = parent.snapshot()
        left = parent.fork("B0")
        right = parent.fork("B4", {"alpha": .9})
        for branch in (left, right):
            self.assertEqual(branch.treatments[-1]["pre_treatment_state_hash"], before["state_hash"])
            self.assertEqual(branch.parent_world_id, parent.world_id)
        left_before = left.snapshot()
        right.preferences[0] = (1., 0.)
        right.pending_packets[0]["packet_id"] = "branch-only"
        right.trajectory[0]["P_true"][0] = -1.
        right.queue.streak[0] += 100
        self.assertEqual(parent.snapshot(), before)
        self.assertEqual(left.snapshot(), left_before)
        left.run()
        parent.run()
        for field in ResearchWorld.LOG_FIELDS:
            if field != "treatments":
                self.assertEqual(jsonable(getattr(left, field)), jsonable(getattr(parent, field)), field)
        for field in ResearchWorld.ARRAY_FIELDS:
            np.testing.assert_array_equal(getattr(left, field), getattr(parent, field))

    def test_existing_response_plans_keep_due_date_and_action_parameters_after_fork(self):
        parent = ResearchWorld(small_config(pref_info=True, sampling_rate=0.,
                                            government_delay=3), 5).run(2)
        pending = copy.deepcopy(parent.queue.pending)
        self.assertTrue(pending)
        branch = parent.fork("faster_stronger", {"government_delay": 0,
                             "response_heat_retention": .2, "response_capacity": 2})
        self.assertEqual(branch.queue.pending, pending)
        branch.run()
        ids = {plan["event_id"] for plan in pending.values()}
        for plan in pending.values():
            event = next(e for e in branch.events if e["event_id"] == plan["event_id"])
            self.assertEqual(event["execution_step"], plan["due_step"])
            self.assertEqual(event["action_parameters"], plan["action_parameters"])
        new_plans = [e for e in branch.events if e["event_id"] not in ids]
        self.assertTrue(new_plans)
        for event in new_plans:
            self.assertEqual(event["due_step"], event["trigger_step"])
            self.assertEqual(event["action_parameters"]["heat_retention"], .2)
        self.assertEqual(parent.queue.pending, pending)

    def test_revoking_survey_access_keeps_history_but_filters_new_government_input(self):
        parent = ResearchWorld(small_config(pref_info=True, sampling_rate=0.,
                                            survey_interval=1), 16).run(4)
        self.assertIsNotNone(parent.latest_survey)
        previous_estimate = parent.sensing.estimate
        previous_history = copy.deepcopy(jsonable(parent.survey_log))
        branch = parent.fork("no_new_surveys", {"pref_info": False})
        self.assertEqual(branch.sensing.estimate, previous_estimate)
        self.assertEqual(jsonable(branch.survey_log), previous_history)
        branch.run()
        self.assertEqual(jsonable(branch.survey_log), previous_history)
        for info in branch.information_log[parent.tick:]:
            self.assertIsNone(info["survey"])
        self.assertEqual(branch.sensing.estimate, previous_estimate)
        self.assertTrue(branch.sensing.has_data)

    def test_exogenous_supply_and_routine_publications_survive_different_response_counts(self):
        parent = ResearchWorld(small_config(pref_info=True, sampling_rate=0.,
                                            government_delay=4), 29).run(2)
        slow = parent.fork("B0").run()
        fast = parent.fork("B2", {"government_delay": 0, "response_capacity": 2}).run()
        self.assertEqual(slow.supply_log, fast.supply_log)
        routine = lambda w: [item for item in w.publication_log if item["source"] == 1]
        replies = lambda w: [item for item in w.publication_log if item["source"] == 2]
        self.assertEqual(routine(slow), routine(fast))
        self.assertNotEqual(len(replies(slow)), len(replies(fast)))
        for world in (slow, fast):
            all_items = world.supply_log + world.publication_log
            self.assertEqual(len({item["item_id"] for item in all_items}), len(all_items))

    def test_addressed_randomness_preserves_shared_object_draws_under_reordering(self):
        rng = AddressedRandomness(38)
        people = np.array([[0], [7]])
        items = np.array([[101, 103, 109]])
        original = rng.item_uniforms("interaction", 4, people, items)
        # Extra endogenous response draws must not consume ordinary-shock state.
        rng.generator("response_content", 4, 0).random(100)
        rng.generator("survey", 4).random(50)
        reordered = rng.item_uniforms("interaction", 4, people, np.array([[999, 109, 101]]))
        np.testing.assert_array_equal(original[:, [2, 0]], reordered[:, [1, 2]])
        restored = AddressedRandomness.from_snapshot(json.loads(json.dumps(rng.snapshot())))
        np.testing.assert_array_equal(original, restored.item_uniforms("interaction", 4, people, items))
        self.assertFalse(np.array_equal(original, rng.item_uniforms("ranking", 4, people, items)))

    def test_no_drift_and_frozen_trust_preserve_states_during_active_dynamics(self):
        world = ResearchWorld(small_config(pref_info=True, drift_rate=0.,
                                           trust_update_rate=0., trust_feedback_strength=.5), 52)
        preferences, trust = world.preferences.copy(), world.trust.copy()
        initial_items = set(world.ids)
        for _ in range(world.config.steps):
            world.step()
            np.testing.assert_array_equal(world.preferences, preferences)
            np.testing.assert_array_equal(world.trust, trust)
        self.assertGreater(sum(row["interactions"] for row in world.trajectory), 0)
        self.assertGreater(sum(row["responses_executed"] for row in world.trajectory), 0)
        self.assertNotEqual(set(world.ids), initial_items)

    def test_disabling_trust_feedback_removes_state_influence_without_freezing_updates(self):
        config = small_config(response_enabled=False, drift_rate=0.,
                              trust_feedback_strength=0., trust_update_rate=.5)
        low = ResearchWorld(config, 57)
        high = ResearchWorld(config, 57)
        low.trust[:] = .1
        high.trust[:] = .9
        low_start, high_start = low.trust.copy(), high.trust.copy()
        low.run()
        high.run()
        self.assertFalse(np.array_equal(low.trust, low_start))
        self.assertFalse(np.array_equal(high.trust, high_start))
        self.assertEqual(low.public_signal_ticks, high.public_signal_ticks)
        self.assertEqual([r["E_exposure"] for r in low.trajectory],
                         [r["E_exposure"] for r in high.trajectory])

    def test_full_heat_off_preserves_interactions_and_uses_ttl_instead_of_heat_floor(self):
        config = small_config(full_heat_off=True, heat_floor=1e6, cold_start_rounds=1,
                              max_item_age=4, pref_info=True, government_delay=0)
        off = ResearchWorld(config, 61)
        alpha_zero = ResearchWorld(replace(config, full_heat_off=False, alpha=0.), 61)
        off.step()
        alpha_zero.step()
        self.assertGreater(len(off.ids), 0)
        self.assertEqual(len(alpha_zero.ids), 0)
        off.run()
        np.testing.assert_array_equal(off.heat, np.zeros(len(off.heat)))
        self.assertTrue(any(row["S_public"] is not None for row in off.trajectory))
        executed = [e for e in off.events if e["execution_step"] is not None]
        self.assertTrue(executed)
        self.assertTrue(all(not e["heat_action_enabled"] for e in executed))
        self.assertTrue(all(e["heat_before"] == e["heat_after_immediate"] for e in executed))
        expected_ids = {item["item_id"] for item in off.supply_log + off.publication_log
                        if off.tick - item["born"] < config.max_item_age}
        self.assertEqual(set(off.ids), expected_ids)

    def test_full_heat_off_ranking_and_interaction_are_invariant_to_hidden_heat(self):
        for ranking in ("topk", "softmax"):
            with self.subTest(ranking=ranking):
                config = small_config(full_heat_off=True, ranking=ranking, response_enabled=False,
                                      max_item_age=20, drift_rate=0.)
                zero = ResearchWorld(config, 62)
                hot = ResearchWorld(config, 62)
                initial_ids = hot.ids.copy()
                initial_heat = np.arange(1, len(hot.ids) + 1, dtype=float) * 100.
                hot.heat[:] = initial_heat
                zero.run(3)
                hot.run(3)
                self.assertEqual([r["E_exposure"] for r in zero.trajectory],
                                 [r["E_exposure"] for r in hot.trajectory])
                self.assertEqual(zero.public_signal_ticks, hot.public_signal_ticks)
                np.testing.assert_array_equal(zero.ids, hot.ids)
                np.testing.assert_array_equal(hot.heat[np.isin(hot.ids, initial_ids)], initial_heat)

    def test_no_response_keeps_routine_publications_and_reports_missing_targeting(self):
        config = small_config(response_enabled=False, sampling_rate=0.)
        world = ResearchWorld(config, 70).run()
        self.assertEqual(world.events, [])
        routine = [p for p in world.publication_log if p["source"] == 1]
        self.assertEqual([p["born"] for p in routine], list(range(0, config.steps, 2)))
        self.assertFalse(any(p["source"] == 2 for p in world.publication_log))
        summary = summarize_world(world.trajectory, world.events, config.analysis_config())
        self.assertEqual(summary["execution_count"], 0)
        self.assertIsNone(summary["targeting_error_trigger"])
        self.assertIsNone(summary["targeting_error_execution"])
        self.assertIsNone(summary["response_completion_L"])
        self.assertIsNone(summary["platform_representation_gap"])
        self.assertIsNone(summary["perception_error"])
        self.assertIsNotNone(summary["exposure_gap"])


if __name__ == "__main__":
    unittest.main()
